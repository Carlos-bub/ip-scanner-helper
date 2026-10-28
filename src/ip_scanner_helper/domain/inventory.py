"""Presentation rules for the inventory, independent of widgets and networking."""

from ipaddress import IPv4Address
import re
import unicodedata


def normalized(value):
    return "".join(char for char in unicodedata.normalize("NFD", str(value)).casefold()
                   if not unicodedata.combining(char))


def missing_name(device):
    name = normalized(device.get("nome", "")).strip()
    return name in ("", "dispositivo ativo", "nome nao encontrado", "desconhecido", "nao disponivel")


def missing_mac(device):
    return not re.fullmatch(r"(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}", str(device.get("mac", "")), re.I)


def unknown_category(device):
    return normalized(device.get("tipo", "")) in ("", "dispositivo nao identificado", "nao identificado")


def category_matches(device, category):
    kind = normalized(device.get("tipo", ""))
    rules = {
        "TODOS": True,
        "SWITCH": any(word in kind for word in ("switch", "roteador", "firewall", "access point")),
        "SERVIDOR": "servidor" in kind and "estacao" not in kind,
        "AD": "servidor" in kind,
        "ESTACAO": "estacao" in kind and "servidor" not in kind,
        "PRINTER": "impressora" in kind,
        "VOIP": "telefonia" in kind or "voip" in kind,
        "CFTV": any(word in kind for word in ("cftv", "camera", "dvr", "nvr")),
        "UNKNOWN": unknown_category(device),
    }
    return rules.get(category, True)


def matches_device(device, text="", category="TODOS", quality="Todos"):
    if not category_matches(device, category):
        return False
    if quality == "Sem nome" and not missing_name(device):
        return False
    if quality == "Sem MAC" and not missing_mac(device):
        return False
    if quality == "Categoria não identificada" and not unknown_category(device):
        return False
    haystack = normalized(" ".join(str(device.get(field, "")) for field in
                                   ("ip", "nome", "fabricante", "tipo", "mac", "origem", "portas", "dns_ptr")))
    return all(word in haystack for word in normalized(text).split())


def identity_source(device):
    source = str(device.get("origem", ""))
    key = normalized(source)
    if missing_name(device):
        return "Nome não obtido", "O equipamento respondeu, mas nenhum nome foi retornado pelas consultas."
    if "snmp" in key:
        return "Nome informado por SNMP", "Identificação declarada pelo equipamento via SNMP."
    if "dns" in key:
        return "Nome obtido por DNS", "Registro reverso da rede; pode estar desatualizado."
    if "netbios" in key:
        return "Nome obtido por NetBIOS", "Nome retornado pelo serviço de nomes do equipamento."
    if "web" in key:
        return "Título da interface Web", "O título da página pode ser genérico e não comprova um hostname."
    if "certificado" in key:
        return "Identificação do certificado", "Nome declarado no certificado; não comprova o hostname nem sua autenticidade."
    return "Identificação alternativa", "Modelo ou assinatura de serviço; não comprova um hostname."


def _sort_value(device, column):
    if column == "ip":
        try:
            return int(IPv4Address(device.get("ip", "")))
        except ValueError:
            return None
    if column == "latencia":
        value = device.get("latencia_ms")
        if isinstance(value, (int, float)):
            return value
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*ms", str(device.get("latencia", "")))
        return float(match.group(1).replace(",", ".")) if match else None
    return normalized(device.get(column, ""))


def sorted_devices(devices, column="ip", reverse=False):
    """Keep missing measurements last in both ascending and descending order."""
    known, missing = [], []
    for device in devices:
        value = _sort_value(device, column)
        (missing if value is None else known).append((value, device))
    known.sort(key=lambda item: item[0], reverse=reverse)
    return [device for _, device in known + missing]


def inventory_metrics(devices):
    return {"total": len(devices), "sem_nome": sum(missing_name(d) for d in devices),
            "sem_mac": sum(missing_mac(d) for d in devices),
            "sem_categoria": sum(unknown_category(d) for d in devices)}
