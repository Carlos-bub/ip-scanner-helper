"""Explicit network identity and immutable facts captured for a scan session."""

from dataclasses import dataclass
import hashlib
from ipaddress import IPv4Address, IPv4Interface
import re
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from ip_scanner_helper.domain.interfaces import LocalInterface
from ip_scanner_helper.domain.targets import MAX_TARGETS, parse_targets


def _text(value, field, limit, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field} inválido.")
    return unicodedata.normalize("NFC", value.strip())


def _address(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} IPv4 inválido.")
    try:
        address = IPv4Address(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field} IPv4 inválido.") from None
    if address.is_multicast or address.is_unspecified or int(address) == 0xFFFFFFFF:
        raise ValueError(f"{field} IPv4 inválido.")
    return str(address)


@dataclass(frozen=True)
class NetworkContext:
    """A selected interface never establishes the identity or egress of a network.

    An explicit, confirmed environment identifier is required for reuse across
    sessions. A manual target may have no interface or environment at all.
    """

    target: str = ""
    environment_id: str | None = None
    environment_label: str = ""
    environment_confirmed: bool = False
    interface_id: str | None = None
    interface_name: str | None = None
    interface_address: str | None = None
    interface_prefix: int | None = None
    gateway: str | None = None

    def __post_init__(self):
        target = _text(self.target, "Alvo", 256)
        if target:
            parse_targets(target)
        object.__setattr__(self, "target", target)
        environment_id = _text(self.environment_id, "Identificador do ambiente", 128, optional=True)
        if environment_id is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", environment_id):
            raise ValueError("Identificador do ambiente inválido.")
        object.__setattr__(self, "environment_id", environment_id)
        object.__setattr__(self, "environment_label", _text(self.environment_label, "Nome do ambiente", 120))
        if not isinstance(self.environment_confirmed, bool) or (self.environment_confirmed and not environment_id):
            raise ValueError("Confirme um identificador explícito para o ambiente.")
        for key in ("interface_id", "interface_name"):
            object.__setattr__(self, key, _text(getattr(self, key), "Interface", 256, optional=True))
        interface_address = _address(self.interface_address, "Endereço da interface")
        prefix = self.interface_prefix
        if (interface_address is None) != (prefix is None):
            raise ValueError("Endereço e prefixo da interface devem ser informados juntos.")
        if prefix is not None and (isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= 32):
            raise ValueError("Prefixo IPv4 da interface inválido.")
        object.__setattr__(self, "interface_address", interface_address)
        object.__setattr__(self, "gateway", _address(self.gateway, "Gateway"))

    @staticmethod
    def named_environment_id(label):
        """Stable only for an exact, explicitly selected environment name.

        NFC handles equivalent Unicode encodings. Case and internal spacing
        remain significant to avoid merging distinct names automatically.
        """
        label = _text(label, "Nome do ambiente", 120)
        if not label:
            raise ValueError("Informe um nome exclusivo para o ambiente.")
        return str(uuid5(NAMESPACE_URL, "ip-scanner-helper:network-environment:v1:" + label))

    @classmethod
    def for_scan(cls, target, interface: LocalInterface | None = None, *, environment_id=None,
                 environment_label="", environment_confirmed=False):
        if interface is not None and not isinstance(interface, LocalInterface):
            raise ValueError("Interface de rede inválida.")
        if environment_confirmed and environment_id is None and environment_label:
            environment_id = cls.named_environment_id(environment_label)
        return cls(
            target=target, environment_id=environment_id, environment_label=environment_label,
            environment_confirmed=environment_confirmed,
            interface_id=(interface.adapter_id or None) if interface is not None else None,
            interface_name=interface.name if interface is not None else None,
            interface_address=interface.address if interface is not None else None,
            interface_prefix=interface.prefix if interface is not None else None,
            gateway=interface.gateway if interface is not None else None,
        )

    def snapshot(self, session_id, targets):
        """Plain metadata, scoped to actual targets; includes no scan credentials."""
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", session_id):
            raise ValueError("Identificador da sessão inválido.")
        targets = tuple(targets)
        if not 1 <= len(targets) <= MAX_TARGETS:
            raise ValueError(f"Use entre 1 e {MAX_TARGETS} alvos por sessão.")
        addresses = {_address(value, "Alvo") for value in targets}
        if None in addresses:
            raise ValueError("Alvo IPv4 inválido.")
        canonical = sorted(addresses, key=IPv4Address)
        if self.target and set(parse_targets(self.target)) != set(canonical):
            raise ValueError("O contexto não corresponde aos alvos da sessão.")
        target_scope = hashlib.sha256("\n".join(canonical).encode("ascii")).hexdigest()
        reusable = self.environment_confirmed and self.environment_id is not None
        return {
            "schema_version": 1,
            "environment_id": self.environment_id,
            "environment_label": self.environment_label,
            "environment_confirmed": self.environment_confirmed,
            "target_expression": self.target,
            "target_scope": target_scope,
            "target_count": len(targets),
            "interface": {
                "adapter_id": self.interface_id, "name": self.interface_name,
                "address": self.interface_address, "prefix": self.interface_prefix,
                "network": str(IPv4Interface(f"{self.interface_address}/{self.interface_prefix}").network)
                if self.interface_address is not None else None,
                "gateway": self.gateway,
            },
            "routing": "system",
            "comparison_scope": f"environment:{self.environment_id}:{target_scope}" if reusable else f"session:{session_id}",
            "environment_reusable": reusable,
        }
