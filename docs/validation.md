# Validação local — versão 2.0.0 — 2026-10-23

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials / Qt 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| `.venv\Scripts\python -m unittest discover -s tests -v` | 65 testes aprovados, incluindo 13 contratos novos do controlador Qt |
| Instalação editável com `pip install --no-build-isolation --no-deps -e .` | Pacote 2.0.0 e comando de entrada instalados no ambiente local |
| `.venv\Scripts\python scripts/smoke_ui.py` | QML real; cliques, setas, Enter, duplo clique, seleção simples, busca, colunas, menus, opções compactas, switches e varredura simulada aprovados |
| `.venv\Scripts\python scripts/capture_desktop.py` | Tabela em toda a largura, detalhes sob demanda e capturas em 1440×900 e 960×640 |
| Layout | Fluxo testado em 960×640, 1100×720 e 1440×900; sem alterar a resolução ou a escala do Windows |
| `python scripts/render_demo.py` | HTML local renderizado pelo Edge: seis equipamentos e um agrupamento lógico |
| Build com `IP_Scanner_Helper.spec` | Executável Qt, QML, ícone e recursos gerados em `dist/portfolio`; sem Tkinter ou WebEngine |
| Executável com `--self-check` | Saída 0; Qt Quick, seis equipamentos fictícios, detalhes fechados e template HTML carregados; captura pelo próprio Qt |

As consultas de rede foram simuladas nos testes. Não foi realizada varredura na rede do usuário. O smoke test utiliza a interface Qt Quick real, sem avisos QML, e a validação HTML anterior utiliza o navegador real. Não foi feita homologação com switches físicos. Escalas de monitor 125% e 150% não foram homologadas nesta migração; Qt utiliza o suporte a DPI do sistema.

O workflow de CI foi preparado para Python 3.11 e 3.14 no Windows, mas a execução remota no GitHub não faz parte desta validação local.

Os arquivos de demonstração usam IPs de documentação, fabricantes fictícios e MACs locais. O snapshot do código anterior está em `.backups/original-source.zip`, excluído do controle de versão e dos pacotes públicos.

Os snapshots anteriores permanecem em `.backups/pre-interface-1.0.0.zip`, `.backups/pre-design-1.1.0.zip` e `.backups/pre-qt-1.2.0.zip`. As distribuições 1.x foram preservadas; os novos pacotes usam a versão 2.0.0. O atalho `Executar Scanner.cmd` inicia o build atualizado em `dist/portfolio/2.0.0/IP_Scanner_Helper`. A pasta por versão evita substituir DLLs em uso por outra instância.
