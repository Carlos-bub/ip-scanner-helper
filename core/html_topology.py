"""Standalone map export shared by desktop frontends, without a GUI dependency."""

import html
from pathlib import Path

from core.topology import build_topology_graph, safe_json


def gerar_html_topologia_interativa(devices, gateway=None):
    graph = build_topology_graph(devices, gateway)
    template = (Path(__file__).resolve().parents[1] / "ui/assets/topology.html").read_text(encoding="utf-8")
    template = template.replace("__DEVICE_COUNT__", str(len(graph["nodes"]) - 1))
    template = template.replace("__GATEWAY__", html.escape(graph["gateway"] or "Não identificado"))
    return template.replace("__GRAPH_DATA__", safe_json(graph))
