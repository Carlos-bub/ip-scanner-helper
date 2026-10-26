"""Standalone map export shared by desktop frontends, without a GUI dependency."""

import html
from ip_scanner_helper.resources import RESOURCE_ROOT

from ip_scanner_helper.domain.topology import build_topology_graph, safe_json


def gerar_html_topologia_interativa(devices, gateway=None):
    graph = build_topology_graph(devices, gateway)
    template = (RESOURCE_ROOT / "templates/topology.html").read_text(encoding="utf-8")
    template = template.replace("__DEVICE_COUNT__", str(len(graph["nodes"]) - 1))
    template = template.replace("__GATEWAY__", html.escape(graph["gateway"] or "Não identificado"))
    return template.replace("__GRAPH_DATA__", safe_json(graph))
