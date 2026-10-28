"""Typed neighbor identities and conservative, directional inventory correlation."""

from collections import defaultdict
from datetime import datetime, timezone
from ipaddress import ip_address


def clean_text(value):
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value if isinstance(value, str) else ""
    return "".join(char if char >= " " and ord(char) != 127 else " " for char in text[:512]).strip()


def identity(subtype, raw, *, port=False):
    raw = raw[:512] if isinstance(raw, bytes) else b""
    subtype = subtype if type(subtype) is int and 1 <= subtype <= 7 else None
    mac_type, network_type = (3, 4) if port else (4, 5)
    value = clean_text(raw)
    if subtype == mac_type:
        value = ":".join(f"{byte:02X}" for byte in raw) if len(raw) == 6 else ""
    elif subtype == network_type:
        value = ""
        if raw and (raw[0], len(raw) - 1) in ((1, 4), (2, 16)):
            value = str(ip_address(raw[1:]))
    return {"subtype": subtype, "value": value, "raw_hex": raw.hex()}


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _same_identity(first, second):
    return bool(first.get("subtype") and first.get("raw_hex")
                and (first.get("subtype"), first.get("raw_hex")) == (second.get("subtype"), second.get("raw_hex")))


def correlate_neighbors(devices, *, now=None, window=300):
    """Keep every direction/protocol; reciprocal evidence is never a cable proof.

    The five minute freshness window is a local correlation policy, not LLDP TTL.
    Unknown/mismatched contexts, identities or ports prevent reciprocal status.
    """
    now = now or datetime.now(timezone.utc)
    records = {item["ip"]: item for item in devices}
    by_address, by_chassis, by_mac, by_name = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    for ip, device in records.items():
        by_address[ip].add(ip)
        mac = str(device.get("mac", "")).replace("-", ":").upper()
        if mac:
            by_mac[mac].add(ip)
        sample = device.get("l2_observation") or {}
        chassis = sample.get("local_chassis") or {}
        if chassis.get("subtype") and chassis.get("raw_hex"):
            by_chassis[(chassis["subtype"], chassis["raw_hex"])].add(ip)
        for name in (device.get("nome"), sample.get("local_system_name")):
            if name:
                by_name[str(name).casefold()].add(ip)
    result = []
    for ip, device in records.items():
        sample = device.get("l2_observation") or {}
        stamp = _stamp(sample.get("observed_at"))
        stale = stamp is None or not 0 <= (now - stamp).total_seconds() <= window
        for neighbor in sample.get("neighbors", []):
            candidates = set()
            for address in neighbor.get("management_addresses", []):
                candidates.update(by_address.get(address, ()))
            chassis = neighbor.get("remote_chassis") or {}
            candidates.update(by_chassis.get((chassis.get("subtype"), chassis.get("raw_hex")), ()))
            if neighbor.get("protocol") == "LLDP" and chassis.get("subtype") == 4:
                candidates.update(by_mac.get(chassis.get("value"), ()))
            if neighbor.get("protocol") == "LLDP" and chassis.get("subtype") == 5:
                candidates.update(by_address.get(chassis.get("value"), ()))
            method = "identity_or_address"
            if not candidates and neighbor.get("remote_name"):
                candidates.update(by_name.get(str(neighbor["remote_name"]).casefold(), ()))
                method = "unique_name"
            target = next(iter(candidates)) if len(candidates) == 1 and ip not in candidates else None
            status = "ambiguous" if len(candidates) > 1 else "unilateral" if target else "unresolved"
            target_chassis = ((records[target].get("l2_observation") or {}).get("local_chassis") or {}) if target else {}
            conflict = (neighbor.get("protocol") == "LLDP" and chassis.get("subtype") and chassis.get("raw_hex")
                        and target_chassis.get("subtype") and target_chassis.get("raw_hex")
                        and not _same_identity(chassis, target_chassis))
            if conflict:
                status = "identity_conflict"
            result.append({**neighbor, "observer_ip": ip, "target_ip": target, "candidate_ips": sorted(candidates),
                           "resolution_method": method if candidates else "unresolved", "observed_at": sample.get("observed_at", ""),
                           "context_scope": (sample.get("network_context") or {}).get("comparison_scope"),
                           "stale": stale, "status": "stale" if stale and target else status,
                           "direct_link_confirmed": False})
    by_direction = defaultdict(list)
    for item in result:
        by_direction[(item["observer_ip"], item["target_ip"], item["protocol"])].append(item)
    for item in result:
        if not item["target_ip"] or item["stale"] or item["status"] == "identity_conflict":
            continue
        opposites = [other for other in by_direction[(item["target_ip"], item["observer_ip"], item["protocol"])]
                     if not other["stale"] and other["status"] != "identity_conflict" and item["context_scope"]
                     and item["context_scope"] == other["context_scope"]]
        matching_ports = [other for other in opposites if _same_identity(item["remote_port"], other["local_port"].get("identity", {}))
                          and _same_identity(other["remote_port"], item["local_port"].get("identity", {}))]
        exact = [other for other in matching_ports if item["resolution_method"] != "unique_name" and other["resolution_method"] != "unique_name"]
        incomplete_ports = any(not side.get("subtype") or not side.get("raw_hex") for other in opposites
                               for side in (item["remote_port"], item["local_port"].get("identity", {}),
                                            other["remote_port"], other["local_port"].get("identity", {})))
        item["status"] = ("reciprocal" if len(exact) == 1 else "ambiguous" if len(exact) > 1 else "unilateral" if matching_ports
                          else "ports_unresolved" if opposites and incomplete_ports
                          else "divergent" if opposites else "unilateral")
    return result


STATUS_LABELS = {"unresolved": "Sem correspondência no inventário", "ambiguous": "Identidade ambígua",
                 "unilateral": "Relato unilateral", "reciprocal": "Relatos recíprocos",
                 "divergent": "Portas divergentes", "ports_unresolved": "Portas insuficientes para correlação",
                 "identity_conflict": "Identidade do chassi divergente",
                 "stale": "Fora da janela de correlação"}


def neighbor_summary(item):
    local = item["local_port"].get("name") or "Porta local não identificada"
    remote = item["remote_port"].get("value") or "Porta remota não identificada"
    name = item.get("remote_name") or item["remote_chassis"].get("value") or "Identidade não informada"
    return f"{item['protocol']} · {local} → {name} · {remote} · {STATUS_LABELS[item['status']]}"
