"""Validation before allocating targets or starting network traffic."""

from ipaddress import IPv4Address, IPv4Network

MAX_TARGETS = 4096


def parse_targets(text: str, limit: int = MAX_TARGETS) -> list[str]:
    text = text.strip()
    if "-" in text:
        parts = text.split("-")
        if len(parts) != 2:
            raise ValueError("Informe uma faixa com início e fim.")
        start, end = (IPv4Address(part.strip()) for part in parts)
        count = int(end) - int(start) + 1
        if count < 1:
            raise ValueError("O fim da faixa deve ser maior ou igual ao início.")
        if count > limit:
            raise ValueError(f"Limite de {limit} endereços por varredura.")
        targets = [IPv4Address(value) for value in range(int(start), int(end) + 1)]
    elif "/" in text:
        network = IPv4Network(text, strict=False)
        count = network.num_addresses - (2 if network.prefixlen < 31 else 0)
        if count > limit:
            raise ValueError(f"Limite de {limit} endereços por varredura.")
        targets = list(network.hosts())
    else:
        targets = [IPv4Address(text)]
    if any(ip.is_multicast or ip.is_unspecified or int(ip) == 0xFFFFFFFF for ip in targets):
        raise ValueError("Use endereços unicast; multicast e broadcast não são alvos válidos.")
    return [str(ip) for ip in targets]
