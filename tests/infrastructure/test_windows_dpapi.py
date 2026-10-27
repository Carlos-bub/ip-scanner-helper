import ctypes
from types import SimpleNamespace
import unittest

from ip_scanner_helper.domain.credentials import CredentialError
from ip_scanner_helper.infrastructure.windows_dpapi import WindowsDPAPI


class DpapiBoundaryTests(unittest.TestCase):
    def test_current_user_flags_native_memory_release_and_plaintext_clear(self):
        calls, allocations, freed = [], [], []
        def transform(source, description, entropy, reserved, prompt, flags, output):
            calls.append((description, reserved, prompt, flags))
            data = b"native-cipher" if description is not None else b"native-plain"
            allocation = ctypes.create_string_buffer(data)
            allocations.append(allocation)
            output._obj.cbData = len(data)
            output._obj.pbData = ctypes.cast(allocation, ctypes.POINTER(ctypes.c_ubyte))
            return True
        api = WindowsDPAPI()
        api._api = (SimpleNamespace(CryptProtectData=transform, CryptUnprotectData=transform),
                    SimpleNamespace(LocalFree=lambda address: freed.append(address.value)))
        self.assertEqual(api.protect(b"fixture-community"), b"native-cipher")
        self.assertEqual(api.unprotect(b"native-cipher"), b"native-plain")
        self.assertEqual(len(freed), 2)
        self.assertEqual(ctypes.string_at(allocations[1], len(b"native-plain")), b"\0" * len(b"native-plain"))
        self.assertTrue(all(reserved is None and prompt is None and flags == 1 for _, reserved, prompt, flags in calls))
        self.assertIsNone(calls[1][0])

    def test_failed_native_call_has_generic_error_and_bad_input_avoids_api(self):
        api = WindowsDPAPI()
        api._api = (SimpleNamespace(CryptProtectData=lambda *args: False), SimpleNamespace(LocalFree=lambda *args: self.fail("No output to free")))
        with self.assertRaises(CredentialError) as error:
            api.protect(b"fixture-community")
        self.assertNotIn("fixture-community", str(error.exception))
        for value in (b"", "text", b"x" * (256 * 1024 + 1)):
            with self.assertRaises(CredentialError):
                WindowsDPAPI().protect(value)
