"""Evidence model shared by the desktop map and offline HTML export."""

from ipaddress import IPv4Address
import json
import math


def valid_ip(value):
    try:
        ip = IPv4Address(value)
        return str(ip) if not ip.is_multicast and not ip.is_unspecified and int(ip) != 0xFFFFFFFF else None
    except (ValueError, TypeError):
        return None


def build_topology_graph(devices, gateway=None):
    """FDB proves a learned path, never a direct cable or LLDP adjacency."""
    nodes = [{"id": "inventory", "nome": "Rede observada", "ip": "", "tipo": "Inventário",
              "color": "#0284c7", "detail": "Agrupamento lógico; conexões físicas não identificadas"}]
    edges = []
    addresses = {d["ip"] for d in devices if valid_ip(d.get("ip"))}
    for device in devices:
        ip = valid_ip(device.get("ip"))
        if not ip:
            continue
        kind = device.get("tipo", "Não identificado")
        color = "#0369a1" if "switch" in kind.lower() else "#475569"
        detail = "\n".join(f"{key}: {device.get(key, 'Não disponível')}" for key in
                           ("nome", "ip", "mac", "tipo", "fabricante", "latencia", "confianca"))
        observations = device.get("switch_observations", [])
        if observations:
            detail += "\n\nCaminhos observados (vínculo direto não confirmado):\n" + "\n".join(
                f"Switch {item.get('switch_ip', '?')} · porta {item.get('port', '?')}" for item in observations)
        nodes.append({"id": ip, "ip": ip, "nome": str(device.get("nome", ip)),
                      "tipo": str(kind), "color": color, "detail": detail})
        observed = False
        for observation in device.get("switch_observations", []):
            switch_ip = valid_ip(observation.get("switch_ip"))
            if switch_ip in addresses and switch_ip != ip:
                edges.append({"from": switch_ip, "to": ip, "observed": True,
                              "port": str(observation.get("port", "?")),
                              "label": f"MAC aprendido: {observation.get('port', '?')}; vínculo direto não confirmado"})
                observed = True
        if not observed:
            edges.append({"from": "inventory", "to": ip, "observed": False,
                          "label": "Conexão física desconhecida; agrupamento do inventário"})
    infrastructure = [node for node in nodes[1:] if any(word in node["tipo"].lower()
                       for word in ("switch", "roteador", "firewall", "access point"))]
    infrastructure_ids = {node["id"] for node in infrastructure}
    hosts = [node for node in nodes[1:] if node["id"] not in infrastructure_ids]
    columns = max(2, min(4, max(len(infrastructure), len(hosts), 1)))
    width, next_y = columns * 260, 190
    nodes[0].update(x=width / 2, y=60)
    for group in (infrastructure, hosts):
        if not group:
            continue
        group_columns = min(columns, len(group))
        for index, node in enumerate(group):
            node.update(x=width / 2 + (index % group_columns - (group_columns - 1) / 2) * 260,
                        y=next_y + index // group_columns * 110)
        next_y += math.ceil(len(group) / group_columns) * 110 + 45
    return {"nodes": nodes, "edges": edges, "gateway": valid_ip(gateway),
            "width": width, "height": max(450, next_y + 30)}


def safe_json(value):
    return (json.dumps(value, ensure_ascii=True).replace("&", "\\u0026")
            .replace("<", "\\u003c").replace(">", "\\u003e"))
