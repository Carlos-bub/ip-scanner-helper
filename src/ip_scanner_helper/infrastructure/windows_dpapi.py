"""Current-user DPAPI with explicit signatures and no interactive prompts."""

import ctypes
from ctypes import wintypes
import os

from ip_scanner_helper.domain.credentials import CredentialError

MAX_PROTECTED_BYTES = 256 * 1024
_ENTROPY = b"IPScannerHelper.credentials.v1"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class WindowsDPAPI:
    """Construction performs no native calls or file access."""

    def __init__(self):
        self._api = None

    def _load(self):
        if self._api is not None:
            return self._api
        if os.name != "nt":
            raise CredentialError("O cofre protegido requer o Windows.")
        try:
            crypt = ctypes.WinDLL("crypt32.dll", use_last_error=True)
            kernel = ctypes.WinDLL("kernel32.dll", use_last_error=True)
            tail = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
            crypt.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, *tail]
            crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, *tail]
            crypt.CryptProtectData.restype = crypt.CryptUnprotectData.restype = wintypes.BOOL
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
        except (OSError, AttributeError):
            raise CredentialError("A proteção de credenciais do Windows está indisponível.") from None
        self._api = crypt, kernel
        return self._api

    def _transform(self, data, *, decrypt):
        if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_PROTECTED_BYTES:
            raise CredentialError("Conteúdo do cofre inválido ou excessivo.")
        crypt, kernel = self._load()
        buffer = ctypes.create_string_buffer(data)
        entropy_buffer = ctypes.create_string_buffer(_ENTROPY)
        source = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        entropy = DATA_BLOB(len(_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = DATA_BLOB()
        try:
            function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
            description = None if decrypt else "IP Scanner Helper credentials"
            success = function(ctypes.byref(source), description, ctypes.byref(entropy), None, None,
                               CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output))
            if not success or not output.pbData or not 1 <= output.cbData <= MAX_PROTECTED_BYTES:
                raise CredentialError("Não foi possível abrir ou proteger o cofre com este usuário do Windows.")
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            ctypes.memset(buffer, 0, ctypes.sizeof(buffer))
            if output.pbData:
                if decrypt and output.cbData <= MAX_PROTECTED_BYTES:
                    ctypes.memset(output.pbData, 0, output.cbData)
                kernel.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))

    def protect(self, data):
        return self._transform(data, decrypt=False)

    def unprotect(self, data):
        return self._transform(data, decrypt=True)
