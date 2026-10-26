"""Network discovery independent of Tk, with evidence-based classification."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event

from core.oui_database import identificar_fabricante_e_tipo
from core.resolver import NetworkResolver


@dataclass(frozen=True)
class ScanOptions:
    community: str = "public"
    workers: int = 32
    mode: str = "Completo"

    def __post_init__(self):
        if not 1 <= self.workers <= 128:
            raise ValueError("Use entre 1 e 128 tarefas simultâneas.")
        if self.mode not in ("Rápido", "Completo"):
            raise ValueError("Modo de varredura inválido.")
        if not self.community.strip():
            raise ValueError("Informe a comunidade SNMP.")


class ScanCancelled(Exception):
    """Cooperative cancellation between bounded network operations."""


def classify_device(description, ports, pjl=None, onvif=None, sip=None):
    """A vendor, DNS suffix or RDP certificate does not establish a device role."""
    text = (description or "").lower()
    if pjl or any(word in text for word in ("printer", "jetdirect", "impressora")):
        return "Impressora", "Alta", "Modelo PJL ou descrição SNMP"
    if onvif:
        return "CFTV", "Alta", "Resposta ONVIF"
    if sip:
        return "Telefonia IP", "Alta", "Resposta SIP"
    if any(word in text for word in ("switch", "procurve", "swos")):
        return "Switch", "Alta", "Descrição SNMP"
    if any(word in text for word in ("router", "routeros", "firewall")):
        return "Roteador / Firewall", "Alta", "Descrição SNMP"
    if any(word in text for word in ("access point", "wireless ap")):
        return "Access Point / Wi-Fi", "Alta", "Descrição SNMP"
    if 9100 in ports or 515 in ports:
        return "Impressora", "Média", "Serviço de impressão TCP"
    if 3389 in ports or 445 in ports:
        return "Estação / Servidor", "Baixa", "Serviços RDP/SMB; função não confirmada"
    return "Dispositivo não identificado", "Baixa", "Evidências insuficientes para definir categoria"


def scan_device(ip: str, options: ScanOptions, cancelled: Event, arp_cache: dict):
    def probe(function, *args, **kwargs):
        if cancelled.is_set():
            raise ScanCancelled()
        return function(*args, **kwargs)

    resolver = NetworkResolver
    mac, arp_active = probe(resolver.obter_mac_e_presenca_windows, ip)
    ping_active, latency = probe(resolver.ping_measurement, ip)
    ports = probe(resolver.scan_ports, ip, cancel_event=cancelled)
    port_numbers = {int(service.rsplit("(", 1)[1][:-1]) for service in ports}
    # Query UDP SNMP even if no TCP port or ICMP response exists.
    snmp_name, snmp_descr, snmp_source = probe(
        resolver.query_snmp, ip, custom_community=options.community)
    evidence = []
    if arp_active:
        evidence.append("ARP: resposta atual")
    if ping_active:
        evidence.append("ICMP: resposta atual")
    if ports:
        evidence.append("TCP: conexão aceita")
    if snmp_name or snmp_descr:
        evidence.append("SNMP: resposta atual")
    # The cache may enrich a confirmed host, but never proves current presence.
    if not evidence:
        return None
    mac_source = "ARP atual" if mac else "Não disponível"
    if not mac and ip in arp_cache:
        mac = arp_cache[ip]
        mac_source = "Cache ARP; endereço não reconfirmado"
    vendor, _ = identificar_fabricante_e_tipo(mac)
    dns = probe(resolver.query_dns_ptr, ip)
    netbios = probe(resolver.query_netbios, ip) if not dns else None
    pjl = onvif = sip = rdp = ssl_cn = web = ssh = ftp = ssdp = None
    if options.mode == "Completo":
        if 9100 in port_numbers:
            pjl = probe(resolver.query_pjl_printer_model, ip)
        if port_numbers & {80, 443, 8080, 8443}:
            onvif = probe(resolver.query_onvif_ws_discovery, ip)
            web, _ = probe(resolver.query_http_title, ip,
                           ports=tuple(p for p in (80, 8080, 8443, 443) if p in port_numbers))
        sip = probe(resolver.query_sip_voip, ip)
        if 3389 in port_numbers:
            rdp = probe(resolver.query_rdp_hostname, ip)
        if 22 in port_numbers:
            ssh = probe(resolver.query_ssh_banner, ip)
        if 21 in port_numbers:
            ftp = probe(resolver.query_ftp_banner, ip)
        if port_numbers & {443, 8443}:
            ssl_cn, _ = probe(resolver.query_ssl_certificate, ip,
                              ports=tuple(p for p in (443, 8443) if p in port_numbers))
        if not snmp_name and not web:
            ssdp = probe(resolver.query_ssdp_device, ip)
    kind, confidence, reason = classify_device(snmp_descr, port_numbers, pjl, onvif, sip)
    candidates = [(snmp_name, snmp_source), (dns, "DNS reverso (PTR)"),
                  (netbios, "NetBIOS"), (rdp, "Certificado RDP"), (web, "Título Web"),
                  (pjl, "Modelo PJL"), (onvif, "ONVIF"), (sip, "SIP"),
                  (ssdp, "SSDP"), (ssl_cn, "Certificado TLS"),
                  (ssh, "Banner SSH"), (ftp, "Banner FTP")]
    name, source = next(((value, origin) for value, origin in candidates if value),
                        ("Dispositivo ativo", "Detecção de presença"))
    if cancelled.is_set():
        raise ScanCancelled()
    return {
        "ip": ip, "nome": name, "fabricante": vendor, "tipo": kind,
        "latencia": (f"{latency:g} ms" if isinstance(latency, (float, int))
                     else latency or "Não medida"),
        "latencia_ms": latency if isinstance(latency, (float, int)) else None,
        "mac": mac or "Desconhecido", "origem_mac": mac_source,
        "portas": " · ".join(ports) or "Nenhuma porta TCP padrão respondeu",
        "origem": source, "confianca": confidence, "evidencia_categoria": reason,
        "evidencias": evidence, "status": "Confirmado nesta varredura",
        "visto_em": datetime.now(timezone.utc).isoformat(),
        "snmp_descr": snmp_descr or "Não disponível", "ssl_cn": rdp or ssl_cn or "Não disponível",
        "web_title": web or "Não disponível", "netbios_name": netbios or "Não disponível",
        "dns_ptr": dns or "Não disponível",
    }
