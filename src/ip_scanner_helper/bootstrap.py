"""Composition root: bind application contracts to concrete implementations."""

from ip_scanner_helper.application.ports import DesktopServices
from ip_scanner_helper.application.scan_service import ScanService
from ip_scanner_helper.application.scanner import scan_device
from ip_scanner_helper.infrastructure.exporters import export_csv, export_json
from ip_scanner_helper.infrastructure.html_topology import gerar_html_topologia_interativa
from ip_scanner_helper.infrastructure.diagram_export import export_diagram
from ip_scanner_helper.infrastructure.network.interfaces import discover_interfaces
from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver
from ip_scanner_helper.infrastructure.network.switch_port_mapper import SwitchPortMapper
from ip_scanner_helper.infrastructure.preferences import JsonPreferencesStore, default_settings_path
from ip_scanner_helper.infrastructure.credential_vault import EncryptedCredentialVault
from ip_scanner_helper.infrastructure.windows_dpapi import WindowsDPAPI


def create_credential_vault():
    return EncryptedCredentialVault(default_settings_path().with_name("credentials.vault"), WindowsDPAPI())


def create_preferences_store():
    return JsonPreferencesStore(default_settings_path())


def create_scan_service(worker=scan_device):
    return ScanService(resolver=NetworkResolver(), worker=worker)


def create_desktop_services():
    return DesktopServices(
        discover_interfaces=discover_interfaces,
        export_csv=export_csv,
        export_json=export_json,
        render_map=gerar_html_topologia_interativa,
        switch_mapper=SwitchPortMapper(),
        export_diagram=export_diagram,
    )
