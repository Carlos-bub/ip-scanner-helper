"""Bounded SNMP table traversal; failures preserve data and explicit coverage."""

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled, TargetBudgetExceeded
from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.infrastructure.network.snmp import SnmpError, SnmpAgentError, oid_parts, query


class WalkResult(dict):
    def __init__(self):
        super().__init__()
        self.partial = False
        self.reason = ""
        self.requests = 0
        self.fallback = False
        self.unsupported = False

    def coverage(self):
        return {"entries": len(self), "partial": self.partial, "reason": self.reason,
                "requests": self.requests, "fallback": self.fallback, "unsupported": self.unsupported}


def walk_tree(ip, community, root_oid, timeout=.6, max_reps=4096, budget=3, *,
              context=None, version=1, bulk=True, query_fn=query):
    result = WalkResult()
    root = oid_parts(root_oid)
    current = root
    context = context.child(budget) if context is not None else ProbeContext.standalone(budget)
    repetitions = 12 if bulk and version == 1 else None
    # At most a bounded number of reductions and one GETNEXT fallback per walk.
    while len(result) < max_reps:
        try:
            context.check()
            result.requests += 1
            kwargs = {"version": version, "timeout": timeout, "context": context}
            if repetitions is None:
                kwargs["next_oid"] = True
            else:
                kwargs["bulk_repetitions"] = min(repetitions, max_reps - len(result))
            values = query_fn(ip, ".".join(map(str, current)), community, **kwargs)
            if not values:
                raise SnmpError("Resposta sem variáveis")
            # One requested repeater cannot legitimately return more than requested.
            if len(values) > (kwargs.get("bulk_repetitions") or 1):
                raise SnmpError("Resposta excede repetições solicitadas")
            for oid, tag, value in values:
                if tag in (0x80, 0x81, 0x82):
                    result.unsupported = not result and tag in (0x80, 0x81)
                    return result
                parts = oid_parts(oid)
                if parts <= current:
                    raise SnmpError("OID repetido ou fora de ordem")
                if parts[:len(root)] != root:
                    return result
                result[oid] = value
                current = parts
        except (ScanCancelled, ProbeTimeout, TargetBudgetExceeded) as exc:
            result.partial = True
            result.reason = "cancelada" if isinstance(exc, ScanCancelled) else "tempo máximo da coleta"
            break
        except (OSError, SnmpError) as exc:
            if version == 0 and isinstance(exc, SnmpAgentError) and exc.status == 2:
                result.unsupported = not result
                return result
            if repetitions is not None:
                # tooBig, timeouts, broken bulk agents: retry smaller, then GETNEXT.
                # Access errors are not a reason to retry with a different PDU.
                if isinstance(exc, SnmpAgentError) and exc.status not in (1, 5):
                    result.partial, result.reason = True, "acesso negado ou erro do agente SNMP"
                    break
                repetitions = (repetitions // 2 if repetitions > 1 else None) if isinstance(exc, SnmpAgentError) and exc.status == 1 else None
                result.fallback = True
                continue
            result.partial, result.reason = True, "falha de comunicação ou resposta SNMP inválida"
            break
    else:
        result.partial, result.reason = True, "limite de entradas"
    return result
