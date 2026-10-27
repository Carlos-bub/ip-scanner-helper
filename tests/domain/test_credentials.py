from dataclasses import FrozenInstanceError, replace
import unittest

from ip_scanner_helper.application.scanner import ScanOptions
from ip_scanner_helper.domain.credentials import CredentialError, SnmpCredential
from ip_scanner_helper.domain.preferences import Preferences


class CredentialModelTests(unittest.TestCase):
    def test_public_metadata_and_representations_do_not_expose_community(self):
        secret = "fixture-private-community"
        credential = SnmpCredential("a" * 32, "Lab", secret, "Matriz")
        self.assertEqual(credential.metadata(), {"id": "a" * 32, "name": "Lab", "environment": "Matriz"})
        self.assertNotIn(secret, repr(credential))
        self.assertNotIn(secret, repr(ScanOptions(community=secret)))
        self.assertNotIn("community", Preferences(credential_id=credential.id).to_dict())
        with self.assertRaises(FrozenInstanceError):
            credential.community = "other"

    def test_empty_control_excessive_and_malformed_values_are_rejected_without_leaking(self):
        for secret in ("", " ", "private\nsecret", "x" * 256, "á" * 128, "\ud800"):
            with self.subTest(length=len(secret)), self.assertRaises(CredentialError):
                SnmpCredential("a" * 32, "Lab", secret)
        for identifier in ("wrong", "../secret", True):
            with self.assertRaises(CredentialError):
                SnmpCredential(identifier, "Lab", "fixture")

    def test_utf8_and_significant_spaces_are_preserved(self):
        self.assertEqual(SnmpCredential("a" * 32, "Lab", " fixture á ").community, " fixture á ")
        credential = SnmpCredential("a" * 32, "Lab", "fixture", "Conexa\u0303o")
        self.assertEqual(credential.environment, "Conexão")
        with self.assertRaises(ValueError):
            replace(Preferences(), credential_id="invalid")
