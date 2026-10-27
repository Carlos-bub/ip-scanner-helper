"""Device discovery orchestrated through an injected network probe."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
import time

from ip_scanner_helper.domain.oui_database import identificar_fabricante_e_tipo
from ip_scanner_helper.application.observations import ProbeRecorder, ScanCancelled
from ip_scanner_helper.application.ports import NetworkProbe
from ip_scanner_helper.domain.classification import classify_device
from ip_scanner_helper.domain.network_context import NetworkContext
from ip_scanner_helper.domain.port_profiles import PortProfile, STANDARD_PROFILE
from ip_scanner_helper.application.errors import ProbeTimeout, ScanIncomplete, TargetBudgetExceeded
from ip_scanner_helper.application.timing import DEFAULT_TIMEOUTS, ProbeContext, ScanTimeouts


@dataclass(frozen=True)
class ScanOptions:
    community: str = "public"
    workers: int = 32
    mode: str = "Completo"
    probe_metrics: bool = False
    timeouts: ScanTimeouts = DEFAULT_TIMEOUTS
    network_context: NetworkContext | None = None
    port_profile: PortProfile = STANDARD_PROFILE

    def __post_init__(self):
        if not isinstance(self.port_profile, PortProfile):
            raise ValueError("Perfil de portas inválido.")
        if not 1 <= self.workers <= 128:
            raise ValueError("Use entre 1 e 128 tarefas simultâneas.")
        if self.mode not in ("Rápido", "Completo"):
            raise ValueError("Modo de varredura inválido.")
        if not self.community.strip():
            raise ValueError("Informe a comunidade SNMP.")
        if not isinstance(self.probe_metrics, bool):
            raise ValueError("A opção de diagnóstico deve ser booleana.")
        if not isinstance(self.timeouts, ScanTimeouts):
            raise ValueError("Configuração de tempo inválida.")
        if self.network_context is not None and not isinstance(self.network_context, NetworkContext):
            raise ValueError("Contexto de rede inválido.")


def scan_device(ip: str, options: ScanOptions, cancelled: Event, arp_cache: dict, *,
                resolver: NetworkProbe, observer=None, on_discovery=None, clock=time.monotonic):
    with ProbeRecorder(cancelled, observer) as recorder:
        return _scan_device(ip, options, cancelled, arp_cache, recorder.call, on_discovery, resolver, clock)


def _scan_device(ip, options, cancelled, arp_cache, probe, on_discovery, resolver, clock):
    evidence, incomplete = [], {}
    published = False
    mac, latency = None, None
    ports, port_numbers = [], set()
    snmp_name = snmp_descr = snmp_source = dns = netbios = None
    pjl = onvif = sip = rdp = ssl_cn = web = ssh = ftp = ssdp = None
    budget = ProbeContext.target(options.timeouts.target_s, cancelled, clock=clock)
    completed_probes = set()
    record_probe = probe

    def probe(name, function, *args, **kwargs):
        context = budget.child(options.timeouts.budget(name, kwargs.get("ports", ())))
        kwargs["context"] = context
        if name != "arp":
            kwargs["timeout"] = getattr(options.timeouts, name)

        def collect():
            context.check()
            return function(*args, **kwargs)

        try:
            value = record_probe(name, collect)
            completed_probes.add(name)
            return value
        except ProbeTimeout as exc:
            incomplete[name] = "Limite por IP atingido" if isinstance(exc, TargetBudgetExceeded) else "Tempo de consulta excedido"
            if isinstance(exc, TargetBudgetExceeded) and exc.partial is None:
                raise
            return exc.partial if exc.partial is not None else {
                "arp": (None, False), "icmp": (False, None), "tcp": [],
                "snmp": (None, None, None), "http": (None, None), "tls": (None, None),
            }.get(name)

    def publish_presence():
        nonlocal published
        if published or not on_discovery or not evidence or cancelled.is_set():
            return
        partial_mac = mac or arp_cache.get(ip)
        vendor, _ = identificar_fabricante_e_tipo(partial_mac)
        on_discovery({"ip": ip, "nome": "Dispositivo ativo", "fabricante": vendor,
                      "tipo": "Dispositivo não identificado", "latencia": (
                          f"{latency:g} ms" if isinstance(latency, (float, int)) else latency or "Coletando…"),
                      "latencia_ms": latency if isinstance(latency, (float, int)) else None,
                      "mac": partial_mac or "Desconhecido", "origem_mac": (
                          "ARP atual" if mac else "Cache ARP; endereço não reconfirmado" if partial_mac else "Não disponível"),
                      "origem": "Detecção de presença", "confianca": "Baixa",
                      "evidencia_categoria": "Identificação em andamento", "evidencias": list(evidence),
                      "portas": "Coleta em andamento", "status": "Identificação em andamento",
                      "coleta_completa": False, "visto_em": datetime.now(timezone.utc).isoformat()})
        published = True

    try:
        mac, arp_active = probe("arp", resolver.obter_mac_e_presenca_windows, ip)
        if arp_active:
            evidence.append("ARP: resposta atual")
            publish_presence()
        ping_active, latency = probe("icmp", resolver.ping_measurement, ip)
        if ping_active:
            evidence.append("ICMP: resposta atual")
            publish_presence()
        ports = probe("tcp", resolver.scan_ports, ip, ports=options.port_profile.tcp_mapping(), cancel_event=cancelled)
        if ports:
            evidence.append("TCP: conexão aceita")
            publish_presence()
        port_numbers = {int(service.rsplit("(", 1)[1][:-1]) for service in ports}
        # Query UDP SNMP even if no TCP port or ICMP response exists.
        snmp_name, snmp_descr, snmp_source = probe(
            "snmp", resolver.query_snmp, ip, custom_community=options.community)
        if snmp_name or snmp_descr:
            evidence.append("SNMP: resposta atual")
            publish_presence()
        # The cache may enrich a confirmed host, but never proves current presence.
        if not evidence:
            if incomplete:
                raise ScanIncomplete("Presença não confirmada; coleta limitada pelo tempo disponível", incomplete)
            return None
        dns = probe("dns_ptr", resolver.query_dns_ptr, ip)
        netbios = probe("netbios", resolver.query_netbios, ip) if not dns else None
        if options.mode == "Completo":
            if 9100 in port_numbers:
                pjl = probe("pjl", resolver.query_pjl_printer_model, ip)
            if port_numbers & {80, 443, 8080, 8443}:
                onvif = probe("onvif", resolver.query_onvif_ws_discovery, ip)
                web, _ = probe("http", resolver.query_http_title, ip,
                               ports=tuple(p for p in (80, 8080, 8443, 443) if p in port_numbers))
            sip = probe("sip", resolver.query_sip_voip, ip)
            if 3389 in port_numbers:
                rdp = probe("rdp", resolver.query_rdp_hostname, ip)
            if 22 in port_numbers:
                ssh = probe("ssh", resolver.query_ssh_banner, ip)
            if 21 in port_numbers:
                ftp = probe("ftp", resolver.query_ftp_banner, ip)
            if port_numbers & {443, 8443}:
                ssl_cn, _ = probe("tls", resolver.query_ssl_certificate, ip,
                                  ports=tuple(p for p in (443, 8443) if p in port_numbers))
            if not snmp_name and not web:
                ssdp = probe("ssdp", resolver.query_ssdp_device, ip)
    except TargetBudgetExceeded:
        pass
    if cancelled.is_set():
        raise ScanCancelled()
    if not evidence:
        if incomplete:
            raise ScanIncomplete("Presença não confirmada; coleta limitada pelo tempo disponível", incomplete)
        return None
    mac_source = "ARP atual" if mac else "Não disponível"
    if not mac and ip in arp_cache:
        mac = arp_cache[ip]
        mac_source = "Cache ARP; endereço não reconfirmado"
    vendor, _ = identificar_fabricante_e_tipo(mac)
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
        "portas": " · ".join(ports) or (("Nenhuma porta TCP padrão respondeu" if options.port_profile.id == "standard"
                                        else "Nenhuma porta TCP do perfil respondeu") if "tcp" in completed_probes else "Consulta TCP incompleta"),
        "perfil_portas": {"id": options.port_profile.id, "nome": options.port_profile.name},
        "portas_previstas_tcp": [port.number for port in options.port_profile.ports],
        "origem": source, "confianca": confidence, "evidencia_categoria": reason,
        "evidencias": evidence, "status": (
            "Limite por IP atingido; identificação incompleta" if "Limite por IP atingido" in incomplete.values()
            else "Identificação incompleta; tempo de consulta excedido" if incomplete else "Confirmado nesta varredura"),
        "coleta_completa": not incomplete,
        **({"motivo_coleta_incompleta": "tempo", "sondas_incompletas": incomplete} if incomplete else {}),
        "visto_em": datetime.now(timezone.utc).isoformat(),
        "snmp_descr": snmp_descr or "Não disponível", "ssl_cn": rdp or ssl_cn or "Não disponível",
        "web_title": web or "Não disponível", "netbios_name": netbios or "Não disponível",
        "dns_ptr": dns or "Não disponível",
    }
