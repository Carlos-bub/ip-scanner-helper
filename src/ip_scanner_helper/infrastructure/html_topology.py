"""Standalone map export shared by desktop frontends, without a GUI dependency."""

import json
from ip_scanner_helper.resources import RESOURCE_ROOT

from ip_scanner_helper.domain.topology import build_topology_graph, safe_json


def gerar_html_topologia_interativa(devices, gateway=None):
    graph = build_topology_graph(devices, gateway)
    return render_topology_html(graph)


def render_topology_html(graph):
    template = (RESOURCE_ROOT / "templates/topology.html").read_text(encoding="utf-8")
    for name in ("topology-layout", "topology-map"):
        script = (RESOURCE_ROOT / f"templates/{name}.js").read_text(encoding="utf-8")
        template = template.replace("__" + name.upper().replace("-", "_") + "__", script)
    return template.replace("__GRAPH_DATA__", safe_json(graph))


def render_example_topology():
    """Explicit fictional hierarchy. Never merged with a collected inventory."""
    sample = json.loads((RESOURCE_ROOT / "demo_topology.json").read_text(encoding="utf-8"))
    graph = build_topology_graph(sample["nodes"], sample["gateway"])
    states = {node["ip"]: node["state"] for node in sample["nodes"]}
    for node in graph["nodes"]:
        node["state"] = states[node["id"]]
        node["detail"] = node["nome"] + "\n" + node["ip"] + "\nDados fictícios; estado e hierarquia definidos no JSON de exemplo."
    graph["example"] = True
    graph["tree_links"] = [{**link, "kind": "example_link", "port": "Exemplo", "source": "JSON fictício",
                             "observed_at": "Demonstração", "label": "Relação do exemplo; não coletada da rede"}
                            for link in sample["links"]]
    return render_topology_html(graph)
