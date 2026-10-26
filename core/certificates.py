"""Extract subject attributes structurally; issuer names are not host names."""

from core.snmp import Reader, SnmpError, decode_oid


def subject_attributes(der: bytes) -> dict[str, str]:
    certificate = Reader(der)
    envelope = Reader(certificate.read(0x30)[1])
    certificate.done()
    body = Reader(envelope.read(0x30)[1])
    if body.data and body.data[0] == 0xA0:
        body.read(0xA0)  # optional explicit version
    body.read(2)  # serial number
    body.read(0x30)  # signature algorithm
    body.read(0x30)  # issuer: deliberately ignored
    body.read(0x30)  # validity
    subject = Reader(body.read(0x30)[1])
    attributes = {}
    encodings = {0x0C: "utf-8", 0x13: "ascii", 0x14: "latin1", 0x16: "ascii", 0x1E: "utf-16-be"}
    while subject.offset < len(subject.data):
        rdn = Reader(subject.read(0x31)[1])
        while rdn.offset < len(rdn.data):
            pair = Reader(rdn.read(0x30)[1])
            oid = decode_oid(pair.read(6)[1])
            tag, value = pair.read()
            pair.done()
            if tag in encodings:
                attributes[oid] = value.decode(encodings[tag], errors="replace").strip()
    return attributes


def certificate_name(der: bytes):
    try:
        attributes = subject_attributes(der)
        return next((attributes[oid] for oid in ("2.5.4.3", "2.5.4.10", "2.5.4.11")
                     if attributes.get(oid)), None)
    except (SnmpError, UnicodeError):
        return None
