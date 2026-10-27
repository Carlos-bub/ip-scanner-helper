"""Command line entry point for the Qt Quick desktop application."""

import argparse

from ip_scanner_helper.infrastructure.logging_config import configure_logging
from ip_scanner_helper.bootstrap import create_desktop_services, create_scan_service, create_preferences_store, create_credential_vault


def main(argv=None):
    parser = argparse.ArgumentParser(description="IP Scanner Helper · inventário de rede para Windows")
    parser.add_argument("--demo", action="store_true", help="Exibe dados fictícios sem sondar a rede")
    parser.add_argument("--self-check", action="store_true", help="Valida a interface com dados fictícios e encerra")
    parser.add_argument("--screenshot", help="Salva uma captura da interface em PNG")
    parser.add_argument("--log-dir", help="Diretório dos logs")
    args = parser.parse_args(argv)
    configure_logging(args.log_dir)
    from ip_scanner_helper.presentation.qt_app import run
    return run(args, service=create_scan_service(), desktop=create_desktop_services(),
               preferences_store=None if args.demo or args.self_check else create_preferences_store(),
               credential_vault=None if args.demo or args.self_check else create_credential_vault())


if __name__ == "__main__":
    raise SystemExit(main())
