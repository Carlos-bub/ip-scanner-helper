"""Documentation-only addresses, explicit environments, no real network data."""
from copy import deepcopy
from dataclasses import asdict

from ip_scanner_helper.application.scanner import ScanOptions
from ip_scanner_helper.domain.network_context import NetworkContext


def snapshot(identifier="session-1", **changes):
    targets = ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
    options = ScanOptions()
    result = {"schema_version": 1, "id": identifier, "started_at": "2026-10-28T12:00:00+00:00",
              "finished_at": "2026-10-28T12:00:02+00:00", "status": "completed",
              "network_context": NetworkContext.for_scan("192.0.2.1-192.0.2.3", environment_id="lab-a",
                  environment_label="Laboratório A", environment_confirmed=True).snapshot(identifier, targets),
              "options": {"mode": options.mode, "workers": options.workers, "timeouts": asdict(options.timeouts),
                          "port_profile": options.port_profile.to_dict(), "probe_rate_limit": 0},
              "targets": targets, "devices": [{"ip": "192.0.2.1", "nome": "SW-A", "tipo": "Switch",
                  "mac": "02:00:00:00:00:01", "coleta_completa": True, "portas": "HTTPS(443)",
                  "visto_em": "2026-10-28T12:00:01+00:00"}],
              "coverage": {"completed": 3, "total": 3, "errors": 0, "limited_targets": 0}, "incomplete_targets": []}
    result.update(deepcopy(changes))
    return result
