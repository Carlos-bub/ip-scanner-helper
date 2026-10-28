import unittest

from ip_scanner_helper.domain.inventory import identity_source, inventory_metrics, matches_device, sorted_devices


class InventoryTests(unittest.TestCase):
    def test_search_includes_ports_and_ignores_accents(self):
        device = {"nome": "Estação Recepção", "portas": "HTTPS(443)", "tipo": "Estação / Servidor"}
        self.assertTrue(matches_device(device, "recepcao 443"))
        self.assertFalse(matches_device(device, "recepcao 22"))

    def test_incomplete_filters_are_independent_of_vendor(self):
        device = {"nome": "Dispositivo ativo", "mac": "Desconhecido", "tipo": "Dispositivo não identificado", "fabricante": "Apple"}
        for quality in ("Sem nome", "Sem MAC", "Categoria não identificada"):
            self.assertTrue(matches_device(device, quality=quality))
        self.assertEqual(inventory_metrics([device]), {"total": 1, "sem_nome": 1, "sem_mac": 1, "sem_categoria": 1})

    def test_numeric_latency_keeps_unmeasured_last_both_directions(self):
        devices = [{"ip": "a", "latencia": "10 ms"}, {"ip": "b", "latencia": "2 ms"},
                   {"ip": "c", "latencia": "Não medida"}, {"ip": "d", "latencia": "< 1 ms"}]
        self.assertEqual([d["ip"] for d in sorted_devices(devices, "latencia")], ["d", "b", "a", "c"])
        self.assertEqual([d["ip"] for d in sorted_devices(devices, "latencia", True)], ["a", "b", "d", "c"])

    def test_numeric_ip_order(self):
        devices = [{"ip": "192.0.2.10"}, {"ip": "192.0.2.2"}]
        self.assertEqual(sorted_devices(devices)[0]["ip"], "192.0.2.2")

    def test_web_title_is_not_labeled_as_hostname(self):
        label, note = identity_source({"nome": "Web Management", "origem": "Título Web"})
        self.assertEqual(label, "Título da interface Web")
        self.assertIn("não comprova", note)

    def test_category_is_combined_with_quality(self):
        device = {"nome": "Printer", "tipo": "Impressora", "mac": "Desconhecido"}
        self.assertTrue(matches_device(device, category="PRINTER", quality="Sem MAC"))
        self.assertFalse(matches_device(device, category="SWITCH", quality="Sem MAC"))

    def test_workstation_and_server_filters_are_distinct(self):
        workstation = {"nome": "PC-01", "tipo": "Estação"}
        server = {"nome": "SRV-01", "tipo": "Servidor"}
        self.assertTrue(matches_device(workstation, category="ESTACAO"))
        self.assertFalse(matches_device(workstation, category="SERVIDOR"))
        self.assertTrue(matches_device(server, category="SERVIDOR"))
        self.assertFalse(matches_device(server, category="ESTACAO"))
