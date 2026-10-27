"""Validated, immutable desktop preferences containing no inventory or secrets."""

from dataclasses import dataclass, field
import math
from typing import Mapping

COLUMN_KEYS = ("ip", "nome", "fabricante", "tipo", "latencia", "mac", "origem", "portas", "confianca")
DEFAULT_VISIBLE_COLUMNS = COLUMN_KEYS[:7]
DEFAULT_COLUMN_WIDTHS = tuple(zip(COLUMN_KEYS, (140, 240, 190, 190, 110, 170, 180, 260, 180)))


def _integer(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"Preferência inválida: {name}.")
    return value


def _boolean(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"Preferência inválida: {name}.")
    return value


def _text(value, maximum, name):
    if (not isinstance(value, str) or len(value) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError(f"Preferência inválida: {name}.")
    return value.strip()


@dataclass(frozen=True)
class WindowPreferences:
    x: int | None = None
    y: int | None = None
    width: int = 1440
    height: int = 900
    maximized: bool = False

    def __post_init__(self):
        for name in ("x", "y"):
            value = getattr(self, name)
            if value is not None:
                _integer(value, -100000, 100000, name)
        _integer(self.width, 960, 16384, "width")
        _integer(self.height, 640, 16384, "height")
        _boolean(self.maximized, "maximized")

    def to_dict(self):
        return {name: getattr(self, name) for name in ("x", "y", "width", "height", "maximized")}

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, Mapping):
            raise ValueError("Preferências de janela inválidas.")
        return cls(**{key: payload[key] for key in ("x", "y", "width", "height", "maximized") if key in payload})


@dataclass(frozen=True)
class Preferences:
    window: WindowPreferences = field(default_factory=WindowPreferences)
    visible_columns: tuple[str, ...] = DEFAULT_VISIBLE_COLUMNS
    column_widths: tuple[tuple[str, float], ...] = DEFAULT_COLUMN_WIDTHS
    sort_key: str = "ip"
    sort_reverse: bool = False
    last_target: str = ""
    interface_id: str = ""
    interface_name: str = ""
    mode: str = "Completo"
    workers: int = 32
    target_timeout: float = 20.0

    def __post_init__(self):
        if not isinstance(self.window, WindowPreferences):
            raise ValueError("Preferências de janela inválidas.")
        if (not isinstance(self.visible_columns, (tuple, list))
                or any(not isinstance(key, str) or key not in COLUMN_KEYS for key in self.visible_columns)
                or len(set(self.visible_columns)) != len(self.visible_columns)):
            raise ValueError("Colunas inválidas.")
        # Mandatory identity columns remain visible even in a hand-edited file.
        selected = set(self.visible_columns) | {"ip", "nome"}
        object.__setattr__(self, "visible_columns", tuple(key for key in COLUMN_KEYS if key in selected))
        if not isinstance(self.column_widths, (tuple, list)):
            raise ValueError("Larguras de colunas inválidas.")
        widths = dict(DEFAULT_COLUMN_WIDTHS)
        seen = set()
        for item in self.column_widths:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError("Larguras de colunas inválidas.")
            key, value = item
            if (not isinstance(key, str) or key not in COLUMN_KEYS or key in seen
                    or isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or not 60 <= value <= 1200):
                raise ValueError("Larguras de colunas inválidas.")
            seen.add(key)
            widths[key] = float(value)
        object.__setattr__(self, "column_widths", tuple((key, widths[key]) for key in COLUMN_KEYS))
        if not isinstance(self.sort_key, str) or self.sort_key not in COLUMN_KEYS:
            raise ValueError("Ordenação inválida.")
        _boolean(self.sort_reverse, "sort_reverse")
        for name, maximum in (("last_target", 256), ("interface_id", 256), ("interface_name", 256)):
            object.__setattr__(self, name, _text(getattr(self, name), maximum, name))
        if self.mode not in ("Rápido", "Completo"):
            raise ValueError("Modo de varredura inválido.")
        _integer(self.workers, 1, 128, "workers")
        if (isinstance(self.target_timeout, bool) or not isinstance(self.target_timeout, (float, int))
                or not math.isfinite(self.target_timeout) or not 0 < self.target_timeout <= 300):
            raise ValueError("Limite por IP inválido.")
        object.__setattr__(self, "target_timeout", float(self.target_timeout))

    def to_dict(self):
        return {
            "window": self.window.to_dict(), "visible_columns": list(self.visible_columns),
            "column_widths": dict(self.column_widths), "sort_key": self.sort_key,
            "sort_reverse": self.sort_reverse, "last_target": self.last_target,
            "interface_id": self.interface_id, "interface_name": self.interface_name,
            "mode": self.mode, "workers": self.workers, "target_timeout": self.target_timeout,
        }

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, Mapping):
            raise ValueError("Preferências inválidas.")
        values = {}
        if "window" in payload:
            values["window"] = WindowPreferences.from_dict(payload["window"])
        if "visible_columns" in payload:
            values["visible_columns"] = payload["visible_columns"]
        if "column_widths" in payload:
            if not isinstance(payload["column_widths"], Mapping):
                raise ValueError("Larguras de colunas inválidas.")
            values["column_widths"] = tuple(payload["column_widths"].items())
        for key in ("sort_key", "sort_reverse", "last_target", "interface_id", "interface_name",
                    "mode", "workers", "target_timeout"):
            if key in payload:
                values[key] = payload[key]
        return cls(**values)
