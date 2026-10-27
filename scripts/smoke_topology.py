"""Generate synthetic offline maps and exercise them in a local headless browser."""

import argparse
from ipaddress import IPv4Address
import json
from pathlib import Path
import shutil
import subprocess

from ip_scanner_helper.infrastructure.html_topology import gerar_html_topologia_interativa, render_example_topology
from ip_scanner_helper.resources import RESOURCE_ROOT

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    node = shutil.which("node")
    if not node:
        raise SystemExit("Instale Node.js 24 para executar este teste de navegador; o aplicativo não depende dele.")
    output = ROOT / "build" / "topology-smoke"
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    kinds = ("Switch", "Estação / Servidor", "Impressora", "CFTV", "Telefonia IP", "Dispositivo não identificado")
    for count in (0, 1, 10, 100, 500, 4096):
        devices = [{"ip": str(IPv4Address("10.0.0.1") + index), "nome": f"NODE-{index:05}",
                    "tipo": kinds[index % len(kinds)], "confianca": "Baixa", "origem": "Dados sintéticos"}
                   for index in range(count)]
        path = output / f"inventory-{count}.html"
        path.write_text(gerar_html_topologia_interativa(devices, "10.0.0.254"), encoding="utf-8")
        cases.append({"path": str(path), "count": count, "kind": "inventory"})
    for variant in ("large-group", "many-switches", "paths"):
        count = 4096 if variant != "paths" else 10
        devices = [{"ip": str(IPv4Address("10.0.0.1") + index), "nome": f"NODE-{index:05}", "tipo": "Impressora"}
                   for index in range(count)]
        if variant == "many-switches":
            for index, device in enumerate(devices):
                device["switch_observations"] = [{"switch_ip": str(IPv4Address("10.2.0.1") + index), "port": "24"}]
        if variant == "paths":
            devices[0]["tipo"] = devices[1]["tipo"] = "Switch"
            devices[-1]["nome"] = '</script><img src="https://invalid.example/x" onerror="globalThis.unsafe=true">'
            devices[-1]["switch_observations"] = [
                {"switch_ip": devices[0]["ip"], "port": "Gi1/0/4", "source": "SNMP sintético", "observed_at": "2026-10-27T12:00:00Z"},
                {"switch_ip": devices[1]["ip"], "port": "Gi1/0/8"},
                {"switch_ip": "192.0.2.254", "port": "24", "source": "Texto sintético"}]
        path = output / f"{variant}.html"
        path.write_text(gerar_html_topologia_interativa(devices, "10.0.0.254"), encoding="utf-8")
        cases.append({"path": str(path), "count": count, "kind": variant})
    demo = json.loads((RESOURCE_ROOT / "demo_inventory.json").read_text(encoding="utf-8"))
    demo.append(dict(demo[0], ip="192.0.2.3", nome="SW-LAB-02", mac="02:00:00:00:00:03"))
    demo[2]["switch_observations"].append({"switch_ip": "192.0.2.3", "port": "Gi1/0/2"})
    path = output / "demo.html"
    path.write_text(gerar_html_topologia_interativa(demo, "192.0.2.1"), encoding="utf-8")
    cases.append({"path": str(path), "count": len(demo), "kind": "demo"})
    sample = json.loads((RESOURCE_ROOT / "demo_topology.json").read_text(encoding="utf-8"))
    path = output / "example-tree.html"
    path.write_text(render_example_topology(), encoding="utf-8")
    cases.append({"path": str(path), "count": len(sample["nodes"]), "kind": "example-tree"})
    manifest = output / "cases.json"
    manifest.write_text(json.dumps(cases), encoding="utf-8")
    command = [node, str(ROOT / "scripts" / "smoke_topology.mjs"), str(manifest)]
    if args.capture:
        command.append("--capture")
    subprocess.run(command, check=True, timeout=120)


if __name__ == "__main__":
    main()
