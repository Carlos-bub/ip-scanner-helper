"""Generate reproducible public examples using fictitious inventory only."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.exporters import export_csv, export_json
from core.html_topology import gerar_html_topologia_interativa


def main():
    devices = json.loads((ROOT / "ui/assets/demo_inventory.json").read_text(encoding="utf-8"))
    output = ROOT / "docs"
    output.mkdir(exist_ok=True)
    (output / "demo-topology.html").write_text(gerar_html_topologia_interativa(devices, "192.0.2.1"), encoding="utf-8")
    export_csv(output / "demo-inventory.csv", devices)
    export_json(output / "demo-inventory.json", devices)
    print("Demonstrações fictícias geradas em docs/; nenhuma consulta de rede.")


if __name__ == "__main__":
    main()
