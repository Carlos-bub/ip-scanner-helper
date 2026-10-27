from copy import deepcopy
from ipaddress import IPv4Address
import unittest

from ip_scanner_helper.domain.topology import build_topology_graph, RelationKind


class TopologyTests(unittest.TestCase):
    def test_empty_inventory_has_no_artificial_gateway_or_root_node(self):
        graph = build_topology_graph([], "192.0.2.1")
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["groupings"], {"category": [], "switch": []})
        self.assertEqual(graph["gateway"], "192.0.2.1")

    def test_gateway_context_and_classification_do_not_prove_a_link(self):
        graph = build_topology_graph([{"ip": "192.0.2.2", "tipo": "Switch"},
                                      {"ip": "192.0.2.1", "tipo": "Dispositivo não identificado"}], "192.0.2.1")
        self.assertEqual(graph["edges"], [])
        self.assertTrue(graph["nodes"][0]["is_gateway"])
        self.assertEqual(graph["nodes"][0]["category"], "unknown")

    def test_category_membership_is_deterministic_and_does_not_infer_a_server_role(self):
        devices = [{"ip": "192.0.2.10", "tipo": "Estação / Servidor"},
                   {"ip": "192.0.2.2", "tipo": "Impressora"}]
        graph = build_topology_graph(devices)
        self.assertEqual(graph, build_topology_graph(list(reversed(devices))))
        groups = {group["id"]: group for group in graph["groupings"]["category"]}
        self.assertEqual(groups["category:workstations_servers"]["member_ids"], ["192.0.2.10"])
        self.assertNotIn("category:servers", groups)
        self.assertTrue(all(group["kind"] == RelationKind.LOGICAL_GROUP.value for group in groups.values()))
        self.assertTrue(all("x" not in node and "y" not in node for node in graph["nodes"]))

    def test_multiple_fdb_paths_and_same_switch_different_ports_are_preserved(self):
        devices = [{"ip": "192.0.2.1", "tipo": "Switch"}, {"ip": "192.0.2.2", "tipo": "Switch"},
                   {"ip": "192.0.2.10", "switch_observations": [
                       {"switch_ip": "192.0.2.1", "port": "Gi1", "source": "SNMP", "observed_at": "2026-10-27T12:00:00Z"},
                       {"switch_ip": "192.0.2.2", "port": "Gi2", "direct_link_confirmed": True},
                       {"switch_ip": "192.0.2.1", "port": "Gi3"}]}]
        original = deepcopy(devices)
        graph = build_topology_graph(devices)
        self.assertEqual(devices, original)
        self.assertEqual(len(graph["edges"]), 3)
        self.assertTrue(all(edge["kind"] == "fdb_path" and not edge["direct_link_confirmed"] for edge in graph["edges"]))
        groups = {group["id"]: group for group in graph["groupings"]["switch"]}
        self.assertEqual(groups["switch:192.0.2.1"]["member_ids"], ["192.0.2.10"])
        self.assertEqual(groups["switch:192.0.2.2"]["member_ids"], ["192.0.2.10"])
        self.assertEqual(groups["switch:192.0.2.1"]["context_ids"], ["192.0.2.1"])
        edge = graph["edges"][0]
        self.assertEqual(edge["source"], "SNMP")
        self.assertEqual(edge["observed_at"], "2026-10-27T12:00:00Z")
        self.assertEqual(graph["edges"][1]["observed_at"], "Instante não registrado")

    def test_external_observer_is_preserved_without_creating_a_device(self):
        graph = build_topology_graph([{"ip": "192.0.2.10", "switch_observations": [
            {"switch_ip": "192.0.2.254", "port": "24"}]}])
        self.assertEqual([node["id"] for node in graph["nodes"]], ["192.0.2.10"])
        self.assertFalse(graph["edges"][0]["source_in_inventory"])
        group = graph["groupings"]["switch"][0]
        self.assertEqual(group["context_ids"], [])
        self.assertIn("Fora do inventário", group["subtitle"])

    def test_unmapped_is_an_explicit_group_without_edges(self):
        graph = build_topology_graph([{"ip": "192.0.2.1"}, {"ip": "192.0.2.2"}])
        self.assertEqual(graph["groupings"]["switch"][0]["id"], "switch:unmapped")
        self.assertEqual(graph["groupings"]["switch"][0]["member_ids"], ["192.0.2.1", "192.0.2.2"])
        self.assertEqual(graph["edges"], [])

    def test_invalid_data_self_paths_and_exact_duplicates_do_not_duplicate_devices(self):
        observation = {"switch_ip": "192.0.2.2", "port": "1"}
        graph = build_topology_graph([None, {}, {"ip": True}, {"ip": "224.0.0.1"}, {"ip": "0.0.0.0"},
            {"ip": "192.0.2.1", "switch_observations": [None, observation, dict(observation),
             {"switch_ip": "192.0.2.1"}, {"switch_ip": "bad"}]}, {"ip": "192.0.2.1", "nome": "duplicate"}])
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(len(graph["edges"]), 1)

    def test_large_inventory_has_bounded_categories_and_complete_membership(self):
        for count in (10, 100, 500, 4096):
            with self.subTest(count=count):
                devices = [{"ip": str(IPv4Address("10.0.0.1") + index), "tipo": "Impressora"} for index in range(count)]
                graph = build_topology_graph(devices)
                groups = graph["groupings"]["category"]
                self.assertEqual(len(groups), 1)
                self.assertEqual(len(groups[0]["member_ids"]), count)
                self.assertEqual(len(graph["nodes"]), count)
                self.assertEqual(graph["edges"], [])

    def test_node_details_preserve_evidence_and_do_not_serialize_unrelated_secrets(self):
        graph = build_topology_graph([{"ip": "192.0.2.1", "origem": "DNS reverso", "confianca": "Baixa",
                                      "evidencia_categoria": "RDP não confirma função", "status": "Coleta incompleta",
                                      "visto_em": "2026-10-27T12:00:00Z", "community": "synthetic-secret"}])
        node = graph["nodes"][0]
        for value in ("DNS reverso", "Baixa", "RDP não confirma função", "Coleta incompleta", "2026-10-27T12:00:00Z"):
            self.assertIn(value, node["detail"])
        self.assertNotIn("synthetic-secret", str(graph))
