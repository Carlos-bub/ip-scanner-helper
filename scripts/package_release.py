"""Package an explicit source allowlist and the already validated Windows build."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from release_support import (ROOT, VERSION, BINARY, EXECUTABLE, DESTINATION, VALIDATION,
                             application_fingerprint, sha256)


def public_source_file(path):
    relative = path.relative_to(ROOT)
    if any(part.endswith((".egg-info", ".dist-info")) for part in relative.parts):
        return False
    if relative.parts[:2] == ("docs", "melhorias"):
        return False
    if any(part in {"__pycache__", ".agents", ".codex", ".claude", ".cursor", ".continue", ".cline", ".windsurf", ".clinerules", ".windsurfrules"}
           or part.startswith(".aider") for part in relative.parts):
        return False
    if path.name in {"AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md", "CODEX.md", "GEMINI.md"}:
        return False
    if relative.parts[:1] == (".github",) and len(relative.parts) > 1:
        if relative.parts[1] in {"copilot-instructions.md", "instructions", "agents", "prompts", "skills"}:
            return False
    return path.suffix != ".pyc"


def main():
    destination = DESTINATION
    binary = BINARY
    if not EXECUTABLE.is_file() or not VALIDATION.is_file():
        raise SystemExit("Execute python scripts/build_windows.py antes de empacotar a versão.")
    report = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if (report.get("version") != VERSION or report.get("self_check") != "passed"
            or report.get("application_fingerprint") != application_fingerprint()
            or report.get("executable_sha256") != sha256(EXECUTABLE)):
        raise SystemExit("Build desatualizado ou não validado. Execute python scripts/build_windows.py.")
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
             ".editorconfig", ".gitattributes", "CONTRIBUTING.md", "THIRD_PARTY_NOTICES.md")]
    for folder in ("src", "tests", "scripts", "packaging", "docs", ".github"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file()
                     and public_source_file(path))
    with ZipFile(source_zip, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("IP_Scanner_Helper-source") / path.relative_to(ROOT))
    with ZipFile(binary_zip, "w", ZIP_DEFLATED) as archive:
        for path in sorted(binary.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(binary.parent))
    checksums = []
    for path in (source_zip, binary_zip):
        digest = sha256(path)
        checksums.append(f"{digest}  {path.name}")
        print(f"{path.name}: {path.stat().st_size / 1024 / 1024:.1f} MB")
    (destination / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
