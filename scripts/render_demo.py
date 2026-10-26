"""Optional developer helper: render the fictitious HTML example with local Edge."""

from pathlib import Path
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    candidates = [Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
                  Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))]
    edge = next((base / "Microsoft/Edge/Application/msedge.exe" for base in candidates
                 if (base / "Microsoft/Edge/Application/msedge.exe").exists()), None)
    if edge is None:
        raise SystemExit("Microsoft Edge não encontrado. Abra docs/demo-topology.html manualmente.")
    profile = ROOT / "build" / "edge-demo-profile"
    profile.mkdir(parents=True, exist_ok=True)
    screenshot = ROOT / "docs" / "demo-map.png"
    result = subprocess.run([
        str(edge), "--headless", "--disable-gpu", "--no-first-run", "--disable-background-networking",
        f"--user-data-dir={profile}", f"--screenshot={screenshot}", "--window-size=1440,1000",
        "--virtual-time-budget=1200", "--dump-dom", (ROOT / "docs/demo-topology.html").as_uri(),
    ], capture_output=True, timeout=30)
    dom = result.stdout.decode("utf-8", errors="replace")
    if result.returncode != 0 or not screenshot.exists() or len(re.findall(r'<g class="node"', dom)) != 7:
        raise SystemExit("Falha ao renderizar o mapa; confira o HTML e a instalação do Edge.")
    print("Mapa renderizado: 6 equipamentos e agrupamento lógico; screenshot em docs/demo-map.png.")


if __name__ == "__main__":
    main()
