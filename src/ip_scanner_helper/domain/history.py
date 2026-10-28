"""Validated history snapshots and comparisons without device identity guesses."""

from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
from ipaddress import IPv4Address, IPv4Interface
import json
import math
import re
import unicodedata

from ip_scanner_helper.domain.port_profiles import PortProfile
from ip_scanner_helper.domain.scan_policy import PROBE_TIMEOUT_DEFAULTS
from ip_scanner_helper.domain.targets import MAX_TARGETS

SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
STATUSES = frozenset(("running", "completed", "cancelled", "failed", "interrupted"))
DEVICE_FIELDS = frozenset((
    "ip", "nome", "fabricante", "tipo", "latencia", "latencia_ms", "mac", "origem_mac", "portas",
    "perfil_portas", "portas_previstas_tcp", "origem", "confianca", "evidencia_categoria", "evidencias",
    "status", "coleta_completa", "motivo_coleta_incompleta", "sondas_incompletas", "visto_em",
    "snmp_descr", "ssl_cn", "web_title", "netbios_name", "dns_ptr", "switch_observations", "l2_observation", "l2_last_attempt",
))
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SECRET_PARTS = ("password", "passphrase", "community", "comunidade", "secret", "segredo", "credential",
                 "credencial", "authorization", "cookie", "privatekey", "token")
_TIMEOUT_KEYS = {"target_s", *(key for key, _ in PROBE_TIMEOUT_DEFAULTS)}


def _text(value, limit=8192):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Texto inválido no histórico.")
    return unicodedata.normalize("NFC", "".join(char if ord(char) >= 32 and ord(char) != 127 else " " for char in value))


def validate_environment_id(value):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Identificador do ambiente inválido.")
    return value


def _ip(value):
    if not isinstance(value, str):
        raise ValueError("Endereço IPv4 inválido no histórico.")
    try:
        address = IPv4Address(value)
    except ValueError:
        raise ValueError("Endereço IPv4 inválido no histórico.") from None
    if address.is_multicast or address.is_unspecified or int(address) == 0xFFFFFFFF:
        raise ValueError("Endereço IPv4 inválido no histórico.")
    return str(address)


def _date(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Data inválida no histórico.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Data inválida no histórico.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("As datas do histórico precisam de fuso horário.")
    return parsed.astimezone(timezone.utc).isoformat()


def _integer(value, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError("Contagem inválida no histórico.")
    return value


def _metadata(value, *, depth=0, budget=None):
    """Keep JSON data only; discard credential-bearing keys at every level."""
    if budget is None:
        budget = [500_000]
    budget[0] -= 1
    if budget[0] < 0 or depth > 12:
        raise ValueError("Metadados excedem o limite do histórico.")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or abs(value) > 1e20:
            raise ValueError("Número inválido no histórico.")
        return value
    if isinstance(value, Mapping):
        if len(value) > 256:
            raise ValueError("Metadados excedem o limite do histórico.")
        result = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("Campo inválido no histórico.")
            normalized = re.sub(r"[^a-z]", "", key.casefold())
            if normalized == "key" or any(part in normalized for part in _SECRET_PARTS):
                continue
            clean_key = _text(key, 128)
            result[clean_key] = _metadata(item, depth=depth + 1, budget=budget)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_TARGETS:
            raise ValueError("Metadados excedem o limite do histórico.")
        return [_metadata(item, depth=depth + 1, budget=budget) for item in value]
    raise ValueError("Tipo de metadado inválido no histórico.")


def _context(raw, identifier, targets):
    if not isinstance(raw, Mapping):
        raise ValueError("Contexto de rede inválido no histórico.")
    environment_id = raw.get("environment_id")
    if environment_id is not None:
        environment_id = validate_environment_id(environment_id)
    confirmed = raw.get("environment_confirmed", False)
    if not isinstance(confirmed, bool) or (confirmed and environment_id is None):
        raise ValueError("Confirmação do ambiente inválida no histórico.")
    reusable = confirmed and environment_id is not None
    target_scope = sha256("\n".join(sorted(targets, key=IPv4Address)).encode("ascii")).hexdigest()
    given_scope = raw.get("target_scope")
    if given_scope is not None and given_scope != target_scope:
        raise ValueError("O escopo do histórico não corresponde aos alvos.")
    interface = raw.get("interface") or {}
    if not isinstance(interface, Mapping):
        raise ValueError("Interface inválida no histórico.")
    clean_interface = {key: _text(interface[key], 256) if interface.get(key) is not None else None
                       for key in ("adapter_id", "name")}
    for key in ("address", "gateway"):
        clean_interface[key] = _ip(interface[key]) if interface.get(key) is not None else None
    prefix = interface.get("prefix")
    if prefix is not None:
        prefix = _integer(prefix, 32)
    if (prefix is None) != (clean_interface["address"] is None):
        raise ValueError("Endereço e prefixo da interface devem ser informados juntos.")
    clean_interface["prefix"] = prefix
    clean_interface["network"] = (str(IPv4Interface(f"{clean_interface['address']}/{prefix}").network)
                                  if prefix is not None else None)
    return {
        "schema_version": 1, "environment_id": environment_id,
        "environment_label": _text(raw.get("environment_label", ""), 120),
        "environment_confirmed": confirmed, "environment_reusable": reusable,
        "target_expression": _text(raw.get("target_expression", ""), 256),
        "target_scope": target_scope, "target_count": len(targets), "interface": clean_interface,
        "routing": "system",
        "comparison_scope": f"environment:{environment_id}:{target_scope}" if reusable else f"session:{identifier}",
    }


def _options(raw):
    if not isinstance(raw, Mapping):
        raise ValueError("Opções inválidas no histórico.")
    result = {}
    if "mode" in raw:
        if raw["mode"] not in ("Rápido", "Completo"):
            raise ValueError("Modo inválido no histórico.")
        result["mode"] = raw["mode"]
    if "workers" in raw:
        if not _integer(raw["workers"], 128):
            raise ValueError("Concorrência inválida no histórico.")
        result["workers"] = raw["workers"]
    if "probe_rate_limit" in raw:
        result["probe_rate_limit"] = _integer(raw["probe_rate_limit"], 1000)
    if "probe_metrics" in raw:
        if not isinstance(raw["probe_metrics"], bool):
            raise ValueError("Diagnóstico inválido no histórico.")
        result["probe_metrics"] = raw["probe_metrics"]
    if "port_profile" in raw:
        result["port_profile"] = PortProfile.from_dict(raw["port_profile"]).to_dict()
    if "port_profile_id" in raw:
        result["port_profile_id"] = _text(raw["port_profile_id"], 64)
    if "ports" in raw:
        ports = raw["ports"]
        if not isinstance(ports, (list, tuple)) or not 1 <= len(ports) <= 128:
            raise ValueError("Portas inválidas no histórico.")
        result["ports"] = sorted({_integer(port, 65535) for port in ports})
        if 0 in result["ports"]:
            raise ValueError("Portas inválidas no histórico.")
    if "timeouts" in raw:
        if not isinstance(raw["timeouts"], Mapping):
            raise ValueError("Prazos inválidos no histórico.")
        result["timeouts"] = {}
        for key in _TIMEOUT_KEYS & raw["timeouts"].keys():
            value = raw["timeouts"][key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 300:
                raise ValueError("Prazo inválido no histórico.")
            result["timeouts"][key] = value
    if "target_timeout" in raw:
        value = raw["target_timeout"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 300:
            raise ValueError("Prazo inválido no histórico.")
        result["target_timeout"] = value
    return result


def sanitize_snapshot(snapshot):
    """Return a defensive, bounded snapshot with no credential fields.

    Device labels and category evidence are preserved verbatim after text
    validation. History never reruns classification or merges records by MAC.
    """
    if not isinstance(snapshot, Mapping) or type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        raise ValueError("Versão do histórico não suportada.")
    identifier = validate_environment_id(snapshot.get("id"))
    status = snapshot.get("status")
    if status not in STATUSES:
        raise ValueError("Estado da sessão inválido.")
    started = _date(snapshot.get("started_at"))
    finished = _date(snapshot["finished_at"]) if snapshot.get("finished_at") is not None else None
    if status != "running" and finished is None:
        raise ValueError("Uma sessão encerrada precisa da data de término.")
    if finished is not None and datetime.fromisoformat(finished) < datetime.fromisoformat(started):
        raise ValueError("O término da sessão antecede o início.")
    targets = snapshot.get("targets")
    if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= MAX_TARGETS:
        raise ValueError("Quantidade de alvos inválida no histórico.")
    targets = [_ip(value) for value in targets]
    if len(set(targets)) != len(targets):
        raise ValueError("Alvos repetidos no histórico.")
    targets.sort(key=IPv4Address)
    allowed_targets = set(targets)
    records = snapshot.get("devices", [])
    if not isinstance(records, (list, tuple)) or len(records) > len(targets):
        raise ValueError("Inventário inválido no histórico.")
    devices, seen, budget = [], set(), [500_000]
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("Dispositivo inválido no histórico.")
        address = _ip(raw.get("ip"))
        if address not in allowed_targets or address in seen:
            raise ValueError("Dispositivo fora do escopo ou repetido no histórico.")
        seen.add(address)
        device = _metadata({key: value for key, value in raw.items() if key in DEVICE_FIELDS}, budget=budget)
        device["ip"] = address
        if "coleta_completa" in device and not isinstance(device["coleta_completa"], bool):
            raise ValueError("Cobertura do dispositivo inválida.")
        if "visto_em" in device:
            device["visto_em"] = _date(device["visto_em"])
        devices.append(device)
    devices.sort(key=lambda device: IPv4Address(device["ip"]))
    raw_coverage = snapshot.get("coverage", {})
    if not isinstance(raw_coverage, Mapping):
        raise ValueError("Cobertura inválida no histórico.")
    total = len(targets)
    if raw_coverage.get("total", total) != total:
        raise ValueError("Cobertura e alvos do histórico divergem.")
    coverage = {"total": total, "completed": _integer(raw_coverage.get("completed", 0), total),
                "errors": _integer(raw_coverage.get("errors", 0), total + 1),
                "limited_targets": _integer(raw_coverage.get("limited_targets", 0), total)}
    incomplete = snapshot.get("incomplete_targets", [])
    if not isinstance(incomplete, (list, tuple)) or len(incomplete) > total:
        raise ValueError("Alvos incompletos inválidos no histórico.")
    clean_incomplete, incomplete_seen = [], set()
    for raw in incomplete:
        if not isinstance(raw, Mapping):
            raise ValueError("Alvo incompleto inválido no histórico.")
        address = _ip(raw.get("ip"))
        if address not in allowed_targets or address in incomplete_seen:
            raise ValueError("Alvo incompleto fora do escopo ou repetido.")
        incomplete_seen.add(address)
        item = _metadata({key: value for key, value in raw.items() if key in ("ip", "reason", "probes", "outcome")}, budget=budget)
        item["ip"] = address
        clean_incomplete.append(item)
    result = {"schema_version": SCHEMA_VERSION, "id": identifier, "started_at": started, "finished_at": finished,
              "status": status, "network_context": _context(snapshot.get("network_context", {}), identifier, targets),
              "options": _options(snapshot.get("options", {})), "targets": targets, "devices": devices,
              "coverage": coverage, "incomplete_targets": clean_incomplete}
    if len(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("O histórico excede o tamanho permitido por sessão.")
    return result


def sanitize_reservation(environment_id, ip, label, tags):
    """Reservations belong to an explicitly selected environment, never a CIDR."""
    if not isinstance(tags, (list, tuple)) or len(tags) > 16:
        raise ValueError("Use até 16 etiquetas por reserva.")
    clean_tags = []
    for tag in tags:
        tag = _text(tag, 48).strip()
        if not tag:
            raise ValueError("Etiqueta da reserva inválida.")
        if tag not in clean_tags:
            clean_tags.append(tag)
    return {"environment_id": validate_environment_id(environment_id), "ip": _ip(ip),
            "label": _text(label, 120).strip(), "tags": clean_tags}


def _detection_key(snapshot):
    options = snapshot["options"]
    profile = options.get("port_profile")
    return {
        "mode": options.get("mode"),
        "profile": profile.get("id") if profile else options.get("port_profile_id"),
        "ports": sorted((port["protocol"], port["number"]) for port in profile["ports"]) if profile else options.get("ports"),
        "timeouts": options.get("timeouts"), "target_timeout": options.get("target_timeout"),
        # Scheduling can change the chance of exhausting the target budget.
        "probe_rate_limit": options.get("probe_rate_limit", 0),
    }


def _compatible(first, second):
    if first["id"] == second["id"] and first["targets"] == second["targets"]:
        return True, "Mesma sessão."
    left, right = first["network_context"], second["network_context"]
    if not all(item["environment_reusable"] for item in (left, right)):
        return False, "Confirme o ambiente das duas sessões para compará-las."
    if left["environment_id"] != right["environment_id"]:
        return False, "As sessões pertencem a ambientes diferentes."
    if left["target_scope"] != right["target_scope"]:
        return False, "As sessões consultaram conjuntos de endereços diferentes."
    if _detection_key(first) != _detection_key(second):
        return False, "Modo, portas, prazos ou limite de sondas diferem entre as sessões."
    return True, "Mesmo ambiente confirmado, alvos e opções de detecção."


def _complete(snapshot):
    coverage = snapshot["coverage"]
    return (snapshot["status"] == "completed" and coverage["completed"] == coverage["total"]
            and not coverage["errors"] and not coverage["limited_targets"] and not snapshot["incomplete_targets"]
            and all(device.get("coleta_completa") is True for device in snapshot["devices"]))


def _known_name(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value.casefold() not in ("", "dispositivo ativo", "desconhecido", "não disponível", "nome não encontrado") else None


def _known_mac(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}", value, re.I):
        return None
    return value.replace("-", ":").upper()


def _services(device):
    if device.get("coleta_completa") is not True:
        return None
    value = device.get("portas")
    if not isinstance(value, str) or not value or "incompleta" in value.casefold():
        return None
    if value.startswith("Nenhuma porta TCP"):
        return ()
    return tuple(sorted(item.strip() for item in value.split(" · ") if item.strip()))


def compare_sessions(first, second):
    """Compare by address, recording observations without declaring outages."""
    first, second = sanitize_snapshot(first), sanitize_snapshot(second)
    compatible, reason = _compatible(first, second)
    summary = dict.fromkeys(("new", "name", "mac", "services", "no_response", "inconclusive", "unchanged"), 0)
    rows = []
    if compatible:
        before = {item["ip"]: item for item in first["devices"]}
        after = {item["ip"]: item for item in second["devices"]}

        def add(address, kind, detail):
            summary[kind] += 1
            rows.append({"ip": address, "kind": kind, "before": before.get(address), "after": after.get(address), "detail": detail})

        for address in sorted(before.keys() | after.keys(), key=IPv4Address):
            left, right = before.get(address), after.get(address)
            if left is None:
                add(address, "new", "Endereço observado nesta sessão; não comprova um equipamento novo na rede.")
            elif right is None:
                if _complete(second):
                    add(address, "no_response", "Sem resposta nesta coleta concluída; indisponibilidade não confirmada.")
                else:
                    add(address, "inconclusive", "Sem nova observação; cobertura interrompida, parcial ou com erros.")
            else:
                changes = 0
                for field, kind, transform, detail in (
                    ("nome", "name", _known_name, "Nome observado alterado."),
                    ("mac", "mac", _known_mac, "MAC observado alterado; não confirma conflito ou troca de equipamento."),
                ):
                    old, new = transform(left.get(field)), transform(right.get(field))
                    if old is not None and new is not None and old != new:
                        add(address, kind, detail)
                        changes += 1
                old, new = _services(left), _services(right)
                if old is not None and new is not None and old != new:
                    add(address, "services", "Serviços TCP observados alterados; resultados dependem da cobertura das sondas.")
                    changes += 1
                if not changes:
                    summary["unchanged"] += 1
    return {"compatible": compatible, "reason": reason, "rows": rows, "summary": summary}


def address_rows(snapshot, reservations):
    """Expose every target; silence never becomes an available or offline IP."""
    snapshot = sanitize_snapshot(snapshot)
    context = snapshot["network_context"]
    environment_id = context["environment_id"] if context["environment_reusable"] else None
    reservation_map = {}
    if not isinstance(reservations, (list, tuple)) or len(reservations) > MAX_TARGETS:
        raise ValueError("Reservas inválidas para a visão de endereços.")
    for item in reservations:
        if not isinstance(item, Mapping) or not environment_id or item.get("environment_id") != environment_id:
            continue
        clean = sanitize_reservation(environment_id, item.get("ip"), item.get("label", ""), item.get("tags", []))
        reservation_map[clean["ip"]] = clean
    devices = {item["ip"]: item for item in snapshot["devices"]}
    incomplete = {item["ip"]: item for item in snapshot["incomplete_targets"]}
    complete = _complete(snapshot)
    rows = []
    labels = {"observed": "Observado", "partial": "Coleta parcial", "no_response": "Sem resposta",
              "not_scanned": "Não consultado", "reserved": "Reservado manualmente"}
    for address in snapshot["targets"]:
        device, reservation = devices.get(address), reservation_map.get(address)
        if device is not None:
            state = "observed" if device.get("coleta_completa") is True and address not in incomplete else "partial"
            detail = "Presença observada nesta sessão."
        elif address in incomplete:
            state, detail = "partial", "Coleta inconclusiva para este endereço."
        elif complete:
            state, detail = "no_response", "Nenhuma resposta registrada; disponibilidade não confirmada em DHCP/IPAM."
        else:
            state, detail = "not_scanned", "Sem conclusão individual; a cobertura desta sessão é incompleta."
        if reservation is not None and device is None:
            state = "reserved"
        rows.append({"ip": address, "state": state, "state_label": labels[state], "detail": detail,
                     "device": device, "reserved": reservation is not None,
                     "label": reservation["label"] if reservation else "", "tags": reservation["tags"] if reservation else [],
                     "last_seen": device.get("visto_em", snapshot["started_at"]) if device else None})
    return rows
