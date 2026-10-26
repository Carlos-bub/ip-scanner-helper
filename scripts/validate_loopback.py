"""Validate Windows native ICMP and real TCP selectors on loopback only."""

import socket

from ip_scanner_helper.infrastructure.network.tcp_probe import scan_tcp_ports, SocketBudget
from ip_scanner_helper.infrastructure.network.windows_network import ping_ipv4


def main():
    # Keep the refused port bound throughout the test so another process cannot
    # take it. Neither socket is exposed on an external network interface.
    with socket.socket() as listener, socket.socket() as refused:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        refused.bind(("127.0.0.1", 0))
        ports = {listener.getsockname()[1]: "Open", refused.getsockname()[1]: "Refused"}
        budget = SocketBudget(2)
        services = scan_tcp_ports("127.0.0.1", ports, timeout=.5, budget=budget)
        assert services == [f"Open({listener.getsockname()[1]})"], services
        assert budget.active == 0
    active, latency = ping_ipv4("127.0.0.1")
    assert active, "Windows ICMP adapter did not receive a loopback echo reply"
    print(f"Loopback OK: real TCP open/refused, native IPv4 ICMP RTT={latency}; no LAN targets.")


if __name__ == "__main__":
    main()
