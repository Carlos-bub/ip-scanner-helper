"""Read local Windows interface prefixes without an internet connection."""

from dataclasses import dataclass
from ipaddress import IPv4Interface, IPv4Address
import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalInterface:
    name: str
    address: str
    prefix: int
    gateway: str | None

    @property
    def network(self):
        return str(IPv4Interface(f"{self.address}/{self.prefix}").network)

    @property
    def label(self):
        return f"{self.name} — {self.address}/{self.prefix}"


def discover_interfaces():
    if os.name != "nt":
        return []
    command = (
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
        "Get-NetIPConfiguration | ForEach-Object { $c = $_; "
        "$_.IPv4Address | ForEach-Object { [pscustomobject]@{ "
        "name=$c.InterfaceAlias; address=$_.IPAddress; prefix=$_.PrefixLength; "
        "gateway=$c.IPv4DefaultGateway.NextHop } } } | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, timeout=8, creationflags=0x08000000, check=True)
        records = json.loads(result.stdout.decode("utf-8-sig") or "[]")
        if isinstance(records, dict):
            records = [records]
        interfaces = []
        for record in records:
            interface = IPv4Interface(f"{record['address']}/{record['prefix']}")
            if interface.ip.is_loopback or interface.ip.is_unspecified:
                continue
            gateway = record.get("gateway")
            if isinstance(gateway, list):
                gateway = gateway[0] if gateway else None
            interfaces.append(LocalInterface(record["name"], str(interface.ip),
                                             interface.network.prefixlen,
                                             str(IPv4Address(gateway)) if gateway else None))
        return sorted(interfaces, key=lambda item: (not bool(item.gateway), item.name))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        logger.warning("Não foi possível obter interfaces locais", exc_info=True)
        return []
