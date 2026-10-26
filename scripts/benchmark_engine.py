"""Full scanner/coordinator benchmark with all network collectors replaced by fixtures."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from queue import Empty
from threading import Event
from types import SimpleNamespace
import sys
import time
import tracemalloc

from ip_scanner_helper.application.scan_service import ScanService
from ip_scanner_helper.application.scanner import ScanOptions

COLLECTORS = ("obter_mac_e_presenca_windows", "ping_measurement", "scan_ports", "query_snmp",
              "query_dns_ptr", "query_netbios", "query_pjl_printer_model", "query_onvif_ws_discovery",
              "query_http_title", "query_sip_voip", "query_rdp_hostname", "query_ssh_banner",
              "query_ftp_banner", "query_ssl_certificate", "query_ssdp_device")


class Fixture:
    def __init__(self, scenario):
        self.scenario = scenario
        self.entered_slow_dns = Event()

    def collector(self, name):
        def call(ip, *args, **kwargs):
            index = int(ip.rsplit(".", 1)[-1])
            group = index % 4
            active = self.scenario != "unresponsive" and (self.scenario != "mixed" or group != 0)
            snmp_only = self.scenario == "snmp_only" or (self.scenario == "mixed" and group == 3)
            tcp_only = self.scenario == "icmp_blocked" or (self.scenario == "mixed" and group == 2)
            if name == "obter_mac_e_presenca_windows":
                return ("02:00:00:00:00:01", True) if active and not snmp_only and not tcp_only else (None, False)
            if name == "ping_measurement":
                return (True, 2.0) if active and not snmp_only and not tcp_only else (False, None)
            if name == "scan_ports":
                return (["HTTP(80)", "HTTPS(443)", "SSH(22)", "RAW-Print(9100)"]
                        if active and not snmp_only else [])
            if name == "query_snmp":
                return (f"SW-{index}", "Managed switch", "SNMP v2c") if active and snmp_only else (None, None, None)
            if name == "query_dns_ptr":
                if self.scenario == "errors" and index % 7 == 0:
                    raise OSError("Simulated DNS failure")
                if self.scenario == "slow_dns":
                    self.entered_slow_dns.set()
                    time.sleep(.007)
                return f"host-{index}.example" if active and not snmp_only and not tcp_only else None
            if name == "query_http_title":
                return "Fixture login", 80
            if name == "query_ssl_certificate":
                return "fixture.example", 443
            return None
        return call


def run_case(scenario, count, workers=32, *, cancel=False, probe_metrics=False):
    fixture = Fixture(scenario)
    resolver = SimpleNamespace(carregar_arp_cache=lambda: {},
                               **{name: fixture.collector(name) for name in COLLECTORS})
    service = ScanService(resolver=resolver)
    final_devices = {}
    first_result = first_complete = cancel_started = None
    summary = None
    tracemalloc.start()
    started, cpu_start = time.monotonic(), time.process_time()
    try:
        service.start([f"198.18.{i // 254}.{i % 254 + 1}" for i in range(count)],
                      ScanOptions(workers=workers, mode="Completo", probe_metrics=probe_metrics))
        deadline = started + 30
        while summary is None:
            if cancel and cancel_started is None and fixture.entered_slow_dns.is_set():
                cancel_started = time.monotonic()
                service.cancel()
            if time.monotonic() > deadline:
                service.cancel()
                raise RuntimeError("Fixture exceeded its deadline")
            try:
                event = service.events.get(timeout=.002)
            except Empty:
                continue
            if event.kind == "device":
                first_result = first_result if first_result is not None else time.monotonic() - started
                device = event.payload["device"]
                if device.get("coleta_completa", True):
                    first_complete = first_complete if first_complete is not None else time.monotonic() - started
                    final_devices[device["ip"]] = device
            elif event.kind == "finished":
                summary = event.payload
        service.thread.join(timeout=2)
        assert not service.running
        duration = time.monotonic() - started
        cpu = time.process_time() - cpu_start
        _, peak = tracemalloc.get_traced_memory()
    finally:
        service.cancel()
        if service.thread:
            service.thread.join(timeout=2)
        tracemalloc.stop()
    signature = [(ip, item["nome"], item["tipo"], item["portas"], item["latencia"], item["origem"])
                 for ip, item in sorted(final_devices.items())]
    return {"scenario": scenario, "targets": count, "workers": workers,
            "duration_s": round(duration, 6), "cpu_process_s": round(cpu, 6),
            "first_result_s": round(first_result, 6) if first_result is not None else None,
            "first_complete_s": round(first_complete, 6) if first_complete is not None else None,
            "python_peak_allocations_mib": round(peak / 1024**2, 3),
            "completed": summary["completed"], "errors": summary["errors"],
            "cancelled": summary["cancelled"], "final_devices": len(final_devices),
            "cancel_to_finish_s": round(time.monotonic() - cancel_started, 6) if cancel_started else None,
            "coverage_sha256": hashlib.sha256(json.dumps(signature).encode()).hexdigest(),
            "metrics": summary.get("metrics")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--probe-metrics", action="store_true", help="Include detailed per-probe timings and outcomes")
    args = parser.parse_args()
    logger = logging.getLogger("ip_scanner_helper.application.scan_service")
    previous_level = logger.level
    logger.setLevel(logging.CRITICAL)  # Errors are intentional fixtures and counted in the report.
    rows = []
    try:
        for scenario in ("unresponsive", "mixed", "icmp_blocked", "snmp_only", "slow_dns", "errors"):
            for count in (32, 254, 1024, 4096):
                row = run_case(scenario, count, probe_metrics=args.probe_metrics)
                rows.append(row)
                print(f"{scenario:13} {count:4}: {row['duration_s']:.3f}s; final={row['final_devices']}; errors={row['errors']}", flush=True)
        cancellation = run_case("slow_dns", 254, cancel=True, probe_metrics=args.probe_metrics)
    finally:
        logger.setLevel(previous_level)
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        for old, current in zip(baseline["rows"], rows, strict=True):
            assert (old["scenario"], old["targets"]) == (current["scenario"], current["targets"])
            assert old["coverage_sha256"] == current["coverage_sha256"], current
            assert old["errors"] == current["errors"], current
        print("Coverage and errors match the baseline in all scenarios.", flush=True)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "probe_metrics_enabled": args.probe_metrics,
              "scope": "Real scanner/coordinator with simulated collectors; no network packets",
              "memory_metric": "tracemalloc Python allocations, not process RSS",
              "fixture_dns_delay_ms": 7, "rows": rows, "cancellation": cancellation}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
