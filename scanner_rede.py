"""
Enterprise Network & Switch Scanner (Entry Point & Compatibilidade).
Redireciona para o módulo principal (main.py).
"""

from main import main
from core.resolver import NetworkResolver
from core.oui_database import OUI_DATABASE, identificar_fabricante_e_tipo


if __name__ == "__main__":
    raise SystemExit(main())
