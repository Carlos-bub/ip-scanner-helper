"""Small, strict BER codec shared by the SNMP discovery and switch mapper.

Only SNMP v1/v2c GET/GETNEXT and response values used by this project are supported.
Unsupported packets fail explicitly instead of being interpreted as empty tables.
"""

from dataclasses import dataclass
import secrets
import socket


class SnmpError(ValueError):
    """Malformed packet, mismatched response or SNMP agent error."""


def encode_tlv(tag: int, value: bytes) -> bytes:
    length = len(value)
    size = length.to_bytes(max(1, (length.bit_length() + 7) // 8), "big")
    header = bytes([length]) if length < 128 else bytes([0x80 | len(size)]) + size
    return bytes([tag]) + header + value


def _base128(value: int) -> bytes:
    chunks = [value & 127]
    while value > 127:
        value >>= 7
        chunks.insert(0, (value & 127) | 128)
    return bytes(chunks)


def oid_parts(oid: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in oid.strip(".").split("."))
    if len(parts) < 2 or parts[0] not in (0, 1, 2) or min(parts) < 0:
        raise SnmpError("OID inválido")
    if parts[0] < 2 and parts[1] > 39:
        raise SnmpError("Segundo componente do OID inválido")
    return parts


def encode_oid(oid: str) -> bytes:
    parts = oid_parts(oid)
    return _base128(parts[0] * 40 + parts[1]) + b"".join(_base128(p) for p in parts[2:])


def decode_oid(data: bytes) -> str:
    values = []
    value = 0
    for byte in data:
        value = (value << 7) | (byte & 127)
        if not byte & 128:
            values.append(value)
            value = 0
    if not values or data[-1] & 128:
        raise SnmpError("OID truncado")
    first = values.pop(0)
    root = min(2, first // 40)
    return ".".join(map(str, [root, first - root * 40, *values]))


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def read(self, expected=None):
        if self.offset + 2 > len(self.data):
            raise SnmpError("Cabeçalho BER truncado")
        tag, length = self.data[self.offset:self.offset + 2]
        self.offset += 2
        if length & 128:
            count = length & 127
            if not 1 <= count <= 4 or self.offset + count > len(self.data):
                raise SnmpError("Comprimento BER inválido")
            length = int.from_bytes(self.data[self.offset:self.offset + count], "big")
            self.offset += count
        end = self.offset + length
        if end > len(self.data) or (expected is not None and tag != expected):
            raise SnmpError("Valor BER inválido ou truncado")
        value = self.data[self.offset:end]
        self.offset = end
        return tag, value

    def done(self):
        if self.offset != len(self.data):
            raise SnmpError("Dados BER excedentes")


@dataclass(frozen=True)
class Response:
    request_id: int
    community: bytes
    version: int
    values: tuple


def parse_response(data: bytes) -> Response:
    packet = Reader(data)
    message = Reader(packet.read(0x30)[1])
    packet.done()
    version = int.from_bytes(message.read(2)[1], "big", signed=True)
    if version not in (0, 1):
        raise SnmpError("Versão SNMP não suportada")
    community = message.read(4)[1]
    pdu = Reader(message.read(0xA2)[1])
    message.done()
    request_id = int.from_bytes(pdu.read(2)[1], "big", signed=True)
    error = int.from_bytes(pdu.read(2)[1], "big")
    pdu.read(2)
    if error:
        raise SnmpError(f"Agente SNMP retornou erro {error}")
    bindings = Reader(pdu.read(0x30)[1])
    pdu.done()
    values = []
    while bindings.offset < len(bindings.data):
        binding = Reader(bindings.read(0x30)[1])
        oid = decode_oid(binding.read(6)[1])
        tag, raw = binding.read()
        binding.done()
        value = raw
        if tag in (2, 0x41, 0x42, 0x43, 0x46):
            value = int.from_bytes(raw, "big", signed=tag == 2)
        elif tag == 6:
            value = decode_oid(raw)
        values.append((oid, tag, value))
    return Response(request_id, community, version, tuple(values))


def build_request(oid, community="public", version=1, request_id=101, next_oid=False):
    if version not in (0, 1) or not 0 <= request_id < 2**31:
        raise SnmpError("Versão ou identificador SNMP inválido")
    binding = encode_tlv(0x30, encode_tlv(6, encode_oid(oid)) + b"\x05\x00")
    rid = request_id.to_bytes(max(1, (request_id.bit_length() + 8) // 8), "big")
    pdu = encode_tlv(0xA1 if next_oid else 0xA0,
                     encode_tlv(2, rid) + b"\x02\x01\x00" * 2 + encode_tlv(0x30, binding))
    return encode_tlv(0x30, encode_tlv(2, bytes([version]))
                      + encode_tlv(4, community.encode("utf-8")) + pdu)


def query(ip, oid, community="public", version=1, timeout=0.5, next_oid=False, *, context=None):
    request_id = secrets.randbelow(2**30)
    packet = build_request(oid, community, version, request_id, next_oid)
    # A connected UDP socket only accepts datagrams from the selected endpoint.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(context.timeout(timeout) if context is not None else timeout)
        sock.connect((ip, 161))
        sock.send(packet)
        if context is not None:
            sock.settimeout(context.timeout(timeout))
        response = parse_response(sock.recv(65535))
    if (response.request_id != request_id or response.version != version
            or response.community != community.encode("utf-8")):
        raise SnmpError("Resposta SNMP não corresponde à consulta")
    return response.values
