"""Conservative device classification from independent, traceable evidence.

Ports describe services and an OUI describes an adapter vendor. Neither proves
a device's role. The public tuple is kept compatible with inventory snapshots.
"""

from dataclasses import dataclass
import re


UNKNOWN = "Dispositivo não identificado"

SERVER_DESCRIPTIONS = (
    "windows server", "ubuntu server", "proxmox", "vmware esxi", "esxi",
    "hyper-v", "truenas", "freenas", "synology", "qnap", "idrac", "ilo",
    # 9600 is shared by Windows client and Server; it cannot establish a role.
    "build 20348",
)
WORKSTATION_DESCRIPTIONS = (
    "windows 10", "windows 11", "workstation",
    # 19041/19042 are shared with Server releases; retain explicit client builds.
    "build 19043", "build 19044", "build 19045",
    "build 22000", "build 22621", "build 22631",
)
SERVER_WEB_TITLES = (
    "proxmox", "vmware esxi", "vsphere", "idrac", "integrated lights-out",
    "hpe ilo", "synology", "diskstation", "truenas", "freenas", "qnap",
    "windows admin center", "iis windows server",
)
PRINTER_TEXT = (
    "printer", "jetdirect", "impressora", "laserjet", "officejet", "deskjet",
    "ecotank", "brother", "kyocera", "ricoh", "lexmark", "xerox", "epson",
)
CCTV_TEXT = (
    "dvr", "nvr", "cftv", "hikvision", "dahua", "ip camera", "network camera",
    "netcamera", "axis camera", "axis communications",
)
VOIP_TEXT = (
    "telefone ip", "ip phone", "voip", "yealink", "polycom", "fanvil",
    "audiocodes", "issabel", "freepbx", "3cx",
)
SWITCH_TEXT = ("switch", "procurve", "swos", "edgeswitch")
ROUTER_TEXT = (
    "router", "routeros", "mikrotik", "webfig", "pfsense", "opnsense",
    "fortigate", "fortios", "sonicwall", "archer",
)
AP_TEXT = ("access point", "wireless ap", "airmax", "wireless access point")

DEVICE_SIGNATURES = (
    ("Impressora", PRINTER_TEXT),
    ("CFTV", CCTV_TEXT),
    ("Telefonia IP", VOIP_TEXT),
    ("Switch", SWITCH_TEXT),
    ("Roteador / Firewall", ROUTER_TEXT),
    ("Access Point / Wi-Fi", AP_TEXT),
)


def _hostname_pattern(prefixes):
    # Abbreviations must be an entire component or followed by a numeric ID:
    # AD01/SRV-ARQUIVOS are conventions; ADMIN/APPLE are ordinary words.
    return re.compile(r"(?:^|[-_])(?:" + prefixes + r")(?:[0-9][a-z0-9]*)?(?=$|[-_])")


HOSTNAME_RULES = (
    (re.compile(r"(?:^|[-_])(?:npi|brn|brw)[0-9a-f]{4,}(?=$|[-_])"), "Impressora"),
    (_hostname_pattern("imp|prn|printer|laserjet|epson"), "Impressora"),
    (_hostname_pattern("cam|ipc|dvr|nvr|cftv|hikvision|dahua"), "CFTV"),
    (_hostname_pattern("sip|voip|ramal|yealink|grandstream|pabx"), "Telefonia IP"),
    (_hostname_pattern("sw|switch|procurve|aruba"), "Switch"),
    (_hostname_pattern("rt|rtr|router|gw|gateway|fw|firewall|mikrotik|pfsense|fortigate"), "Roteador / Firewall"),
    (_hostname_pattern("ap|uap|unifi|wifi|wlan"), "Access Point / Wi-Fi"),
    (_hostname_pattern("srv|server|dc|ad|sql|db|fs|fileserver|pve|esxi|hyperv|nas|truenas|synology"), "Servidor"),
    (_hostname_pattern("desktop|laptop|win|macbook|imac|pc|nb|note|notebook|wks|workstation|estacao|micro|pdv|caixa"), "Estação"),
)


@dataclass(frozen=True)
class _Evidence:
    category: str
    strength: int
    reason: str


def _signature(text, signatures):
    """Match complete words/phrases: 'ilo' must never match 'pilot'."""
    for signature in signatures:
        if re.search(r"(?<!\w)" + re.escape(signature) + r"(?!\w)", text):
            return signature
    return None


def _resolve(evidence):
    if not evidence:
        return None
    strongest = max(item.strength for item in evidence)
    winners = [item for item in evidence if item.strength == strongest]
    categories = sorted({item.category for item in winners})
    reasons = "; ".join(dict.fromkeys(item.reason for item in winners))
    if len(categories) > 1:
        return UNKNOWN, "Baixa", "Evidências contraditórias: " + reasons
    return categories[0], "Alta" if strongest == 2 else "Média", reasons


def classify_device(description, ports, pjl=None, onvif=None, sip=None, *,
                    ssh=None, web=None, ftp=None, ssdp=None, netbios=None,
                    dns=None, name=None, vendor=None):
    """Return category, qualitative confidence and the actual winning evidence.

    ``name`` is a hostname (e.g. SNMP sysName), never a display label, Web title,
    model or arbitrary certificate text. Generic OS/SSH/FTP banners, vendor,
    PTR registration and open ports do not establish server/workstation roles.
    """
    evidence = []

    def add(category, strength, reason):
        evidence.append(_Evidence(category, strength, reason))

    def signatures(value, source, groups):
        text = (value or "").casefold()
        for category, patterns in groups:
            matched = _signature(text, patterns)
            if matched:
                add(category, 2, f'{source}: assinatura "{matched}" ({category})')

    signatures(description, "Descrição SNMP", DEVICE_SIGNATURES + (
        ("Servidor", SERVER_DESCRIPTIONS), ("Estação", WORKSTATION_DESCRIPTIONS),
    ))
    signatures(web, "Título Web", DEVICE_SIGNATURES + (("Servidor", SERVER_WEB_TITLES),))
    # Distribution names and generic FTP products identify software, not roles.
    for value, source in ((ssh, "Banner SSH"), (ftp, "Banner FTP")):
        signatures(value, source, (
            ("Servidor", ("proxmox", "vmware esxi", "truenas", "freenas")),
            ("Switch", ("cisco switch", "swos", "edgeswitch")),
            ("Roteador / Firewall", ("routeros", "pfsense", "opnsense", "fortigate", "fortios")),
        ))
    if pjl:
        add("Impressora", 2, "Resposta do protocolo PJL: equipamento de impressão")
    if onvif:
        add("CFTV", 2, "Resposta ONVIF: equipamento de vídeo")
    if sip:
        add("Telefonia IP", 1, "Resposta SIP: função de telefonia; tipo físico não confirmado")
    if _signature((ssdp or "").casefold(), ("smart tv", "tizen", "webos", "roku")):
        add("IoT / Smart TV", 1, "Resposta SSDP de Smart TV ou mídia")

    for raw_name, source in ((name, "Hostname SNMP"), (netbios, "NetBIOS"), (dns, "DNS reverso (PTR)")):
        hostname = (raw_name or "").strip().casefold().rstrip(".")
        if not re.fullmatch(r"[a-z0-9_][a-z0-9_.-]{0,252}", hostname):
            continue
        host = hostname.split(".", 1)[0]
        for pattern, category in HOSTNAME_RULES:
            if pattern.search(host):
                add(category, 1, f'{source}: convenção de nome "{host}" ({category})')

    resolved = _resolve(evidence)
    if resolved:
        return resolved
    if ports:
        return UNKNOWN, "Baixa", "Portas TCP abertas não confirmam o tipo ou a função do equipamento"
    if vendor:
        return UNKNOWN, "Baixa", "Fabricante pelo MAC não confirma o tipo ou a função do equipamento"
    return UNKNOWN, "Baixa", "Evidências insuficientes para definir categoria"
