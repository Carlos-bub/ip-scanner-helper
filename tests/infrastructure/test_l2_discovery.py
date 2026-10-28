from datetime import datetime, timezone
import json
from threading import Event
import unittest
from unittest.mock import patch

from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.infrastructure.network.l2_discovery import L2Collector, ROOTS, parse_snapshot, port_bitmap
from ip_scanner_helper.infrastructure.network.snmp import SnmpAgentError, SnmpError
from ip_scanner_helper.infrastructure.network.snmp_walk import WalkResult, walk_tree


def fixture_tables():
    local, remote, management, cdp = (ROOTS[key] for key in ("lldp_local", "lldp_remote", "lldp_management", "cdp"))
    return {
        "lldp_local": {local + ".1.0": 4, local + ".2.0": bytes.fromhex("020000000001"), local + ".3.0": b"SW-A",
                       local + ".7.1.2.24": 5, local + ".7.1.3.24": b"Gi1/0/24", local + ".7.1.4.24": b"Uplink"},
        "lldp_remote": {remote + ".4.100.24.1": 4, remote + ".5.100.24.1": bytes.fromhex("020000000002"),
                        remote + ".6.100.24.1": 5, remote + ".7.100.24.1": b"Gi1/0/48", remote + ".9.100.24.1": b"SW-B"},
        "lldp_management": {management + ".3.100.24.1.1.4.192.0.2.2": 2,
                            management + ".4.100.24.1.1.4.192.0.2.2": 148},
        "cdp": {cdp + ".3.124.1": 1, cdp + ".4.124.1": bytes([192, 0, 2, 2]), cdp + ".6.124.1": b"arbitrary-device-id",
                cdp + ".7.124.1": b"Gi1/0/48", cdp + ".24.124.1": 50},
        "if_names": {ROOTS["if_names"] + ".124": b"Gi1/0/24"},
        "bridge_ports": {ROOTS["bridge_ports"] + ".3": 124},
        "pvid": {ROOTS["pvid"] + ".3": 10},
        "vlan_current": {ROOTS["vlan_current"] + ".4.0.10": b"\x20", ROOTS["vlan_current"] + ".5.0.10": b"\x20",
                         ROOTS["vlan_current"] + ".4.0.20": b"\x20", ROOTS["vlan_current"] + ".5.0.20": b"\0"},
    }


def snapshot(tables=None):
    tables = fixture_tables() if tables is None else tables
    return parse_snapshot("192.0.2.1", tables,
                          {key: {"entries": len(value), "partial": False, "reason": "", "requests": 1,
                                 "fallback": False, "unsupported": False} for key, value in tables.items()},
                          datetime.now(timezone.utc).isoformat(), uptime=500)


class L2DiscoveryTests(unittest.TestCase):
    def test_decodes_lldp_and_cdp_without_merging_protocols_or_port_indices(self):
        sample = snapshot()
        self.assertEqual(len(sample["neighbors"]), 2)
        lldp, cdp = sample["neighbors"]
        self.assertEqual(lldp["local_port"]["lldp_port_num"], 24)
        self.assertEqual(lldp["local_port"]["if_index"], 124)
        self.assertEqual(lldp["remote_port"]["value"], "Gi1/0/48")
        self.assertEqual(lldp["remote_chassis"]["value"], "02:00:00:00:00:02")
        self.assertEqual(lldp["management_addresses"], ["192.0.2.2"])
        self.assertEqual(cdp["local_port"]["if_index"], 124)
        self.assertEqual(cdp["remote_chassis"]["value"], "arbitrary-device-id")
        self.assertEqual(cdp["management_addresses"], ["192.0.2.2"])
        self.assertEqual(lldp["seconds_since_change"], 4)
        self.assertIsNone(lldp["expires_at"])
        self.assertIsNone(sample["expires_at"])

    def test_vlan_bitmaps_use_bridge_port_map_and_keep_pvid_separate_from_tagging(self):
        port = snapshot()["vlan_ports"][0]
        self.assertEqual((port["bridge_port"], port["if_index"], port["pvid"]), (3, 124, 10))
        self.assertEqual(port["tagged"], [20])
        self.assertEqual(port["untagged"], [10])
        self.assertEqual(port["mode"], "Não determinado")
        self.assertTrue(port["membership_complete"])
        self.assertEqual(port_bitmap(b"\x81\x80"), {1, 8, 9})
        self.assertIsNone(port_bitmap(b"\0" * 513))

    def test_missing_or_inconsistent_bitmap_does_not_invent_tagged_memberships(self):
        tables = fixture_tables()
        tables["vlan_current"][ROOTS["vlan_current"] + ".5.0.20"] = b"\x80"
        sample = snapshot(tables)
        self.assertTrue(sample["partial"])
        self.assertTrue(sample["vlan_issues"])
        self.assertFalse(sample["vlan_ports"][0]["tagged"])
        self.assertFalse(sample["vlan_ports"][0]["membership_complete"])
        del tables["vlan_current"][ROOTS["vlan_current"] + ".5.0.20"]
        self.assertFalse(snapshot(tables)["vlan_ports"][0]["tagged"])

    def test_latest_vlan_row_is_not_mixed_with_older_untagged_bitmap(self):
        tables = fixture_tables()
        tables["vlan_current"][ROOTS["vlan_current"] + ".4.99.20"] = b"\x20"
        sample = snapshot(tables)
        self.assertTrue(sample["partial"])
        self.assertFalse(sample["vlan_ports"][0]["tagged"])

    def test_lldp_port_number_is_never_assumed_to_be_ifindex(self):
        tables = fixture_tables()
        tables["if_names"] = {ROOTS["if_names"] + ".24": b"Other"}
        sample = snapshot(tables)
        self.assertIsNone(sample["neighbors"][0]["local_port"]["if_index"])
        tables["bridge_ports"] = {}
        self.assertIsNone(snapshot(tables)["vlan_ports"][0]["if_index"])
        tables["if_names"][ROOTS["if_names"] + ".124"] = b"Gi1/0/24"
        tables["if_names"][ROOTS["if_names"] + ".224"] = b"Gi1/0/24"
        self.assertIsNone(snapshot(tables)["neighbors"][0]["local_port"]["if_index"])

    def test_management_indices_require_exact_length_and_skip_unsupported_address_types(self):
        tables = fixture_tables()
        tables["lldp_management"] = {ROOTS["lldp_management"] + ".3.100.24.1.1.5.192.0.2.2": 2,
                                      ROOTS["lldp_management"] + ".3.100.24.1.7.4.192.0.2.2": 2}
        self.assertFalse(snapshot(tables)["neighbors"][0]["management_addresses"])

    def test_empty_tables_are_not_a_claim_that_no_neighbors_exist(self):
        sample = snapshot({})
        self.assertFalse(sample["neighbors"])
        self.assertFalse(sample["vlan_ports"])
        self.assertIsNone(sample["local_chassis"]["subtype"])

    def test_cancelled_collection_never_opens_a_socket_and_keeps_coverage(self):
        cancel = Event()
        cancel.set()
        with patch("ip_scanner_helper.infrastructure.network.snmp.socket.socket") as socket:
            sample = L2Collector().collect("192.0.2.1", "fixture-secret", context=ProbeContext.standalone(30, cancel))
        socket.assert_not_called()
        self.assertTrue(sample["cancelled"])
        self.assertTrue(sample["partial"])
        self.assertNotIn("fixture-secret", json.dumps(sample))
        self.assertTrue(all(item["requests"] == 0 for item in sample["coverage"].values()))

    def test_agent_simulation_preserves_tables_and_sanitizes_failures(self):
        tables = fixture_tables()
        def walk(ip, community, root, **kwargs):
            result = WalkResult()
            result.update(next((values for key, values in tables.items() if ROOTS[key] == root), {}))
            return result
        with patch("ip_scanner_helper.infrastructure.network.l2_discovery.walk_tree", side_effect=walk), \
             patch("ip_scanner_helper.infrastructure.network.l2_discovery.query", side_effect=SnmpError("fixture-secret")):
            sample = L2Collector().collect("192.0.2.1", "fixture-secret")
        self.assertEqual(len(sample["neighbors"]), 2)
        self.assertNotIn("fixture-secret", json.dumps(sample))
        self.assertIsNone(sample["neighbors"][0]["seconds_since_change"])


class BulkWalkTests(unittest.TestCase):
    root = "1.3.6.1.2.1.2"

    def test_bulk_preserves_many_rows_in_fewer_requests(self):
        calls = []
        def agent(ip, oid, community, **kwargs):
            calls.append(kwargs)
            start = 1 if oid == self.root else int(oid.split(".")[-1]) + 1
            return [(f"{self.root}.{index}", 2, index) for index in range(start, min(start + kwargs["bulk_repetitions"], 31))] or [(self.root, 0x82, b"")]
        result = walk_tree("192.0.2.1", "public", self.root, query_fn=agent)
        self.assertEqual(len(result), 30)
        self.assertEqual(result.requests, 4)
        self.assertFalse(result.partial)

    def test_too_big_reduces_repetitions_then_falls_back(self):
        calls = []
        def agent(*args, **kwargs):
            calls.append(kwargs)
            if "bulk_repetitions" in kwargs:
                raise SnmpAgentError(1)
            return [(self.root, 0x82, b"")]
        result = walk_tree("192.0.2.1", "secret", self.root, query_fn=agent)
        self.assertEqual([item["bulk_repetitions"] for item in calls[:-1]], [12, 6, 3, 1])
        self.assertTrue(calls[-1]["next_oid"])
        self.assertFalse(result.partial)
        self.assertTrue(result.fallback)

    def test_timeout_uses_getnext_without_discarding_collected_rows(self):
        def agent(ip, oid, community, **kwargs):
            if oid == self.root:
                return [(self.root + ".1", 2, 1)]
            if "bulk_repetitions" in kwargs:
                raise TimeoutError("secret")
            return [(self.root, 0x82, b"")]
        result = walk_tree("192.0.2.1", "secret", self.root, query_fn=agent)
        self.assertEqual(len(result), 1)
        self.assertTrue(result.fallback)
        self.assertFalse(result.partial)

    def test_version_one_always_uses_getnext(self):
        def agent(*args, **kwargs):
            self.assertTrue(kwargs["next_oid"])
            self.assertNotIn("bulk_repetitions", kwargs)
            raise SnmpAgentError(2)
        result = walk_tree("192.0.2.1", "public", self.root, version=0, query_fn=agent)
        self.assertTrue(result.unsupported)
        self.assertFalse(result.partial)

    def test_cancel_deadline_and_entry_cap_keep_partial_data(self):
        cancel = Event()
        def agent(*args, **kwargs):
            cancel.set()
            return [(self.root + ".1", 2, 1)]
        result = walk_tree("192.0.2.1", "public", self.root, context=ProbeContext.standalone(2, cancel), query_fn=agent)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.reason, "cancelada")
        deadline = walk_tree("192.0.2.1", "public", self.root, context=ProbeContext.standalone(0), query_fn=agent)
        self.assertEqual(deadline.requests, 0)
        cap = walk_tree("192.0.2.1", "public", self.root, max_reps=1, query_fn=agent)
        self.assertEqual(cap.reason, "limite de entradas")

    def test_malformed_order_or_excess_bindings_do_not_claim_complete(self):
        for values in ([(self.root + ".1", 2, 1)] * 2,
                       [(self.root + ".2", 2, 2), (self.root + ".1", 2, 1)],
                       [(self.root + ".1", 2, 1)] * 51):
            with self.subTest(values=values):
                result = walk_tree("192.0.2.1", "secret", self.root, query_fn=lambda *args, **kwargs: values)
                self.assertTrue(result.partial)
                self.assertNotIn("secret", result.reason)

    def test_out_of_subtree_lower_oid_is_not_a_clean_termination(self):
        def agent(ip, oid, community, **kwargs):
            return [(self.root + ".1", 2, 1)] if oid == self.root else [("1.3.6.1.2.1.1.9", 2, 1)]
        result = walk_tree("192.0.2.1", "public", self.root, query_fn=agent)
        self.assertTrue(result.partial)
        self.assertEqual(len(result), 1)
