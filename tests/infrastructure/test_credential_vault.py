import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from ip_scanner_helper.domain.credentials import CredentialError
from ip_scanner_helper.infrastructure.credential_vault import EncryptedCredentialVault, MAGIC, MAX_VAULT_BYTES
from ip_scanner_helper.infrastructure.windows_dpapi import WindowsDPAPI


class MemoryProtector:
    """Token-based test double; never used by the application as encryption."""
    def __init__(self):
        self.values = {}

    def protect(self, data):
        token = uuid4().bytes
        self.values[token] = data
        return token

    def unprotect(self, data):
        return self.values[data]


class CredentialVaultTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "profile" / "credentials.vault"
        self.protector = MemoryProtector()
        self.vault = EncryptedCredentialVault(self.path, self.protector)

    def test_construction_and_missing_list_create_no_files(self):
        self.assertFalse(self.path.parent.exists())
        self.assertEqual(self.vault.list_credentials(), [])
        self.assertFalse(self.path.parent.exists())

    def test_create_edit_keep_secret_resolve_and_delete_across_instances(self):
        identifier = self.vault.save_credential("", "Lab", "fixture-secret", "Matriz")
        other = EncryptedCredentialVault(self.path, self.protector)
        self.assertEqual(other.list_credentials(), [{"id": identifier, "name": "Lab", "environment": "Matriz"}])
        self.assertNotIn(b"fixture-secret", self.path.read_bytes())
        self.assertEqual(other.resolve(identifier).community, "fixture-secret")
        other.save_credential(identifier, "Renamed", "", "Filial")
        self.assertEqual(self.vault.resolve(identifier).community, "fixture-secret")
        other.save_credential(identifier, "Renamed", "replacement", "Filial")
        self.assertEqual(self.vault.resolve(identifier).community, "replacement")
        self.vault.delete_credential(identifier)
        self.assertEqual(other.list_credentials(), [])
        with self.assertRaises(CredentialError):
            other.resolve(identifier)

    def test_corrupt_or_unreadable_vault_is_not_overwritten(self):
        self.path.parent.mkdir()
        for data in (b"broken", b"ISHVAULT\x99other", b"x" * (MAX_VAULT_BYTES + 1), MAGIC + b"foreign-user"):
            with self.subTest(size=len(data)):
                self.path.write_bytes(data)
                for operation in (lambda: self.vault.list_credentials(), lambda: self.vault.save_credential("", "Lab", "fixture")):
                    with self.assertRaises(CredentialError):
                        operation()
                self.assertEqual(self.path.read_bytes(), data)
        with patch.object(self.vault, "_load", side_effect=PermissionError("synthetic-private")):
            with self.assertRaises(CredentialError) as error:
                self.vault.list_credentials()
            self.assertNotIn("synthetic-private", str(error.exception))

    def test_write_or_protection_failure_preserves_last_file_and_sanitizes_errors(self):
        identifier = self.vault.save_credential("", "Lab", "fixture-secret")
        before = self.path.read_bytes()
        for target in ("replace", "protect"):
            operation = patch("ip_scanner_helper.infrastructure.credential_vault.os.replace", side_effect=OSError("fixture-secret")) if target == "replace" else patch.object(self.protector, "protect", side_effect=RuntimeError("fixture-secret"))
            with operation, self.assertRaises(CredentialError) as error:
                self.vault.save_credential(identifier, "Lab", "replacement")
            self.assertNotIn("fixture-secret", str(error.exception))
            self.assertEqual(self.path.read_bytes(), before)
            self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_duplicate_names_stale_updates_and_cap_are_rejected(self):
        self.vault.save_credential("", "Lab", "fixture")
        with self.assertRaises(CredentialError):
            self.vault.save_credential("", "lab", "fixture")
        with self.assertRaises(CredentialError):
            self.vault.save_credential("a" * 32, "Lab", "fixture")
        for index in range(31):
            self.vault.save_credential("", f"Lab {index}", "fixture")
        with self.assertRaises(CredentialError):
            self.vault.save_credential("", "Overflow", "fixture")
        self.assertEqual(len(self.vault.list_credentials()), 32)

    def test_lock_contention_does_not_overwrite_another_mutation(self):
        self.vault.save_credential("", "Lab", "fixture")
        before = self.path.read_bytes()
        with self.vault._lock():
            with self.assertRaises(CredentialError):
                EncryptedCredentialVault(self.path, self.protector).save_credential("", "Other", "fixture")
        self.assertEqual(self.path.read_bytes(), before)

    @unittest.skipUnless(os.name == "nt", "DPAPI requires Windows")
    def test_real_dpapi_file_survives_new_protector_and_rejects_tampering(self):
        real = EncryptedCredentialVault(self.path, WindowsDPAPI())
        identifier = real.save_credential("", "Native lab", "synthetic-á-secret", "Fictitious environment")
        ciphertext = self.path.read_bytes()
        self.assertNotIn("synthetic-á-secret".encode(), ciphertext)
        self.assertNotIn(b"Native lab", ciphertext)
        self.assertEqual(EncryptedCredentialVault(self.path, WindowsDPAPI()).resolve(identifier).community, "synthetic-á-secret")
        damaged = bytearray(ciphertext)
        damaged[-1] ^= 1
        self.path.write_bytes(damaged)
        with self.assertRaises(CredentialError):
            real.list_credentials()
        self.assertEqual(self.path.read_bytes(), bytes(damaged))
