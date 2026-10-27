from dataclasses import FrozenInstanceError, replace
import unittest

from ip_scanner_helper.domain.port_profiles import BUILTIN_PROFILES, PortProfile, ServicePort, STANDARD_PROFILE, UDP_SERVICES
from ip_scanner_helper.domain.preferences import Preferences


class PortProfileTests(unittest.TestCase):
    def test_standard_preserves_original_ports_order_and_labels(self):
        self.assertEqual(STANDARD_PROFILE.tcp_mapping(), {21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 443: "HTTPS",
                         445: "SMB", 5060: "SIP-VoIP", 515: "LPD-Print", 3389: "RDP", 8080: "HTTP-Alt", 8443: "HTTPS-Alt", 9100: "RAW-Print"})
        self.assertEqual(len(BUILTIN_PROFILES), 5)

    def test_custom_editor_roundtrip_and_immutable_ports(self):
        profile = PortProfile.from_text("custom-lab", "Aplicações", " 8088 Minha aplicação  \n65535   \n\n")
        self.assertEqual(profile.tcp_mapping(), {8088: "Minha aplicação", 65535: "TCP-65535"})
        self.assertEqual(PortProfile.from_dict(profile.to_dict()), profile)
        self.assertEqual(PortProfile.from_text(profile.id, profile.name, profile.ports_text()), profile)
        with self.assertRaises(FrozenInstanceError):
            profile.ports[0].number = 80

    def test_bad_ports_and_ambiguous_editor_inputs_are_rejected(self):
        for text in ("", "0 HTTP", "65536 Test", "80 HTTP\n80 Outra", "80-90", "udp/161 SNMP", "80 Label(test)", "80 " + "x" * 49,
                     "\n".join(str(port) for port in range(1, 130))):
            with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                PortProfile.from_text("custom-lab", "Lab", text)
        for number in (True, 80.1, "80"):
            with self.subTest(number=number), self.assertRaises(ValueError):
                ServicePort("tcp", number, "Test")

    def test_udp_is_separate_from_tcp_profiles(self):
        self.assertIn(ServicePort("udp", 161, "SNMP"), UDP_SERVICES)
        self.assertIn(ServicePort("udp", 3702, "WS-Discovery"), UDP_SERVICES)
        for profile in BUILTIN_PROFILES:
            self.assertTrue(all(port.protocol == "tcp" for port in profile.ports))
            self.assertNotIn(3702, profile.tcp_mapping())
        with self.assertRaises(ValueError):
            PortProfile("custom-lab", "Lab", (ServicePort("udp", 161, "SNMP"),))

    def test_preferences_roundtrip_preserves_profile_and_probe_times(self):
        profile = PortProfile.from_text("custom-lab", "Lab", "8088 App")
        prefs = replace(Preferences(), custom_port_profiles=(profile,), port_profile_id=profile.id,
                        probe_timeouts=(("tcp", .8), ("dns_ptr", 4.5)))
        self.assertEqual(Preferences.from_dict(prefs.to_dict()), prefs)
        self.assertEqual(prefs.port_profile, profile)
        self.assertEqual(dict(prefs.probe_timeouts)["snmp"], .35)

    def test_stale_duplicate_reserved_profiles_and_invalid_times_are_rejected(self):
        profile = PortProfile.from_text("custom-lab", "Lab", "8088 App")
        for fields in ({"port_profile_id": "missing"}, {"custom_port_profiles": (profile, profile)},
                       {"custom_port_profiles": (STANDARD_PROFILE,)}, {"probe_timeouts": (("fake", 1),)},
                       {"probe_timeouts": (("tcp", float("inf")),)}, {"probe_timeouts": (("snmp", True),)},
                       {"probe_timeouts": (("tcp", .2), ("tcp", .3))}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                replace(Preferences(), **fields)
