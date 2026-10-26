from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from threading import Event
import time
import unittest

from ip_scanner_helper.application.observations import (PROBES, ProbeObservation, ProbeRecorder, ScanCancelled, ScanMetrics)


class ObservationTests(unittest.TestCase):
    def test_tuple_without_response_is_not_a_success_and_skipped_probes_are_explicit(self):
        records = []
        with ProbeRecorder(Event(), records.append) as recorder:
            recorder.call("snmp", lambda: (None, None, None))
            recorder.call("http", lambda: (None, 443))
            recorder.call("icmp", lambda: (True, "< 1 ms"))
        by_name = {item.probe: item for item in records}
        self.assertEqual(by_name["snmp"].outcome, "no_result")
        self.assertEqual(by_name["http"].outcome, "no_result")
        self.assertEqual(by_name["icmp"].outcome, "result")
        self.assertEqual(by_name["dns_ptr"].outcome, "not_run")
        self.assertIsNone(by_name["dns_ptr"].started_at)
        self.assertIn("+00:00", by_name["icmp"].started_at)
        self.assertEqual(len(records), len(PROBES))

    def test_exception_records_error_and_preserves_the_original_exception(self):
        records = []
        with self.assertRaisesRegex(OSError, "fixture error"):
            with ProbeRecorder(Event(), records.append) as recorder:
                recorder.call("dns_ptr", lambda: (_ for _ in ()).throw(OSError("fixture error")))
        self.assertEqual(next(item for item in records if item.probe == "dns_ptr").outcome, "error")

    def test_pre_cancelled_call_is_not_executed_or_mislabeled_as_no_response(self):
        records, called, cancelled = [], [], Event()
        cancelled.set()
        with self.assertRaises(ScanCancelled), ProbeRecorder(cancelled, records.append) as recorder:
            recorder.call("arp", lambda: called.append(True))
        self.assertFalse(called)
        self.assertEqual(next(item for item in records if item.probe == "arp").outcome, "cancelled")

    def test_parallel_aggregation_and_returned_snapshot_are_isolated(self):
        metrics = ScanMetrics()
        record = ProbeObservation("tcp", "result", "2026-10-26T00:00:00+00:00", .002)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(metrics.observe, [record] * 200))
        metrics.found()
        report = metrics.snapshot(time.monotonic() - .01)
        self.assertEqual(report["probes"]["tcp"]["result"], 200)
        self.assertAlmostEqual(report["probes"]["tcp"]["duration_s"], .4)
        self.assertIsNotNone(report["first_result_s"])
        self.assertGreaterEqual(report["cancel_to_finish_s"], .01)
        report["probes"]["tcp"]["result"] = -1
        self.assertEqual(metrics.snapshot()["probes"]["tcp"]["result"], 200)
        self.assertEqual(set(asdict(record)), {"probe", "outcome", "started_at", "duration_s"})
        self.assertNotIn("community", json.dumps(report))
