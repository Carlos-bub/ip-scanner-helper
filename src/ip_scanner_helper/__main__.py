"""Support python -m ip_scanner_helper and the frozen Windows entry point."""

from ip_scanner_helper.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
