"""Build and self-check a versioned Windows bundle using pyproject metadata."""

import argparse
from datetime import datetime, timezone
import json
import os
import subprocess
import sys

from release_support import (ROOT, VERSION, BUILD, DESTINATION, EXECUTABLE,
                             SPEC, VALIDATION, application_fingerprint, sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="Rebuild PyInstaller analysis cache")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("O build Windows precisa ser gerado no Windows.")
    BUILD.mkdir(parents=True, exist_ok=True)
    VALIDATION.unlink(missing_ok=True)
    fingerprint = application_fingerprint()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm",
               "--distpath", str(DESTINATION / VERSION), "--workpath", str(BUILD)]
    if args.clean:
        command.append("--clean")
    subprocess.run([*command, str(SPEC)], cwd=ROOT, check=True)
    subprocess.run([str(EXECUTABLE), "--self-check", "--log-dir", str(BUILD / "validation")],
                   cwd=BUILD, check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if application_fingerprint() != fingerprint:
        raise SystemExit("As fontes mudaram durante o build. Gere novamente antes de empacotar.")
    VALIDATION.write_text(json.dumps({
        "schema": 1, "version": VERSION, "self_check": "passed",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "application_fingerprint": fingerprint, "executable_sha256": sha256(EXECUTABLE),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Build {VERSION} e autoverificação aprovados: {EXECUTABLE}")


if __name__ == "__main__":
    main()
