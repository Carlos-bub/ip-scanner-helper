"""Device categories inferred from explicit evidence, independent of collection."""

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


