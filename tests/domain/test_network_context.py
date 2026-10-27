from dataclasses import FrozenInstanceError
import unittest

from ip_scanner_helper.domain.interfaces import LocalInterface
from ip_scanner_helper.domain.network_context import NetworkContext


class NetworkContextTests(unittest.TestCase):
    targets = ("192.0.2.1", "192.0.2.2")

    def test_same_range_and_adapter_are_isolated_without_confirmed_environment(self):
        context = NetworkContext.for_scan("192.0.2.1-192.0.2.2", LocalInterface("Ethernet", "192.0.2.3", 24, "192.0.2.254", "adapter"))
        first, second = context.snapshot("first", self.targets), context.snapshot("second", self.targets)
        self.assertNotEqual(first["comparison_scope"], second["comparison_scope"])
        self.assertFalse(first["environment_reusable"])
        self.assertEqual(first["interface"]["network"], "192.0.2.0/24")
        self.assertEqual(first["routing"], "system")

    def test_explicit_environment_and_actual_targets_define_comparison(self):
        context = NetworkContext.for_scan("192.0.2.1-192.0.2.2", environment_label="Matriz", environment_confirmed=True)
        first = context.snapshot("first", self.targets)
        second = context.snapshot("second", reversed(self.targets))
        self.assertEqual(first["comparison_scope"], second["comparison_scope"])
        other = NetworkContext.for_scan("192.0.2.1-192.0.2.2", environment_label="Filial", environment_confirmed=True)
        self.assertNotEqual(first["comparison_scope"], other.snapshot("third", self.targets)["comparison_scope"])

    def test_manual_target_has_no_invented_interface(self):
        snapshot = NetworkContext.for_scan("192.0.2.1").snapshot("one", ["192.0.2.1"])
        self.assertTrue(all(value is None for value in snapshot["interface"].values()))

    def test_target_mismatch_and_unconfirmed_identity_are_rejected(self):
        with self.assertRaises(ValueError):
            NetworkContext.for_scan("192.0.2.1").snapshot("one", ["192.0.2.2"])
        with self.assertRaises(ValueError):
            NetworkContext(environment_confirmed=True)
        with self.assertRaises(FrozenInstanceError):
            NetworkContext().gateway = "192.0.2.1"

    def test_unicode_equivalence_does_not_merge_distinct_names(self):
        make = NetworkContext.named_environment_id
        self.assertEqual(make("Conexão"), make("Conexa\u0303o"))
        self.assertNotEqual(make("matriz"), make("Matriz"))
        self.assertNotEqual(make("ß"), make("ss"))
