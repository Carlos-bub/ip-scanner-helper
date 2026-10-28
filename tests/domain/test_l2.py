from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
import xml.etree.ElementTree as ET

from ip_scanner_helper.domain.l2 import identity, correlate_neighbors
from ip_scanner_helper.domain.topology import build_topology_graph
from ip_scanner_helper.infrastructure.diagram_export import render_dot, render_drawio


def neighbor(local="Gi24", remote="Gi48", address="192.0.2.2", chassis="02:00:00:00:00:02"):
    return {"protocol": "LLDP", "local_port": {"name": local, "identity": identity(5, local.encode(), port=True)},
            "remote_port": identity(5, remote.encode(), port=True),
            "remote_chassis": identity(4, bytes.fromhex(chassis.replace(":", ""))),
            "remote_name": "SW-B", "management_addresses": [address], "expires_at": None}


def devices(now=None):
    now = now or datetime.now(timezone.utc)
    samples = []
    for index, local, remote, remote_index in ((1, "Gi24", "Gi48", 2), (2, "Gi48", "Gi24", 1)):
        samples.append({"ip": f"192.0.2.{index}", "nome": f"SW-{index}", "tipo": "Switch",
                        "mac": f"02:00:00:00:00:0{index}", "l2_observation": {
                            "observed_at": now.isoformat(), "network_context": {"comparison_scope": "session:fixture"},
                            "local_chassis": identity(4, bytes.fromhex(f"02000000000{index}")),
                            "neighbors": [neighbor(local, remote, f"192.0.2.{remote_index}", f"02:00:00:00:00:0{remote_index}")],
                            "vlan_ports": []}})
    return samples


class L2DomainTests(unittest.TestCase):
    def test_identity_preserves_non_mac_non_ip_and_binary_subtypes(self):
        self.assertEqual(identity(7, b"arbitrary-chassis")["value"], "arbitrary-chassis")
        self.assertEqual(identity(5, b"\x01\xc0\x00\x02\x01")["value"], "192.0.2.1")
        self.assertEqual(identity(4, b"invalid")["value"], "")
        self.assertEqual(identity(3, bytes.fromhex("020000000001"), port=True)["value"], "02:00:00:00:00:01")
        self.assertEqual(identity(7, b"x\0y")["raw_hex"], "780079")

    def test_reciprocal_requires_matching_ports_scope_freshness_and_identity(self):
        records = devices()
        original = deepcopy(records)
        result = correlate_neighbors(records)
        self.assertEqual([item["status"] for item in result], ["reciprocal", "reciprocal"])
        self.assertTrue(all(not item["direct_link_confirmed"] for item in result))
        self.assertEqual(records, original)
        records[1]["l2_observation"]["network_context"]["comparison_scope"] = "session:other"
        self.assertEqual(correlate_neighbors(records)[0]["status"], "unilateral")

    def test_old_future_and_unknown_timestamps_do_not_claim_reciprocity(self):
        now = datetime.now(timezone.utc)
        for stamp in ((now - timedelta(seconds=301)).isoformat(), (now + timedelta(seconds=5)).isoformat(), "", "2026-10-27"):
            records = devices(now)
            records[1]["l2_observation"]["observed_at"] = stamp
            result = correlate_neighbors(records, now=now)
            self.assertEqual(result[0]["status"], "unilateral")
            self.assertEqual(result[1]["status"], "stale")

    def test_divergent_ports_missing_ports_and_conflicting_chassis_are_distinct(self):
        records = devices()
        records[1]["l2_observation"]["neighbors"][0]["remote_port"] = identity(5, b"Gi9", port=True)
        self.assertEqual(correlate_neighbors(records)[0]["status"], "divergent")
        records[1]["l2_observation"]["neighbors"][0]["remote_port"] = identity(None, None, port=True)
        self.assertEqual(correlate_neighbors(records)[0]["status"], "ports_unresolved")
        records = devices()
        records[0]["l2_observation"]["neighbors"][0]["remote_chassis"] = identity(7, b"wrong")
        self.assertEqual(correlate_neighbors(records)[0]["status"], "identity_conflict")
        self.assertEqual(correlate_neighbors(records)[1]["status"], "unilateral")

    def test_duplicate_identity_or_conflicting_management_address_is_ambiguous(self):
        records = devices()
        records.append({"ip": "192.0.2.3", "mac": records[1]["mac"]})
        result = correlate_neighbors(records)
        self.assertIsNone(result[0]["target_ip"])
        self.assertEqual(result[0]["status"], "ambiguous")
        self.assertEqual(result[0]["candidate_ips"], ["192.0.2.2", "192.0.2.3"])

    def test_unresolved_neighbors_keep_details_without_fake_ip_or_gateway_edge(self):
        records = devices()[:1]
        records[0]["l2_observation"]["neighbors"][0]["remote_name"] = "unmanaged-peer"
        graph = build_topology_graph(records, "192.0.2.254")
        self.assertFalse(graph["edges"])
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertIn("unmanaged-peer", graph["nodes"][0]["detail"])

    def test_multiple_ports_and_protocols_and_fdb_remain_separate(self):
        records = devices()
        second = neighbor("Gi25", "Gi49")
        records[0]["l2_observation"]["neighbors"].append(second)
        records[0]["l2_observation"]["neighbors"].append(dict(deepcopy(second), protocol="CDP"))
        records[1]["switch_observations"] = [{"switch_ip": "192.0.2.1", "port": "Gi24"}]
        graph = build_topology_graph(records)
        self.assertEqual(len(graph["edges"]), 5)
        self.assertEqual(sum(item["kind"] == "fdb_path" for item in graph["edges"]), 1)
        self.assertTrue(all(not item["direct_link_confirmed"] for item in graph["edges"]))
        xml = ET.fromstring(render_drawio(records))
        edges = xml.findall('.//object[@kind="reported_neighbor"]')
        self.assertEqual(len(edges), 8)  # Same observations on both diagram pages.
        self.assertTrue(all(item.get("remote_port") and item.get("expires_at") == "unknown" for item in edges))
        self.assertIn('kind="reported_neighbor"', render_dot(records))
        self.assertIn('kind="fdb_path"', render_dot(records))

    def test_name_only_resolution_is_not_sufficient_for_reciprocity(self):
        records = devices()
        for index, remote_name in ((0, "SW-2"), (1, "SW-1")):
            report = records[index]["l2_observation"]["neighbors"][0]
            report.update(management_addresses=[], remote_name=remote_name, remote_chassis=identity(None, None))
        result = correlate_neighbors(records)
        self.assertEqual([item["status"] for item in result], ["unilateral", "unilateral"])

    def test_partial_vlan_membership_and_coverage_are_kept_in_all_diagrams(self):
        records = devices()
        records[0]["tipo"] = "Dispositivo não identificado"
        records[0]["l2_observation"].update(partial=True, coverage={"vlan_current": {
            "entries": 3, "reason": "limite de entradas", "partial": True}}, vlan_ports=[{
                "name": "Gi24", "bridge_port": 3, "if_index": 124, "pvid": 10,
                "tagged": [20], "untagged": [10], "membership_complete": False}])
        node = build_topology_graph(records)["nodes"][0]
        self.assertTrue(node["neighbor_observer"])
        self.assertEqual(node["category"], "unknown")
        for content in (node["detail"], render_dot(records), render_drawio(records)):
            self.assertIn("participação parcial", content)
            self.assertIn("limite de entradas", content)
