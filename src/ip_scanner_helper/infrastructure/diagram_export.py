"""Editable offline diagrams; membership never creates a network edge."""

from collections import defaultdict
import html
from ipaddress import IPv4Address
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from ip_scanner_helper.domain.topology import build_topology_graph


def _plain(value):
    # XML 1.0 excludes NUL, most control characters and lone surrogates.
    return "".join(char if (char in "\t\n\r" or 0x20 <= ord(char) <= 0xD7FF
                            or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)
                   else "\ufffd" for char in str(value))


def _quote(value):
    return '"' + (_plain(value).replace("\\", "\\\\").replace('"', '\\"')
                  .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace("\t", "    ")) + '"'


def _edge_caption(edge):
    if edge["kind"] == "reported_neighbor":
        return edge["source"] + " · " + edge["port"] + " → " + edge["remote_port"]
    return "FDB · " + edge["port"]


def render_dot(devices, gateway=None):
    graph = build_topology_graph(devices, gateway)
    nodes = {node["id"]: node for node in graph["nodes"]}
    label = ("Inventário · agrupamento lógico\nGateway informado: " + (graph["gateway"] or "Não informado")
             + "\nFDB: caminho aprendido; LLDP/CDP: vizinho reportado; vínculo físico direto não confirmado")
    lines = ["digraph inventory {", '  graph [charset="UTF-8", rankdir=TB, compound=true, labelloc=t, label=' + _quote(label) + "];",
             '  node [shape=box, style="rounded", fontname="Arial", fontsize=11];',
             '  edge [style=dashed, color="#557d80", fontname="Arial", fontsize=10, constraint=false];']
    for index, group in enumerate(graph["groupings"]["category"]):
        lines.append(f"  subgraph cluster_{index} {{")
        lines.append("    label=" + _quote(group["title"]) + '; color="#dce3e8";')
        for ip in group["member_ids"]:
            node = nodes[ip]
            lines.append("    " + _quote(ip) + " [label=" + _quote(node["nome"] + "\n" + ip + "\n" + node["tipo"])
                         + ", tooltip=" + _quote(node["detail"]) + ", color=" + _quote(node["color"]) + "];")
        lines.append("  }")
    external = sorted({edge["from"] for edge in graph["edges"] if not edge["source_in_inventory"]}, key=IPv4Address)
    for ip in external:
        lines.append("  " + _quote(ip) + " [label=" + _quote("Observador fora do inventário\n" + ip) + ', style="rounded,dashed"];')
    for edge in graph["edges"]:
        lines.append("  " + _quote(edge["from"]) + " -> " + _quote(edge["to"]) + " [label="
                     + _quote(_edge_caption(edge)) + ", tooltip="
                     + _quote(edge["label"] + "\n" + edge["source"] + " · " + edge["observed_at"])
                     + ", kind=" + _quote(edge["kind"])
                     + ", neighbor_status=" + _quote(edge.get("neighbor_status", "")) + "];")
    return "\n".join([*lines, "}", ""])


def diagram_groups_layout(groups, *, columns=3, width=640):
    """Export all members, using the maximum real height in each row."""
    result, y = [], 150
    for start in range(0, len(groups), columns):
        row = []
        for column, group in enumerate(groups[start:start + columns]):
            header = 140 if group.get("observer_ip") else 54
            height = header + math.ceil(len(group["member_ids"]) / 3) * 84 + 20
            row.append({"group": group, "x": 24 + column * (width + 24), "y": y,
                        "width": width, "height": height, "header": header})
        result.extend(row)
        y += max(item["height"] for item in row) + 24
    return result, max(500, y + 30)


def _geometry(cell, **values):
    return ET.SubElement(cell, "mxGeometry", {"as": "geometry", **{key: str(value) for key, value in values.items()}})


def _vertex(root, identifier, label, tooltip, kind, parent, x, y, width, height, *, color="#526577", ip="", style=""):
    metadata = ET.SubElement(root, "object", {"id": identifier, "label": _plain(label), "tooltip": html.escape(_plain(tooltip)),
                                            "kind": kind, "ip": ip})
    cell = ET.SubElement(metadata, "mxCell", {"vertex": "1", "parent": parent,
        "style": "rounded=1;whiteSpace=wrap;html=0;fillColor=#ffffff;fontColor=#243342;fontSize=12;strokeColor=" + color + ";" + style})
    _geometry(cell, x=x, y=y, width=width, height=height)
    return cell


def render_drawio(devices, gateway=None):
    graph = build_topology_graph(devices, gateway)
    nodes = {node["id"]: node for node in graph["nodes"]}
    document = ET.Element("mxfile", {"host": "app.diagrams.net", "agent": "IP Scanner Helper", "compressed": "false"})
    for mode, name in (("category", "Categorias"), ("switch", "Caminhos e vizinhos")):
        diagram = ET.SubElement(document, "diagram", {"id": mode, "name": name})
        placements, height = diagram_groups_layout(graph["groupings"][mode], columns=3 if mode == "category" else 2)
        model = ET.SubElement(diagram, "mxGraphModel", {"grid": "1", "gridSize": "10", "tooltips": "1", "fold": "1",
            "page": "0", "pageWidth": "2100", "pageHeight": str(height), "connect": "1", "arrows": "1"})
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", {"id": "0"})
        ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
        _vertex(root, "gateway-context", "Gateway informado: " + (graph["gateway"] or "Não informado")
                + "\nReferência da interface; sem ligação presumida", "Não estabelece presença nem relação física com os switches.",
                "gateway_context", "1", 24, 20, 640, 80, color="#316c5a")
        representations, members, observers = defaultdict(list), {}, {}
        for index, placement in enumerate(placements):
            group = placement["group"]
            group_id = "group-" + str(index)
            cell = _vertex(root, group_id, group["title"] + f" · {len(group['member_ids'])}", group["subtitle"],
                           "logical_group", "1", placement["x"], placement["y"], placement["width"], placement["height"],
                           color="#dce3e8", style="swimlane;startSize=40;collapsible=1;horizontal=1;")
            ET.SubElement(cell.find("mxGeometry"), "mxRectangle", {"as": "alternateBounds", "width": "640", "height": "50"})
            members[group_id] = {}
            if observer := group.get("observer_ip"):
                observer_id = group_id + "-observer"
                node = nodes.get(observer)
                label = (node["nome"] if node else "Observador fora do inventário") + "\n" + observer
                _vertex(root, observer_id, label, "Observador de caminhos/vizinhos; vínculo físico direto não confirmado.",
                        "device_reference" if node else "observer_reference", group_id, 16, 54, 608, 64, ip=observer, color="#356a78")
                observers[observer] = (group_id, observer_id)
                representations[observer].append(observer_id)
            for number, ip in enumerate(group["member_ids"]):
                node = nodes[ip]
                identifier = group_id + "-node-" + ip
                _vertex(root, identifier, node["nome"] + "\n" + ip + "\n" + node["tipo"], node["detail"],
                        "device" if mode == "category" else "device_reference", group_id,
                        16 + number % 3 * 208, placement["header"] + number // 3 * 84, 192, 64, ip=ip, color=node["color"])
                representations[ip].append(identifier)
                members[group_id][ip] = identifier
        for index, edge in enumerate(graph["edges"]):
            if mode == "switch":
                group_id, source = observers[edge["from"]]
                target = members[group_id][edge["to"]]
            else:
                if not representations[edge["from"]]:
                    identifier = "external-" + edge["from"]
                    _vertex(root, identifier, "Observador fora do inventário\n" + edge["from"], edge["label"],
                            "observer_reference", "1", 24, height, 320, 64, ip=edge["from"], style="dashed=1;")
                    representations[edge["from"]].append(identifier)
                    height += 84
                source, target = representations[edge["from"]][0], representations[edge["to"]][0]
            metadata = ET.SubElement(root, "object", {"id": "path-" + str(index), "label": _plain(_edge_caption(edge)),
                "tooltip": html.escape(_plain(edge["label"])), "kind": edge["kind"], "source": _plain(edge["source"]),
                "observed_at": _plain(edge["observed_at"]), "direct_link_confirmed": "false",
                "neighbor_status": edge.get("neighbor_status", ""), "remote_port": _plain(edge.get("remote_port", "")),
                "expires_at": "unknown"})
            cell = ET.SubElement(metadata, "mxCell", {"edge": "1", "parent": "1", "source": source, "target": target,
                "style": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=0;dashed=1;strokeColor=#557d80;fontSize=10;endArrow=open;"})
            _geometry(cell, relative=1)
    ET.indent(document)
    return ET.tostring(document, encoding="unicode", xml_declaration=True) + "\n"


def export_diagram(path, devices, gateway, kind):
    if kind not in ("drawio", "xml", "dot"):
        raise ValueError("Formato de diagrama inválido.")
    content = render_dot(devices, gateway) if kind == "dot" else render_drawio(devices, gateway)
    Path(path).write_text(content, encoding="utf-8", newline="\n")
