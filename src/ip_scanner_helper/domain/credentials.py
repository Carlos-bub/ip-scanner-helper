"""Validated SNMP credentials; public metadata never contains the community."""

from dataclasses import dataclass, field
import re
import unicodedata

MAX_CREDENTIALS = 32


class CredentialError(Exception):
    """User-safe vault failure; messages must never include secret values."""


def valid_credential_id(value, *, allow_empty=False):
    return isinstance(value, str) and ((allow_empty and value == "") or bool(re.fullmatch(r"[0-9a-f]{32}", value)))


def _label(value, maximum, *, optional=False):
    if (not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip())
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise CredentialError("Nome ou ambiente da credencial inválido.")
    return unicodedata.normalize("NFC", value.strip())


@dataclass(frozen=True)
class SnmpCredential:
    id: str
    name: str
    community: str = field(repr=False)
    environment: str = ""

    def __post_init__(self):
        if not valid_credential_id(self.id):
            raise CredentialError("Identificador da credencial inválido.")
        object.__setattr__(self, "name", _label(self.name, 64))
        object.__setattr__(self, "environment", _label(self.environment, 120, optional=True))
        try:
            size = len(self.community.encode("utf-8")) if isinstance(self.community, str) else 0
        except UnicodeError:
            raise CredentialError("Comunidade SNMP com codificação inválida.") from None
        if (not isinstance(self.community, str) or not self.community.strip() or not 1 <= size <= 255
                or any(ord(char) < 32 or ord(char) == 127 for char in self.community)):
            raise CredentialError("Informe uma comunidade SNMP de 1 a 255 bytes, sem caracteres de controle.")

    def metadata(self):
        return {"id": self.id, "name": self.name, "environment": self.environment}
