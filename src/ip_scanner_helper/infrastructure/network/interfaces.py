"""Read local Windows interface prefixes without an internet connection."""

from ipaddress import IPv4Interface, IPv4Address
import json
import logging
import os
import subprocess

from ip_scanner_helper.infrastructure.network.windows_adapters import get_ipv4_adapters
from ip_scanner_helper.domain.interfaces import LocalInterface

logger = logging.getLogger(__name__)


def discover_interfaces():
    if os.name != "nt":
        return []
    try:
        records = get_ipv4_adapters()
        interfaces = [LocalInterface(**record) for record in records]
        return sorted(interfaces, key=lambda item: (not bool(item.gateway), item.name, item.address))
    except (OSError, ValueError, AttributeError):
        logger.warning("API de interfaces indisponível; usando fallback PowerShell", exc_info=True)
        return _discover_interfaces_powershell()


def _discover_interfaces_powershell():
    """Compatibility fallback; native enumeration does not spawn PowerShell."""
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
