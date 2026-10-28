from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import Mock
import unittest

from PySide6.QtCore import QCoreApplication

from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.domain.l2 import identity
from ip_scanner_helper.presentation.qt_controller import ScannerController


def sample():
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "local_chassis": identity(7, b"SW-A"),
            "neighbors": [{"protocol": "LLDP", "remote_name": "Printer", "management_addresses": ["192.0.2.11"],
                           "remote_chassis": identity(7, b"peer"), "remote_port": identity(5, b"eth0", port=True),
                           "local_port": {"name": "Gi1", "identity": identity(5, b"Gi1", port=True)}}],
            "vlan_ports": [{"name": "Gi1", "bridge_port": 3, "if_index": 101, "pvid": 10,
                            "tagged": [20], "untagged": [10], "membership_complete": True}],
            "vlan_issues": [], "coverage": {"lldp_remote": {"entries": 8, "requests": 1, "partial": False,
                                                           "reason": "", "unsupported": False, "fallback": False}},
            "partial": False, "cancelled": False}


class L2ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.collector = Mock()
        self.controller = ScannerController(Mock(), replace(create_desktop_services(), l2_collector=self.collector), demo=True)
        self.addCleanup(self.controller.close)
        self.controller.demo = False
        self.controller._data["demo"] = False
        self.controller.selectRow(0)
        self.controller._inventory_context = {"comparison_scope": "session:fixture", "interface": {"address": "192.0.2.100"}}

    def test_manual_action_captures_ip_credential_and_context_before_async_work(self):
        c = self.controller
        c._async = Mock()
        self.collector.collect.return_value = sample()
        c.collectL2("fixture-secret")
        self.assertTrue(c.state["l2Busy"])
        operation, callback = c._async.call_args.args[1:]
        c._inventory_context["interface"]["address"] = "192.0.2.200"
        c.selectRow(1)
        result = operation()
        self.assertEqual(self.collector.collect.call_args.args, ("192.0.2.2", "fixture-secret"))
        self.assertFalse(self.collector.collect.call_args.kwargs["context"].cancelled.is_set())
        callback(result, None)
        host = next(item for item in c.devices if item["ip"] == "192.0.2.2")
        self.assertEqual(host["l2_observation"]["network_context"]["interface"]["address"], "192.0.2.100")
        self.assertEqual(c.state["l2Neighbors"][0]["address"], "192.0.2.11")
        self.assertEqual(c.state["l2Vlans"][0]["bridgePort"], "3")
        self.assertNotIn("fixture-secret", str(c.state))
        self.assertFalse(c.state["l2Busy"])

    def test_cancel_and_scan_reset_signal_worker_and_discard_stale_completion(self):
        c = self.controller
        c._async = Mock()
        c.collectL2("public")
        operation = c._async.call_args.args[1]
        c.cancelL2()
        operation()
        self.assertTrue(self.collector.collect.call_args.kwargs["context"].cancelled.is_set())
        c._data["l2Busy"] = False
        c.collectL2("public")
        c._jobs["l2"] = "old-token"
        old_cancel = c._l2_cancel
        c.service.start.return_value = "new-session"
        c.setTarget("192.0.2.1")
        c.startScan("public", 2)
        self.assertTrue(old_cancel.is_set())
        self.assertNotIn("l2", c._jobs)
        self.assertFalse(c.state["l2Busy"])

    def test_failure_and_empty_cancel_do_not_erase_previous_observation(self):
        c = self.controller
        original = deepcopy(sample())
        c.devices[0]["l2_observation"] = original
        context = deepcopy(c._inventory_context)
        c._received_l2(c.devices[0]["ip"], context, None, "generic error")
        self.assertEqual(c.devices[0]["l2_observation"], original)
        empty = sample()
        empty.update(partial=True, cancelled=True, neighbors=[], vlan_ports=[], local_chassis=identity(None, None))
        c._received_l2(c.devices[0]["ip"], context, empty, None)
        self.assertEqual(c.devices[0]["l2_observation"], original)
        self.assertTrue(c.devices[0]["l2_last_attempt"]["cancelled"])
        self.assertIn("preservada", c.state["l2Status"])
        self.assertFalse(c.state["l2Neighbors"])

    def test_demo_scan_or_other_switch_job_prevent_collection(self):
        c = self.controller
        c._async = Mock()
        for key in ("demo", "scanning", "switchBusy", "l2Busy"):
            if key == "demo":
                c.demo = True
            else:
                c._data[key] = True
            c.collectL2("public")
            c.demo = False
            c._data[key] = False
        c._async.assert_not_called()
