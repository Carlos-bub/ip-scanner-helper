"""Rotating application logs; output location can be overridden for portability."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def configure_logging(directory=None):
    base = Path(directory or os.environ.get("IP_SCANNER_DATA_DIR") or
                Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "IPScannerHelper")
    try:
        base.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(base / "scanner.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    return base
