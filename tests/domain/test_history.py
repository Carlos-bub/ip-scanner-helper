from copy import deepcopy
import json
import unittest

from ip_scanner_helper.domain.history import sanitize_snapshot, compare_sessions, address_rows
from tests.history_fixtures import snapshot


class HistoryDomainTests(unittest.TestCase):
    def test_snapshot_drops_secrets_at_every_level_and_preserves_classification(self):
        value = snapshot()
        value["community"] = value["options"]["community"] = "synthetic-secret"
        value["devices"][0].update(tipo="Servidor de teste", password="synthetic-secret",
                                    l2_observation={"neighbors": [{"remote_name": "peer", "password": "synthetic-secret"}]})
        original = deepcopy(value)
        clean = sanitize_snapshot(value)
        self.assertEqual(value, original)
        self.assertNotIn("synthetic-secret", json.dumps(clean))
        self.assertEqual(clean["devices"][0]["tipo"], "Servidor de teste")
        self.assertEqual(sanitize_snapshot(clean), clean)

    def test_normalizes_timezones_and_rejects_scope_mismatch_and_duplicates(self):
        value = snapshot(started_at="2026-10-28T09:00:00-03:00")
        self.assertEqual(sanitize_snapshot(value)["started_at"], "2026-10-28T12:00:00+00:00")
        value["targets"].append("192.0.2.1")
        with self.assertRaises(ValueError): sanitize_snapshot(value)
        value = snapshot()
        value["network_context"]["target_scope"] = "wrong"
        with self.assertRaises(ValueError): sanitize_snapshot(value)

    def test_compares_names_macs_services_without_reclassifying_or_merging(self):
        left, right = snapshot(), snapshot("session-2")
        right["devices"][0].update(nome="Novo nome", mac="02:00:00:00:00:02", portas="SSH(22)")
        result = compare_sessions(left, right)
        self.assertTrue(result["compatible"])
        self.assertEqual({row["kind"] for row in result["rows"]}, {"name", "mac", "services"})
        self.assertEqual(len(result["rows"]), 3)

    def test_blocks_other_environments_unconfirmed_scope_and_different_profiles(self):
        for mutation in ("environment", "unconfirmed", "ports", "mode", "timeouts", "rate"):
            right = snapshot("session-2")
            if mutation == "environment": right["network_context"]["environment_id"] = "lab-b"
            elif mutation == "unconfirmed": right["network_context"]["environment_confirmed"] = False
            elif mutation == "ports": right["options"]["port_profile"]["ports"] = [{"protocol": "tcp", "number": 1, "service": "test"}]
            elif mutation == "mode": right["options"]["mode"] = "Rápido"
            elif mutation == "timeouts": right["options"]["timeouts"]["target_s"] = 1
            else: right["options"]["probe_rate_limit"] = 10
            with self.subTest(mutation=mutation): self.assertFalse(compare_sessions(snapshot(), right)["compatible"])

    def test_partial_cancelled_or_failed_absence_is_inconclusive(self):
        for state in ("cancelled", "failed", "interrupted", "running"):
            right = snapshot("session-2", status=state, devices=[])
            result = compare_sessions(snapshot(), right)
            self.assertEqual(result["rows"][0]["kind"], "inconclusive")
        result = compare_sessions(snapshot(), snapshot("session-2", devices=[]))
        self.assertEqual(result["rows"][0]["kind"], "no_response")
        self.assertNotIn("offline", json.dumps(result).lower())

    def test_addresses_include_every_target_and_keep_reservations_isolated(self):
        reservations = [{"environment_id": "lab-a", "ip": "192.0.2.2", "label": "Impressora", "tags": ["TI"]},
                        {"environment_id": "lab-b", "ip": "192.0.2.3", "label": "Outra rede", "tags": []}]
        rows = address_rows(snapshot(), reservations)
        self.assertEqual([row["state"] for row in rows], ["observed", "reserved", "no_response"])
        self.assertFalse(rows[2]["reserved"])
        rows = address_rows(snapshot(status="cancelled", devices=[]), [])
        self.assertTrue(all(row["state"] == "not_scanned" for row in rows))

    def test_invalid_or_future_snapshot_is_rejected(self):
        for changes in ({"schema_version": 2}, {"id": "bad/id"}, {"finished_at": None}, {"targets": []},
                        {"started_at": "2026-10-28"}, {"devices": [{"ip": "192.0.2.200"}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): sanitize_snapshot(snapshot(**changes))

    def test_partial_device_prevents_full_coverage_claim_for_missing_addresses(self):
        first = snapshot()
        first["devices"].append({"ip": "192.0.2.2", "nome": "PC", "coleta_completa": True})
        second = snapshot("session-2")
        second["devices"][0]["coleta_completa"] = False
        result = compare_sessions(first, second)
        self.assertEqual(next(row["kind"] for row in result["rows"] if row["ip"] == "192.0.2.2"), "inconclusive")
