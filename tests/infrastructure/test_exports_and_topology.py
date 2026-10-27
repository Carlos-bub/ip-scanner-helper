import csv
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

from ip_scanner_helper.infrastructure.exporters import export_csv, export_json
from ip_scanner_helper.domain.topology import build_topology_graph
from ip_scanner_helper.infrastructure.html_topology import gerar_html_topologia_interativa, render_example_topology


class ExportTests(unittest.TestCase):
    def test_fictional_hierarchy_and_offline_states_are_isolated_from_collected_graphs(self):
        output = render_example_topology()
        sample = json.loads(re.search(r'<script id="graph-data" type="application/json">(.*?)</script>', output, re.S)[1])
        self.assertTrue(sample["example"])
        self.assertEqual(len(sample["nodes"]), 129)
        self.assertTrue(any(node["state"] == "offline" for node in sample["nodes"]))
        self.assertTrue(all(edge["kind"] == "example_link" for edge in sample["tree_links"]))
        actual = build_topology_graph([{"ip": "192.0.2.1", "state": "offline"}])
        self.assertNotIn("tree_links", actual)
        self.assertNotIn("example", actual)
        self.assertEqual(actual["nodes"][0]["state"], "observed")

    def test_csv_handles_metadata_and_neutralizes_formulas(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "out.csv"
            export_csv(path, [{"ip": "192.0.2.1", "nome": " =HYPERLINK(1)", "evidencias": ["ICMP"]}])
            with path.open(encoding="utf-8-sig", newline="") as file:
                row = next(csv.DictReader(file, delimiter=";"))
            self.assertTrue(row["nome"].startswith("'"))
            self.assertEqual(json.loads(row["evidencias"]), ["ICMP"])

    def test_json_preserves_unicode_and_types(self):
        data = [{"nome": "Estação", "latencia_ms": None, "evidencias": ["ARP"]}]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            export_json(path, data)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), data)

    def test_html_escapes_script_breakout_and_round_trips_data(self):
        payload = '</script><script>alert("x")</script> & __GATEWAY__'
        devices = [{"ip": "192.0.2.1", "nome": payload, "tipo": "Estação"}]
        output = gerar_html_topologia_interativa(devices, "192.0.2.254")
        self.assertNotIn(payload, output)
        data = re.search(r'<script id="graph-data" type="application/json">(.*?)</script>', output, re.S)[1]
        self.assertEqual(json.loads(data)["nodes"][0]["nome"], payload)
        self.assertNotIn("__TOPOLOGY_LAYOUT__", output)
        self.assertNotIn("__TOPOLOGY_MAP__", output)
        self.assertNotIn("unpkg.com", output)
        self.assertNotIn("innerHTML", output)

    def test_topology_does_not_assign_hosts_to_arbitrary_switches(self):
        graph = build_topology_graph([{"ip": "192.0.2.1", "tipo": "Switch"}, {"ip": "192.0.2.2", "tipo": "Estação"}])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(len(graph["nodes"]), 2)

    def test_fdb_observation_does_not_claim_direct_link(self):
        graph = build_topology_graph([
            {"ip": "192.0.2.1", "tipo": "Switch"},
            {"ip": "192.0.2.2", "switch_observations": [{"switch_ip": "192.0.2.1", "port": "Gi1/0/2"}]}])
        observed = next(edge for edge in graph["edges"] if edge["observed"])
        self.assertIn("não confirmado", observed["label"])

    def test_invalid_ips_do_not_become_nodes(self):
        graph = build_topology_graph([{"ip": "192.0.2.1 & calc"}])
        self.assertEqual(graph["nodes"], [])
