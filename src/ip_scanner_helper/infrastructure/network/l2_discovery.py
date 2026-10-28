"""Read-only LLDP-MIB, CISCO-CDP-MIB and Q-BRIDGE-MIB snapshots.

No vendor mode guessing, credential discovery, network recursion or SNMP SET.
Every table has a deadline and entry cap under one cancellable operation budget.
"""

from datetime import datetime
from ipaddress import ip_address

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled, TargetBudgetExceeded
from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.domain.l2 import identity, clean_text
from ip_scanner_helper.domain.topology import valid_ip
from ip_scanner_helper.infrastructure.network.snmp import query, SnmpError
from ip_scanner_helper.infrastructure.network.snmp_walk import walk_tree


ROOTS = {
    "lldp_local": "1.0.8802.1.1.2.1.3",
    "lldp_remote": "1.0.8802.1.1.2.1.4.1.1",
    "lldp_management": "1.0.8802.1.1.2.1.4.2.1",
    "cdp": "1.3.6.1.4.1.9.9.23.1.2.1.1",
    "if_names": "1.3.6.1.2.1.31.1.1.1.1",
    "if_descriptions": "1.3.6.1.2.1.2.2.1.2",
    "bridge_ports": "1.3.6.1.2.1.17.1.4.1.2",
    "vlan_current": "1.3.6.1.2.1.17.7.1.4.2.1",
    "pvid": "1.3.6.1.2.1.17.7.1.4.5.1.1",
}


def indexed(values, root):
    """Drop malformed and unrelated indices, without accepting suffix lookalikes."""
    prefix = root + "."
    result = {}
    for oid, value in values.items():
        if not oid.startswith(prefix):
            continue
        try:
            suffix = tuple(int(item) for item in oid[len(prefix):].split("."))
        except ValueError:
            continue
        if suffix and all(0 <= item <= 0xFFFFFFFF for item in suffix):
            result[suffix] = value
    return result


def rows(values, root, size):
    result = {}
    for suffix, value in indexed(values, root).items():
        if len(suffix) == size + 1:
            result.setdefault(suffix[1:], {})[suffix[0]] = value
    return result


def _positive(value):
    return value if type(value) is int and 0 < value <= 2147483647 else None


def _address(family, raw):
    if not isinstance(raw, bytes) or (family, len(raw)) not in ((1, 4), (2, 16)):
        return None
    address = ip_address(raw)
    return str(address) if not address.is_multicast and not address.is_unspecified else None


def _elapsed(uptime, tick):
    # TimeMark/LastChange are update markers, not advertisement age or TTL.
    if type(uptime) is int and type(tick) is int and 0 <= tick <= uptime <= 0xFFFFFFFF:
        return (uptime - tick) / 100
    return None


def port_bitmap(value):
    """PortList uses bridge port numbers, MSB first (RFC 4363)."""
    if not isinstance(value, bytes) or len(value) > 512:
        return None
    return {offset * 8 + bit + 1 for offset, byte in enumerate(value)
            for bit in range(8) if byte & (0x80 >> bit)}


def parse_snapshot(ip, tables, coverage, observed_at, *, uptime=None):
    local = indexed(tables.get("lldp_local", {}), ROOTS["lldp_local"])
    names = {key[0]: clean_text(value) for key, value in indexed(tables.get("if_names", {}), ROOTS["if_names"]).items()
             if len(key) == 1 and _positive(key[0])}
    descriptions = {key[0]: clean_text(value) for key, value in indexed(tables.get("if_descriptions", {}), ROOTS["if_descriptions"]).items()
                    if len(key) == 1 and _positive(key[0])}
    ports = {}
    for key, value in local.items():
        if len(key) == 4 and key[:2] == (7, 1) and _positive(key[3]):
            ports.setdefault(key[3], {})[key[2]] = value
    local_ports = {}
    for number, values in ports.items():
        port_id = identity(values.get(2), values.get(3), port=True)
        # lldpLocPortNum is NOT ifIndex. Only subtype interfaceName maps to ifName.
        candidates = [index for index in names if port_id["value"] and port_id["value"] == names[index]
                      and port_id["subtype"] == 5]
        index = candidates[0] if len(candidates) == 1 else None
        local_ports[number] = {"lldp_port_num": number, "identity": port_id, "if_index": index,
                               "name": names.get(index) or port_id["value"] or f"LLDP porta {number}",
                               "description": clean_text(values.get(4)), "mapping": "unique_label" if index else "unresolved"}
    management = {}
    for key in indexed(tables.get("lldp_management", {}), ROOTS["lldp_management"]):
        # column + timeMark + localPort + remIndex + family + addressLength + octets
        if len(key) < 7 or key[0] not in (3, 4, 5) or key[5] != len(key) - 6:
            continue
        if any(item > 255 for item in key[6:]):
            continue
        address = _address(key[4], bytes(key[6:]))
        if address:
            management.setdefault(key[1:4], set()).add(address)
    neighbors = []
    for key, values in sorted(rows(tables.get("lldp_remote", {}), ROOTS["lldp_remote"], 3).items()):
        tick, port, remote_index = key
        if not _positive(port) or not _positive(remote_index):
            continue
        neighbors.append({"protocol": "LLDP", "row_index": list(key),
            "local_port": local_ports.get(port, {"lldp_port_num": port, "if_index": None,
                "name": f"LLDP porta {port}", "identity": identity(None, None, port=True), "mapping": "unresolved"}),
            "remote_chassis": identity(values.get(4), values.get(5)),
            "remote_port": identity(values.get(6), values.get(7), port=True),
            "remote_name": clean_text(values.get(9)), "remote_description": clean_text(values.get(10)),
            "management_addresses": sorted(management.get(key, set())), "time_mark_ticks": tick,
            "seconds_since_change": _elapsed(uptime, tick), "expires_at": None})
    for key, values in sorted(rows(tables.get("cdp", {}), ROOTS["cdp"], 2).items()):
        index, remote_index = key
        if not _positive(index) or not _positive(remote_index):
            continue
        # CiscoNetworkProtocol ip(1); other address encodings remain unavailable.
        addresses = [_address(1, values.get(column)) for type_col, column in ((3, 4), (19, 20), (21, 22))
                     if values.get(type_col) == 1]
        neighbors.append({"protocol": "CDP", "row_index": list(key),
            "local_port": {"if_index": index, "name": names.get(index) or descriptions.get(index) or f"ifIndex {index}",
                           "identity": identity(5, (names.get(index) or "").encode(), port=True),
                           "mapping": "cdp_index", "lldp_port_num": None},
            "remote_chassis": identity(7, values.get(6)),
            "remote_port": identity(5, values.get(7), port=True),
            "remote_name": clean_text(values.get(16)) or clean_text(values.get(6)),
            "remote_description": clean_text(values.get(8)),
            "management_addresses": sorted({item for item in addresses if item}),
            "time_mark_ticks": values.get(24), "seconds_since_change": _elapsed(uptime, values.get(24)),
            "expires_at": None})
    vlan_ports, vlan_issues = _vlans(tables, names, descriptions)
    membership_complete = bool(tables.get("vlan_current")) and not vlan_issues and not coverage.get("vlan_current", {}).get("partial", True)
    for port in vlan_ports:
        port["membership_complete"] = membership_complete
    return {"schema_version": 1, "observer_ip": ip, "source": "SNMP v2c · LLDP/CDP/Q-BRIDGE",
            "observed_at": observed_at, "expires_at": None, "sys_uptime_ticks": uptime,
            "local_chassis": identity(local.get((1, 0)), local.get((2, 0))),
            "local_system_name": clean_text(local.get((3, 0))), "local_ports": list(local_ports.values()),
            "neighbors": neighbors, "vlan_ports": vlan_ports, "vlan_issues": vlan_issues,
            "coverage": coverage, "partial": any(item["partial"] for item in coverage.values()) or bool(vlan_issues),
            "cancelled": any(item["reason"] == "cancelada" for item in coverage.values())}


def _vlans(tables, names, descriptions):
    bridge = {key[0]: value for key, value in indexed(tables.get("bridge_ports", {}), ROOTS["bridge_ports"]).items()
              if len(key) == 1 and _positive(key[0]) and _positive(value)}
    pvids = {key[0]: value for key, value in indexed(tables.get("pvid", {}), ROOTS["pvid"]).items()
             if len(key) == 1 and _positive(key[0]) and type(value) is int and 1 <= value <= 4094}
    current, issues = {}, []
    for key, values in rows(tables.get("vlan_current", {}), ROOTS["vlan_current"], 2).items():
        tick, vlan = key
        if not 1 <= vlan <= 4094:
            continue  # Local VLAN indices >4095 do not identify an 802.1Q VID.
        if vlan not in current or tick > current[vlan][0]:
            current[vlan] = (tick, values)
    ports = {number: {"bridge_port": number, "if_index": bridge.get(number),
                      "name": names.get(bridge.get(number)) or descriptions.get(bridge.get(number)) or f"Bridge porta {number}",
                      "pvid": pvids.get(number), "tagged": [], "untagged": [], "egress": [],
                      "mode": "Não determinado", "source": "Q-BRIDGE-MIB"} for number in bridge.keys() | pvids.keys()}
    for vlan, (_, values) in sorted(current.items()):
        egress, untagged = port_bitmap(values.get(4)), port_bitmap(values.get(5))
        if egress is None or untagged is None or not untagged <= egress:
            issues.append(f"VLAN {vlan}: bitmap ausente, inválido ou inconsistente")
        for number in (egress or set()) | (untagged or set()):
            if number not in ports:
                ports[number] = {"bridge_port": number, "if_index": None, "name": f"Bridge porta {number}",
                                 "pvid": None, "tagged": [], "untagged": [], "egress": [],
                                 "mode": "Não determinado", "source": "Q-BRIDGE-MIB"}
            row = ports[number]
            if egress is not None and number in egress:
                row["egress"].append(vlan)
            if untagged is not None and number in untagged:
                row["untagged"].append(vlan)
            if egress is not None and untagged is not None and untagged <= egress and number in egress - untagged:
                row["tagged"].append(vlan)
    return [ports[number] for number in sorted(ports)], issues


class L2Collector:
    def collect(self, ip, community, *, context=None):
        if not valid_ip(ip):
            raise ValueError("IP de gerenciamento inválido")
        context = context or ProbeContext.standalone(30)
        observed_at = datetime.now().astimezone().isoformat()
        tables, coverage, uptime = {}, {}, None
        for name, root in ROOTS.items():
            if name == "if_descriptions" and tables.get("if_names"):
                coverage[name] = {"entries": 0, "partial": False, "reason": "ifName disponível; consulta dispensada",
                                  "requests": 0, "fallback": False, "unsupported": False}
                continue
            table = walk_tree(ip, community, root, context=context, budget=2.5)
            tables[name], coverage[name] = table, table.coverage()
        try:
            values = query(ip, "1.3.6.1.2.1.1.3.0", community, timeout=.6, context=context)
            uptime = next((value for oid, tag, value in values if oid == "1.3.6.1.2.1.1.3.0" and tag == 0x43), None)
        except (OSError, SnmpError, ProbeTimeout, ScanCancelled, TargetBudgetExceeded):
            pass  # Optional age reference; expiry is never invented.
        return parse_snapshot(ip, tables, coverage, observed_at, uptime=uptime)
