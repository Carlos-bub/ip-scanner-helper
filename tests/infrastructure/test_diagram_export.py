from ipaddress import IPv4Address
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from ip_scanner_helper.domain.topology import build_topology_graph
from ip_scanner_helper.infrastructure.diagram_export import diagram_groups_layout, export_diagram, render_dot, render_drawio


class DiagramExportTests(unittest.TestCase):
    def fixture(self):
        return [{"ip": "192.0.2.1", "nome": "SW-01", "tipo": "Switch"},
                {"ip": "192.0.2.2", "nome": "SW-02", "tipo": "Switch"},
                {"ip": "192.0.2.10", "nome": "Estação ç", "tipo": "Estação / Servidor", "switch_observations": [
                    {"switch_ip": "192.0.2.1", "port": "Gi1", "source": "SNMP", "observed_at": "2026-10-27T12:00:00Z"},
                    {"switch_ip": "192.0.2.2", "port": "Gi2"}, {"switch_ip": "192.0.2.254", "port": "24"}]}]

    def test_drawio_has_two_editable_pages_and_valid_references_for_all_paths(self):
        document = ET.fromstring(render_drawio(self.fixture(), "192.0.2.253"))
        self.assertEqual(document.tag, "mxfile")
        self.assertEqual([page.get("name") for page in document.findall("diagram")], ["Categorias", "Caminhos e vizinhos"])
        for page in document.findall("diagram"):
            objects = page.findall(".//object")
            identifiers = {item.get("id") for item in objects} | {"0", "1"}
            self.assertEqual(len(identifiers), len(objects) + 2)
            paths = [item for item in objects if item.get("kind") == "fdb_path"]
            self.assertEqual(len(paths), 3)
            for edge in paths:
                cell = edge.find("mxCell")
                self.assertIn(cell.get("source"), identifiers)
                self.assertIn(cell.get("target"), identifiers)
                self.assertEqual(edge.get("direct_link_confirmed"), "false")
                self.assertNotEqual(cell.get("source"), "gateway-context")
            for item in objects:
                self.assertIn(item.find("mxCell").get("parent"), identifiers)
            self.assertTrue(any(item.get("kind") == "observer_reference" for item in objects))
            metadata = next(item for item in paths if item.get("source") == "SNMP")
            self.assertEqual(metadata.get("observed_at"), "2026-10-27T12:00:00Z")

    def test_absence_of_evidence_never_adds_an_edge_in_either_format(self):
        devices = [{"ip": "192.0.2.1", "tipo": "Switch"}, {"ip": "192.0.2.10"}]
        xml = ET.fromstring(render_drawio(devices, "192.0.2.254"))
        self.assertFalse(xml.findall('.//mxCell[@edge="1"]'))
        self.assertNotIn(" -> ", render_dot(devices, "192.0.2.254"))
        self.assertFalse(ET.fromstring(render_drawio([])).findall('.//object[@kind="device"]'))

    def test_xml_hostile_labels_are_plain_text_and_controls_are_replaced(self):
        payload = 'x"/><mxCell id="injected"/> & </script>\x00ç'
        xml = render_drawio([{"ip": "192.0.2.1", "nome": payload, "community": "synthetic-secret"}])
        document = ET.fromstring(xml)
        self.assertFalse(document.findall('.//mxCell[@id="injected"]'))
        node = document.find('.//object[@kind="device"]')
        self.assertIn(payload.replace("\x00", "\ufffd"), node.get("label"))
        self.assertTrue(all("html=0" in cell.get("style", "") for cell in document.findall('.//object/mxCell')))
        self.assertNotIn("synthetic-secret", xml)
        self.assertIn("&lt;mxCell", node.get("tooltip"))
        self.assertNotIn("<mxCell", node.get("tooltip"))

    def test_dot_quotes_do_not_allow_statement_or_html_injection(self):
        payload = 'x" ]; attacker -> victim; //\n<IMG SRC="remote">\\N'
        result = render_dot([{"ip": "192.0.2.1", "nome": payload}])
        self.assertIn('x\\" ]; attacker -> victim; //\\n<IMG SRC=\\"remote\\">\\\\N', result)
        self.assertEqual(result.count("subgraph cluster_"), 1)
        self.assertNotIn('label=<', result)
        self.assertNotIn('\n<IMG', result)

    def test_dot_retains_parallel_and_external_paths_and_metadata(self):
        result = render_dot(self.fixture(), "192.0.2.253")
        self.assertEqual(result.count('kind="fdb_path"'), 3)
        self.assertIn('"192.0.2.1" -> "192.0.2.10"', result)
        self.assertIn('"192.0.2.2" -> "192.0.2.10"', result)
        self.assertIn('"192.0.2.254" -> "192.0.2.10"', result)
        self.assertIn("Observador fora do inventário", result)
        self.assertIn("2026-10-27T12:00:00Z", result)
        self.assertNotIn('"192.0.2.253" ->', result)

    def test_export_preserves_full_inventory_and_unequal_groups_do_not_overlap(self):
        devices = [{"ip": str(IPv4Address("10.0.0.1") + i), "tipo": "Impressora" if i % 10 else "Switch"}
                   for i in range(500)]
        graph = build_topology_graph(devices)
        placements, height = diagram_groups_layout(graph["groupings"]["category"], columns=1)
        for a, b in zip(placements, placements[1:]):
            self.assertLessEqual(a["y"] + a["height"], b["y"])
        self.assertGreater(height, placements[-1]["y"] + placements[-1]["height"])
        document = ET.fromstring(render_drawio(devices))
        self.assertEqual(len(document.findall('.//object[@kind="device"]')), 500)

    def test_drawio_and_xml_are_the_same_format_and_unknown_type_does_not_create_a_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            for kind in ("drawio", "xml", "dot"):
                export_diagram(path / ("map." + kind), self.fixture(), "192.0.2.253", kind)
            self.assertEqual((path / "map.drawio").read_bytes(), (path / "map.xml").read_bytes())
            self.assertIn("digraph", (path / "map.dot").read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                export_diagram(path / "bad", self.fixture(), None, "bad")
            self.assertFalse((path / "bad").exists())
