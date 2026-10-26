"""Local IPv4 interface value object, independent of Windows discovery."""

from dataclasses import dataclass
from ipaddress import IPv4Interface


@dataclass(frozen=True)
class LocalInterface:
    name: str
    address: str
    prefix: int
    gateway: str | None
    adapter_id: str = ""

    @property
    def network(self):
        return str(IPv4Interface(f"{self.address}/{self.prefix}").network)

    @property
    def label(self):
        return f"{self.name} — {self.address}/{self.prefix}"


