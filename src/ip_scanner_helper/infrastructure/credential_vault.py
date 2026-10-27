"""Encrypted whole-file vault, atomic writes and cooperative process locking."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from ip_scanner_helper.domain.credentials import CredentialError, MAX_CREDENTIALS, SnmpCredential, valid_credential_id
from ip_scanner_helper.application.ports import SecretProtector

MAGIC = b"ISHVAULT\x01"
MAX_VAULT_BYTES = 128 * 1024


class EncryptedCredentialVault:
    def __init__(self, path, protector: SecretProtector):
        self.path = Path(path)
        self.protector = protector

    def _load(self):
        try:
            with self.path.open("rb") as source:
                raw = source.read(MAX_VAULT_BYTES + 1)
        except FileNotFoundError:
            return ()
        if len(raw) > MAX_VAULT_BYTES or not raw.startswith(MAGIC):
            raise CredentialError("O cofre está inválido ou usa uma versão não suportada. O arquivo foi preservado.")
        try:
            plain = self.protector.unprotect(raw[len(MAGIC):])
            if len(plain) > MAX_VAULT_BYTES:
                raise ValueError()
            payload = json.loads(plain.decode("utf-8"))
            if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
                raise ValueError()
            items = payload.get("credentials")
            if not isinstance(items, list) or len(items) > MAX_CREDENTIALS:
                raise ValueError()
            entries = tuple(SnmpCredential(**entry) for entry in items)
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError()
            return entries
        except Exception:
            raise CredentialError("Não foi possível abrir o cofre. Verifique o arquivo e o usuário do Windows; o original foi preservado.") from None

    @contextmanager
    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+b") as lock:
            if lock.seek(0, 2) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                unlock = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                unlock = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            try:
                yield
            finally:
                lock.seek(0)
                unlock()

    def _save(self, entries):
        payload = {"schema_version": 1, "credentials": [dict(entry.metadata(), community=entry.community) for entry in entries]}
        plaintext = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            protected = self.protector.protect(plaintext)
        except Exception:
            raise CredentialError("O Windows não pôde proteger o cofre. O arquivo anterior foi preservado.") from None
        data = MAGIC + protected
        if not isinstance(protected, bytes) or not len(MAGIC) < len(data) <= MAX_VAULT_BYTES:
            raise CredentialError("O cofre excede o limite ou não pôde ser protegido.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".credentials-", suffix=".tmp", dir=self.path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def list_credentials(self):
        try:
            return [entry.metadata() for entry in self._load()]
        except Exception:
            raise CredentialError("O cofre não pôde ser lido. O arquivo foi preservado; confira o usuário do Windows e as permissões.") from None

    def resolve(self, identifier):
        try:
            if not valid_credential_id(identifier):
                raise CredentialError()
            entry = next((entry for entry in self._load() if entry.id == identifier), None)
            if entry is None:
                raise CredentialError()
            return entry
        except Exception:
            raise CredentialError("A credencial selecionada está indisponível. Escolha outra credencial ou a entrada manual.") from None

    def save_credential(self, identifier, name, community, environment=""):
        try:
            if identifier and not valid_credential_id(identifier):
                raise CredentialError("Identificador da credencial inválido.")
            with self._lock():
                entries = list(self._load())
                previous = next((entry for entry in entries if entry.id == identifier), None)
                if identifier and previous is None:
                    raise CredentialError("A credencial não existe mais. Atualize a lista.")
                entry = SnmpCredential(identifier or uuid4().hex, name,
                                       previous.community if previous is not None and community == "" else community, environment)
                if any(item.id != entry.id and (item.name.casefold(), item.environment) == (entry.name.casefold(), entry.environment) for item in entries):
                    raise CredentialError("Já existe uma credencial com esse nome e ambiente.")
                entries = [entry if item.id == identifier else item for item in entries] if previous else [*entries, entry]
                if len(entries) > MAX_CREDENTIALS:
                    raise CredentialError(f"Use até {MAX_CREDENTIALS} credenciais.")
                self._save(entries)
                return entry.id
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Não foi possível salvar o cofre. O arquivo anterior foi preservado; confira as permissões e se outra instância está usando o cofre.") from None

    def delete_credential(self, identifier):
        try:
            if not valid_credential_id(identifier):
                raise CredentialError("Identificador da credencial inválido.")
            with self._lock():
                entries = self._load()
                remaining = tuple(entry for entry in entries if entry.id != identifier)
                if len(remaining) == len(entries):
                    raise CredentialError("A credencial não existe mais. Atualize a lista.")
                self._save(remaining)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Não foi possível remover a credencial. O cofre anterior foi preservado.") from None
