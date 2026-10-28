"""Regressions for ambiguous, conflicting and source-specific observations."""

import unittest

from ip_scanner_helper.domain.classification import UNKNOWN, classify_device


class ClassificationTests(unittest.TestCase):
    def test_explicit_server_and_workstation_descriptions(self):
        cases = (
            ("Windows Server 2022 Standard", "Servidor"),
            ("Software: Windows Version 6.3 (Build 20348 Multiprocessor Free)", "Servidor"),
            ("Windows 11 Pro Workstation", "Estação"),
            ("Software: Windows Version 6.3 (Build 22631 Multiprocessor Free)", "Estação"),
        )
        for description, category in cases:
            with self.subTest(description=description):
                self.assertEqual(classify_device(description, {445, 80})[:2], (category, "Alta"))

    def test_distribution_and_ftp_software_do_not_prove_server_role(self):
        for key, values in {
            "description": ("Debian GNU/Linux", "Red Hat Enterprise Linux", "FreeBSD",
                            "Build 9600", "Windows Version 10.0 (Build 19041)",
                            "Windows Version 10.0 (Build 19042)"),
            "ssh": ("SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.6", "OpenSSH Debian"),
            "ftp": ("220 FileZilla Server", "220 vsftpd", "220 ProFTPD", "Microsoft IIS FTP"),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    kwargs = {key: value} if key != "description" else {}
                    result = classify_device(value if key == "description" else None, {21, 22, 80}, **kwargs)
                    self.assertEqual(result[:2], (UNKNOWN, "Baixa"))

    def test_short_signatures_require_word_boundaries(self):
        self.assertEqual(classify_device("Windows 11 Pro pilot workstation", {445})[:2], ("Estação", "Alta"))
        for text in ("pilot dashboard", "switching application", "axis analytics", "TP-Link", "UniFi"):
            with self.subTest(text=text):
                self.assertEqual(classify_device(None, {80}, web=text)[0], UNKNOWN)

    def test_explicit_description_beats_ports_and_hostname_hypotheses(self):
        for ports in ({631, 445}, {8000}, {5060}, {1433, 443}):
            with self.subTest(ports=ports):
                self.assertEqual(classify_device("Windows 11 Pro Workstation", ports, name="SRV-LAB")[:2], ("Estação", "Alta"))

    def test_snmp_camera_and_phone_descriptions_are_recognized(self):
        for description, category in (("Hikvision Network Camera", "CFTV"),
                                      ("Yealink SIP-T46U IP Phone", "Telefonia IP")):
            with self.subTest(description=description):
                result = classify_device(description, set())
                self.assertEqual(result[:2], (category, "Alta"))
                self.assertIn("SNMP", result[2])

    def test_device_signatures_across_categories(self):
        for description, category in (("HP LaserJet printer", "Impressora"),
                                      ("Managed switch", "Switch"),
                                      ("MikroTik RouterOS", "Roteador / Firewall"),
                                      ("Wireless access point", "Access Point / Wi-Fi")):
            with self.subTest(description=description):
                self.assertEqual(classify_device(description, set())[:2], (category, "Alta"))

    def test_dedicated_protocols_preserve_their_evidence(self):
        for key, value, category in (("pjl", "LaserJet M404", "Impressora"),
                                     ("onvif", "Câmera ONVIF: Lab", "CFTV")):
            with self.subTest(key=key):
                result = classify_device(None, set(), **{key: value})
                self.assertEqual(result[:2], (category, "Alta"))
                self.assertIn(key.upper(), result[2])

    def test_sip_describes_function_and_does_not_override_explicit_os(self):
        self.assertEqual(classify_device(None, set(), sip="Asterisk")[:2], ("Telefonia IP", "Média"))
        self.assertEqual(classify_device("Windows 11", set(), sip="Softphone")[:2], ("Estação", "Alta"))

    def test_hypervisor_management_interface_is_explicit_evidence(self):
        result = classify_device(None, {443}, web="pve01 - Proxmox Virtual Environment")
        self.assertEqual(result[:2], ("Servidor", "Alta"))
        self.assertIn('Título Web: assinatura "proxmox"', result[2])

    def test_generic_hostname_prefixes_and_asset_numbers_do_not_set_category(self):
        for hostname in ("administracao-01", "apple-01", "admin", "camera-ready", "switching-lab",
                         "colab-01.empresa.local", "20102-mecanica4.rdcblda.com"):
            with self.subTest(hostname=hostname):
                self.assertEqual(classify_device(None, set(), name=hostname)[0], UNKNOWN)

    def test_structured_hostname_conventions_preserved(self):
        for hostname, category in (("FIN-PC01", "Estação"), ("MATRIZ-SRV01", "Servidor"),
                                   ("SRV-ARQUIVOS", "Servidor"), ("DC01", "Servidor"),
                                   ("AP-01", "Access Point / Wi-Fi"), ("SW24", "Switch"),
                                   ("CAM-01", "CFTV"), ("BRN001122aabbcc", "Impressora")):
            with self.subTest(hostname=hostname):
                self.assertEqual(classify_device(None, set(), name=hostname)[:2], (category, "Média"))

    def test_hostname_source_is_preserved_and_suffix_is_not_a_role(self):
        result = classify_device(None, set(), dns="PC01.example.local.")
        self.assertEqual(result[:2], ("Estação", "Média"))
        self.assertIn("DNS reverso (PTR)", result[2])
        self.assertEqual(classify_device(None, set(), dns="host.server.example")[0], UNKNOWN)
        self.assertEqual(classify_device(None, set(), name="SRV example")[0], UNKNOWN)

    def test_oui_alone_does_not_prove_role(self):
        for vendor in ("Dell Inc.", "VMware Inc.", "VMware ESXi", "Intel Corporate", "HP Enterprise",
                       "TP-Link", "Hikvision", "Samsung Electronics"):
            with self.subTest(vendor=vendor):
                self.assertEqual(classify_device(None, set(), vendor=vendor)[:2], (UNKNOWN, "Baixa"))

    def test_open_ports_never_prove_device_role(self):
        for ports in ({445}, {3389, 445}, {445, 443}, {53, 80}, {22, 80},
                      {443}, {445, 1433}, {631}, {8000}, {554}, {5060}):
            for vendor in (None, "Desconhecido", "Dell Inc.", "TP-Link"):
                with self.subTest(ports=ports, vendor=vendor):
                    self.assertEqual(classify_device(None, ports, vendor=vendor)[:2], (UNKNOWN, "Baixa"))

    def test_services_do_not_change_explicit_hostname_role(self):
        result = classify_device(None, {445, 443, 1433}, name="PC-LAB", ssh="OpenSSH Ubuntu")
        self.assertEqual(result[:2], ("Estação", "Média"))

    def test_strong_conflicts_are_inconclusive_instead_of_first_match_wins(self):
        for kwargs in ({"description": "Windows 11 Pro", "onvif": "ONVIF camera"},
                       {"description": "Windows 11 Pro", "web": "Proxmox Virtual Environment"},
                       {"description": "Windows 11 Windows Server 2022"}):
            with self.subTest(kwargs=kwargs):
                result = classify_device(ports=set(), **kwargs)
                self.assertEqual(result[:2], (UNKNOWN, "Baixa"))
                self.assertIn("contraditórias", result[2])

    def test_conflicting_hostnames_are_inconclusive_regardless_of_order(self):
        for names in ({"name": "PC-LAB", "netbios": "SRV-LAB"},
                      {"name": "SRV-LAB", "netbios": "PC-LAB"},
                      {"dns": "PC-LAB.example", "netbios": "SRV-LAB"}):
            with self.subTest(names=names):
                self.assertEqual(classify_device(None, set(), **names)[:2], (UNKNOWN, "Baixa"))

    def test_independent_agreeing_sources_are_reported(self):
        result = classify_device("Windows Server 2022", set(), web="Windows Admin Center")
        self.assertEqual(result[:2], ("Servidor", "Alta"))
        self.assertIn("Descrição SNMP", result[2])
        self.assertIn("Título Web", result[2])


if __name__ == "__main__":
    unittest.main()
