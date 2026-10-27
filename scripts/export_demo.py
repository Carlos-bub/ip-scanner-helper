"""Generate reproducible public examples using fictitious inventory only."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

from ip_scanner_helper.resources import RESOURCE_ROOT
from ip_scanner_helper.infrastructure.exporters import export_csv, export_json
from ip_scanner_helper.infrastructure.html_topology import gerar_html_topologia_interativa, render_example_topology
from ip_scanner_helper.infrastructure.diagram_export import export_diagram


def main():
    devices = json.loads((RESOURCE_ROOT / "demo_inventory.json").read_text(encoding="utf-8"))
    output = ROOT / "docs"
    output.mkdir(exist_ok=True)
    (output / "demo-topology.html").write_text(gerar_html_topologia_interativa(devices, "192.0.2.1"), encoding="utf-8")
    (output / "demo-topology-tree.html").write_text(render_example_topology(), encoding="utf-8")
    export_csv(output / "demo-inventory.csv", devices)
    export_json(output / "demo-inventory.json", devices)
    for kind in ("drawio", "xml", "dot"):
        export_diagram(output / f"demo-topology.{kind}", devices, "192.0.2.1", kind)
    print("Demonstrações fictícias geradas em docs/; nenhuma consulta de rede.")


if __name__ == "__main__":
    main()
