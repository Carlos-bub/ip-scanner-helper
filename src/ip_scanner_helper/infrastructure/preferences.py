"""Versioned JSON preferences with atomic replacement and recoverable failures."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from ip_scanner_helper.domain.preferences import Preferences

SCHEMA_VERSION = 1
MAX_SETTINGS_BYTES = 64 * 1024


def default_settings_path():
    """Resolve the user location without reading or creating any directories."""
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / ".local" / "share") / "IPScannerHelper" / "settings.json"


class JsonPreferencesStore:
    def __init__(self, path):
        self.path = Path(path)
        self.read_only = False
        self.message = ""
        self.recovered_path = None

    def _read(self):
        with self.path.open("rb") as source:
            data = source.read(MAX_SETTINGS_BYTES + 1)
        if len(data) > MAX_SETTINGS_BYTES:
            raise ValueError("Arquivo de preferências excede o limite.")
        payload = json.loads(data.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Estrutura de preferências inválida.")
        version = payload.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("Versão de preferências inválida.")
        return payload

    def _recover(self):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = self.path.with_name(f"{self.path.stem}.invalid-{stamp}-{uuid4().hex[:8]}{self.path.suffix}")
        try:
            os.replace(self.path, backup)
        except OSError:
            self.read_only = True
            self.message = "Preferências inválidas; não foi possível preservar o arquivo. Usando os padrões sem sobrescrevê-lo."
        else:
            self.recovered_path = backup
            self.message = "Preferências inválidas foram preservadas em um backup. Os valores padrão foram carregados."

    def load(self):
        self.read_only, self.message, self.recovered_path = False, "", None
        try:
            payload = self._read()
        except FileNotFoundError:
            return Preferences()
        except (ValueError, UnicodeError, RecursionError):
            self._recover()
            return Preferences()
        except OSError:
            self.read_only = True
            self.message = "Não foi possível ler as preferências. Usando os padrões sem alterar o arquivo."
            return Preferences()
        if payload["schema_version"] != SCHEMA_VERSION:
            self.read_only = True
            self.message = "Este arquivo de preferências usa uma versão não suportada. Ele será preservado sem alterações."
            return Preferences()
        try:
            return Preferences.from_dict(payload.get("preferences", {}))
        except (ValueError, TypeError, RecursionError):
            self._recover()
            return Preferences()

    def save(self, preferences):
        if not isinstance(preferences, Preferences):
            raise ValueError("Preferências inválidas.")
        # Recheck the on-disk schema before every save, including when another
        # program upgraded the file after this application loaded it.
        self.load()
        if self.read_only:
            raise PermissionError(self.message)
        data = json.dumps({"schema_version": SCHEMA_VERSION, "preferences": preferences.to_dict()},
                          ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if len(data.encode("utf-8")) > MAX_SETTINGS_BYTES:
            raise ValueError("Arquivo de preferências excede o limite.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=".settings-",
                                             suffix=".tmp", dir=self.path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
