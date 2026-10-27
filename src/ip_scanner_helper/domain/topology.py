"""Inventory relationships and logical memberships, independent of positions."""

from collections.abc import Mapping
from enum import Enum
from ipaddress import IPv4Address
import json

from ip_scanner_helper.domain.inventory import normalized


class RelationKind(str, Enum):
    LOGICAL_GROUP = "logical_group"
    FDB_PATH = "fdb_path"
    # Reserved for a future collector. FDB never produces this kind.
    REPORTED_NEIGHBOR = "reported_neighbor"


CATEGORIES = (
    ("infrastructure", "Infraestrutura", "network", "#356a78"),
    ("servers", "Servidores", "server", "#4e6e5d"),
    ("workstations", "Estações", "computer", "#526577"),
    ("workstations_servers", "Estações / servidores", "computer", "#526577"),
    ("printers", "Impressoras", "printer", "#896b46"),
    ("cctv", "CFTV", "camera", "#8b5d60"),
    ("voip", "Telefonia IP", "phone", "#7c7650"),
    ("other", "Outras categorias", "device", "#666b78"),
    ("unknown", "Não identificados", "device", "#727b88"),
)


def valid_ip(value):
    if not isinstance(value, str):
        return None
    try:
        ip = IPv4Address(value)
        return str(ip) if not ip.is_multicast and not ip.is_unspecified and int(ip) != 0xFFFFFFFF else None
    except ValueError:
        return None


def _category(kind):
    text = normalized(kind)
    if any(word in text for word in ("switch", "roteador", "firewall", "access point")):
        return "infrastructure"
    if "estacao" in text:
        return "workstations_servers" if "servidor" in text else "workstations"
    if "servidor" in text:
        return "servers"
    if "impressora" in text:
        return "printers"
    if any(word in text for word in ("cftv", "camera", "dvr", "nvr")):
        return "cctv"
    if any(word in text for word in ("telefonia", "voip")):
        return "voip"
    return "unknown" if text in ("", "nao identificado", "dispositivo nao identificado") else "other"


def build_topology_graph(devices, gateway=None):
    """Keep every learned path without inventing a parent, cable, or gateway link."""
    records = {}
    for device in devices:
        if isinstance(device, Mapping) and (ip := valid_ip(device.get("ip"))):
            records.setdefault(ip, device)
    addresses = sorted(records, key=IPv4Address)
    categories = {item[0]: item for item in CATEGORIES}
    nodes, edges, seen = [], [], set()
    gateway = valid_ip(gateway)
    for ip in addresses:
        device = records[ip]
        kind = str(device.get("tipo") or "Dispositivo não identificado")
        category = _category(kind)
        _, _, icon, color = categories[category]
        if any(word in normalized(kind) for word in ("roteador", "firewall")):
            icon = "router"
        elif "access point" in normalized(kind):
            icon = "wifi"
        detail = "\n".join(f"{key}: {device.get(key, 'Não disponível')}" for key in (
            "nome", "ip", "mac", "tipo", "fabricante", "latencia", "origem", "confianca",
            "evidencia_categoria", "status", "visto_em"))
        observations = device.get("switch_observations", [])
        if not isinstance(observations, (list, tuple)):
            observations = []
        for observation in observations:
            if not isinstance(observation, Mapping):
                continue
            switch_ip = valid_ip(observation.get("switch_ip"))
            if not switch_ip or switch_ip == ip:
                continue
            port = str(observation.get("port") or "Porta não registrada")
            origin = str(observation.get("source") or "Origem da observação não registrada")
            stamp = str(observation.get("observed_at") or "Instante não registrado")
            key = (switch_ip, ip, port, origin, stamp)
            if key in seen:
                continue
            seen.add(key)
            edge = {"kind": RelationKind.FDB_PATH.value, "from": switch_ip, "to": ip,
                    "observed": True, "source_in_inventory": switch_ip in records,
                    "port": port, "source": origin, "observed_at": stamp,
                    "direct_link_confirmed": False,
                    "label": f"MAC aprendido em {switch_ip} · {port}; vínculo direto não confirmado"}
            edges.append(edge)
        nodes.append({"id": ip, "ip": ip, "nome": str(device.get("nome") or ip),
                      "tipo": kind, "category": category, "icon": icon, "color": color,
                      "detail": detail, "is_gateway": ip == gateway,
                      "state": "partial" if device.get("coleta_completa") is False else "observed",
                      "origem": str(device.get("origem") or "Não disponível"),
                      "confianca": str(device.get("confianca") or "Não disponível")})

    category_groups = []
    for key, title, icon, color in CATEGORIES:
        members = [node["id"] for node in nodes if node["category"] == key]
        if members:
            category_groups.append({"id": "category:" + key, "kind": RelationKind.LOGICAL_GROUP.value,
                                    "title": title, "subtitle": "Agrupamento pela categoria do inventário",
                                    "icon": icon, "color": color, "member_ids": members, "context_ids": []})
    by_source, mapped = {}, set()
    for edge in edges:
        by_source.setdefault(edge["from"], set()).add(edge["to"])
        mapped.add(edge["to"])
    switch_groups = []
    for switch_ip in sorted(by_source, key=IPv4Address):
        source = records.get(switch_ip)
        name = str(source.get("nome") or switch_ip) if source else switch_ip
        switch_groups.append({"id": "switch:" + switch_ip, "kind": RelationKind.LOGICAL_GROUP.value,
                              "title": "Vistos por " + name,
                              "subtitle": switch_ip + (" · Caminhos FDB" if source else " · Fora do inventário"),
                              "icon": "network", "color": "#356a78",
                              "observer_ip": switch_ip,
                              "member_ids": sorted(by_source[switch_ip], key=IPv4Address),
                              "context_ids": [switch_ip] if source else []})
    unmapped = [ip for ip in addresses if ip not in mapped]
    if unmapped:
        switch_groups.append({"id": "switch:unmapped", "kind": RelationKind.LOGICAL_GROUP.value,
                              "title": "Sem caminho FDB", "subtitle": "Nenhuma associação registrada nesta coleta",
                              "icon": "device", "color": "#727b88", "member_ids": unmapped, "context_ids": []})
    return {"nodes": nodes, "edges": edges, "gateway": gateway,
            "groupings": {"category": category_groups, "switch": switch_groups}}


def safe_json(value):
    return (json.dumps(value, ensure_ascii=True).replace("&", "\\u0026")
            .replace("<", "\\u003c").replace(">", "\\u003e"))
