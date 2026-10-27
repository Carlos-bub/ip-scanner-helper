"""Bounded TCP profiles and explicit protocol/port/service descriptions."""

from dataclasses import dataclass
from collections.abc import Mapping
import re

MAX_PROFILE_PORTS = 128
MAX_CUSTOM_PROFILES = 8


@dataclass(frozen=True)
class ServicePort:
    protocol: str
    number: int
    service: str

    def __post_init__(self):
        if self.protocol not in ("tcp", "udp"):
            raise ValueError("Protocolo inválido. Use TCP ou UDP.")
        if isinstance(self.number, bool) or not isinstance(self.number, int) or not 1 <= self.number <= 65535:
            raise ValueError("A porta deve ser um inteiro entre 1 e 65535.")
        if (not isinstance(self.service, str) or not self.service.strip() or len(self.service) > 48
                or any(ord(c) < 32 or ord(c) == 127 or c in "()" for c in self.service)):
            raise ValueError("Descrição da porta inválida; use até 48 caracteres sem parênteses.")
        object.__setattr__(self, "service", self.service.strip())

    def to_dict(self):
        return {"protocol": self.protocol, "number": self.number, "service": self.service}

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, Mapping):
            raise ValueError("Porta inválida.")
        try:
            return cls(payload["protocol"], payload["number"], payload["service"])
        except KeyError:
            raise ValueError("Informe protocolo, número e descrição da porta.") from None


@dataclass(frozen=True)
class PortProfile:
    id: str
    name: str
    ports: tuple[ServicePort, ...]

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.id):
            raise ValueError("Identificador do perfil inválido.")
        if (not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 48
                or any(ord(c) < 32 or ord(c) == 127 for c in self.name)):
            raise ValueError("Nome do perfil inválido; use de 1 a 48 caracteres.")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.ports, (tuple, list)) or not 1 <= len(self.ports) <= MAX_PROFILE_PORTS:
            raise ValueError(f"Use de 1 a {MAX_PROFILE_PORTS} portas TCP por perfil.")
        if any(not isinstance(port, ServicePort) or port.protocol != "tcp" for port in self.ports):
            raise ValueError("Este perfil aceita somente TCP. UDP usa sondas específicas.")
        if len({port.number for port in self.ports}) != len(self.ports):
            raise ValueError("Remova as portas repetidas do perfil.")
        object.__setattr__(self, "ports", tuple(self.ports))

    def tcp_mapping(self):
        return {port.number: port.service for port in self.ports}

    def to_dict(self):
        return {"id": self.id, "name": self.name, "ports": [port.to_dict() for port in self.ports]}

    def ports_text(self):
        return "\n".join(f"{port.number} {port.service}" for port in self.ports)

    @classmethod
    def from_dict(cls, payload):
        if (not isinstance(payload, Mapping) or not isinstance(payload.get("ports"), (tuple, list))
                or not 1 <= len(payload["ports"]) <= MAX_PROFILE_PORTS):
            raise ValueError("Perfil de portas inválido.")
        return cls(payload.get("id"), payload.get("name"), tuple(ServicePort.from_dict(port) for port in payload["ports"]))

    @classmethod
    def from_text(cls, identifier, name, text):
        if not isinstance(text, str) or len(text) > 8192:
            raise ValueError("Lista de portas inválida ou muito longa.")
        ports = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.fullmatch(r"\s*([0-9]{1,5})(?:[ \t]+([^\r\n]+))?\s*", line)
            if not match:
                raise ValueError("Use uma porta por linha: 8088 Minha aplicação.")
            number = int(match[1])
            ports.append(ServicePort("tcp", number, (match[2] or f"TCP-{number}").strip()))
        return cls(identifier, name, tuple(ports))


def _profile(identifier, name, entries):
    return PortProfile(identifier, name, tuple(ServicePort("tcp", number, service) for number, service in entries))


STANDARD_PROFILE = _profile("standard", "Padrão", (
    (21, "FTP"), (22, "SSH"), (23, "Telnet"), (53, "DNS"), (80, "HTTP"), (443, "HTTPS"),
    (445, "SMB"), (5060, "SIP-VoIP"), (515, "LPD-Print"), (3389, "RDP"),
    (8080, "HTTP-Alt"), (8443, "HTTPS-Alt"), (9100, "RAW-Print"),
))
BUILTIN_PROFILES = (
    STANDARD_PROFILE,
    _profile("infrastructure", "Infraestrutura", (*STANDARD_PROFILE.tcp_mapping().items(),
             (179, "BGP"), (8291, "Winbox"), (8728, "RouterOS-API"), (8729, "RouterOS-API-TLS"))),
    _profile("cctv", "CFTV", ((80, "HTTP"), (443, "HTTPS"), (554, "RTSP"), (8000, "TCP-8000"),
             (8080, "HTTP-Alt"), (8443, "HTTPS-Alt"), (37777, "TCP-37777"))),
    _profile("printing", "Impressão", ((80, "HTTP"), (443, "HTTPS"), (515, "LPD-Print"), (631, "IPP"), (9100, "RAW-Print"))),
    _profile("servers", "Servidores", ((21, "FTP"), (22, "SSH"), (80, "HTTP"), (443, "HTTPS"), (445, "SMB"),
             (3389, "RDP"), (1433, "MSSQL"), (1521, "Oracle"), (3306, "MySQL"), (5432, "PostgreSQL"),
             (6379, "Redis"), (8080, "HTTP-Alt"), (8443, "HTTPS-Alt"))),
)
# Dedicated collectors own these protocols; they are never TCP profile entries.
UDP_SERVICES = (ServicePort("udp", 161, "SNMP"), ServicePort("udp", 137, "NetBIOS"),
                ServicePort("udp", 3702, "WS-Discovery"), ServicePort("udp", 5060, "SIP"), ServicePort("udp", 1900, "SSDP"))
