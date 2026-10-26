"""Package an explicit source allowlist and the already validated Windows build."""

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def main():
    destination = ROOT / "dist" / "portfolio"
    binary = destination / VERSION / "IP_Scanner_Helper"
    if not (binary / "IP_Scanner_Helper.exe").is_file():
        raise SystemExit("Gere e valide o executável antes de empacotar a versão.")
    (binary / "LEIA-ME.txt").write_text(
        f"IP Scanner Helper {VERSION}\n\n"
        "Extraia e mantenha esta pasta inteira, incluindo _internal.\n"
        "Abra IP_Scanner_Helper.exe para usar o inventário de rede.\n"
        "Demonstração sem sondagens: IP_Scanner_Helper.exe --demo\n"
        "Autoverificação: IP_Scanner_Helper.exe --self-check\n"
        "Logs: %LOCALAPPDATA%\\IPScannerHelper\\scanner.log\n",
        encoding="utf-8")
    source_zip = destination / f"IP_Scanner_Helper-{VERSION}-source.zip"
    binary_zip = destination / f"IP_Scanner_Helper-{VERSION}-windows.zip"
    files = [ROOT / name for name in ("README.md", "CHANGELOG.md", "pyproject.toml", ".gitignore",
             ".editorconfig", "main.py", "scanner_rede.py", "IP_Scanner_Helper.spec", "THIRD_PARTY_NOTICES.md")]
    for folder in ("core", "ui", "tests", "scripts", "docs", ".github"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts and path.suffix != ".pyc")
    with ZipFile(source_zip, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("IP_Scanner_Helper-source") / path.relative_to(ROOT))
    with ZipFile(binary_zip, "w", ZIP_DEFLATED) as archive:
        for path in sorted(binary.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(binary.parent))
    checksums = []
    for path in (source_zip, binary_zip):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.name}")
        print(f"{path.name}: {path.stat().st_size / 1024 / 1024:.1f} MB")
    (destination / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
