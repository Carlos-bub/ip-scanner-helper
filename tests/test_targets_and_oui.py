import ast
from pathlib import Path
import unittest

from core.oui_database import identificar_fabricante_e_tipo
from core.targets import parse_targets


class TargetsTests(unittest.TestCase):
    def test_single_range_and_cidr(self):
        self.assertEqual(parse_targets("192.0.2.1"), ["192.0.2.1"])
        self.assertEqual(parse_targets("192.0.2.1 - 192.0.2.2"), ["192.0.2.1", "192.0.2.2"])
        self.assertEqual(parse_targets("192.0.2.0/30"), ["192.0.2.1", "192.0.2.2"])

    def test_point_to_point_and_host_prefix(self):
        self.assertEqual(len(parse_targets("192.0.2.0/31")), 2)
        self.assertEqual(parse_targets("192.0.2.1/32"), ["192.0.2.1"])

    def test_large_network_rejected_before_expansion(self):
        for value in ("0.0.0.0/0", "10.0.0.0/8", "1.0.0.1 - 255.255.255.254"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Limite"):
                parse_targets(value)

    def test_invalid_targets(self):
        for value in ("", "foo", "192.0.2.2-192.0.2.1", "224.0.0.1", "255.255.255.255", "0.0.0.0", "192.0.2.1--192.0.2.2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_targets(value)


class OuiTests(unittest.TestCase):
    def test_unknown_prefix_is_not_approximated(self):
        self.assertEqual(identificar_fabricante_e_tipo("00:03:00:00:00:01")[0], "Fabricante Não Mapeado")

    def test_private_mac_is_not_a_smartphone(self):
        vendor, category = identificar_fabricante_e_tipo("02:00:00:00:00:01")
        self.assertIn("privado", vendor)
        self.assertEqual(category, "Dispositivo não identificado")

    def test_exact_vendor_does_not_imply_category(self):
        vendor, category = identificar_fabricante_e_tipo("00-03-93-00-00-01")
        self.assertEqual(vendor, "Apple Inc.")
        self.assertEqual(category, "Dispositivo não identificado")

    def test_invalid_mac_does_not_produce_vendor(self):
        self.assertEqual(identificar_fabricante_e_tipo("invalid")[0], "Desconhecido")

    def test_oui_table_has_no_duplicate_keys(self):
        source = Path(__file__).resolve().parents[1] / "core" / "oui_database.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign))
        keys = [ast.literal_eval(key) for key in assignment.value.keys]
        self.assertEqual(len(keys), len(set(keys)))
