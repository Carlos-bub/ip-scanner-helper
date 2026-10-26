"""Command line entry point for the Qt Quick desktop application."""

import argparse

from core.logging_config import configure_logging


def main(argv=None):
    parser = argparse.ArgumentParser(description="IP Scanner Helper · inventário de rede para Windows")
    parser.add_argument("--demo", action="store_true", help="Exibe dados fictícios sem sondar a rede")
    parser.add_argument("--self-check", action="store_true", help="Valida a interface com dados fictícios e encerra")
    parser.add_argument("--screenshot", help="Salva uma captura da interface em PNG")
    parser.add_argument("--log-dir", help="Diretório dos logs")
    args = parser.parse_args(argv)
    configure_logging(args.log_dir)
    from ui.qt_app import run
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
