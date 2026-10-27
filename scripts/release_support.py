"""Shared paths and provenance checks for local Windows release tooling."""

import hashlib
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
PACKAGE = ROOT / "src" / "ip_scanner_helper"
SPEC = ROOT / "packaging" / "windows" / "IP_Scanner_Helper.spec"
BUILD = ROOT / "build" / "windows" / VERSION
DESTINATION = ROOT / "dist" / "portfolio"
BINARY = DESTINATION / VERSION / "IP_Scanner_Helper"
EXECUTABLE = BINARY / "IP_Scanner_Helper.exe"
VALIDATION = BUILD / "validated-build.json"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def application_fingerprint():
    """Hash runtime sources, resources, build configuration and project metadata."""
    paths = [ROOT / "pyproject.toml"]
    for folder in (PACKAGE, ROOT / "packaging"):
        paths.extend(path for path in folder.rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts and path.suffix != ".pyc")
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n")
                      if path.suffix in {".py", ".spec", ".toml", ".qml", ".html", ".json", ".js"}
                      else path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
