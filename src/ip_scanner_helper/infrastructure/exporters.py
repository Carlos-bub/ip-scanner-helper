"""Portable inventory exports, with spreadsheet formula neutralization."""

import csv
import json
from pathlib import Path


def spreadsheet_cell(value):
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(path, devices):
    if not devices:
        raise ValueError("Não há dispositivos para exportar.")
    fields = list(dict.fromkeys(key for device in devices for key in device))
    with Path(path).open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows({key: spreadsheet_cell(value) for key, value in device.items()} for device in devices)


def export_json(path, devices):
    Path(path).write_text(json.dumps(devices, indent=2, ensure_ascii=False), encoding="utf-8")
