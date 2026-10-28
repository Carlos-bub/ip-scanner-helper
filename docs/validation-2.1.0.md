# Validação local — 2.1.0 — 28/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e Edge
156.0.4314.50 headless. Apenas dados fictícios e armazenamento temporário.

| Verificação | Resultado |
| --- | --- |
| Suíte completa | 315 testes aprovados, incluindo temas, migração de schema 4→5 e falha de gravação sem aplicação parcial |
| Navegação | Quatro páginas, seleção e coleta ativa preservadas; rascunhos protegidos ao navegar e fechar a janela |
| Aparência | Claro, escuro e sistema; mudança de esquema Qt exercitada; contraste dos botões selecionados verificado; tema persistido; 960×640, 1100×720 e 1440×900 |
| Topologia nativa | Seleção e retorno ao inventário, zoom, grupo com 4.096 registros, expansão para 4.097 cartões e enquadramento; canvas do tamanho do viewport |
| Preferências | Perfis TCP, duplicar/remover/cancelar, tempos, taxa, campos inválidos, sessão imutável e maximização |
| Cofre | DPAPI real com segredos sintéticos, criar/editar/excluir, seleção e isolamento de estado/arquivos/exportações |
| Histórico/IPAM | SQLite temporário, diff, mapa de endereços com visibilidade/geometria das células verificadas, reservas, backup/restauração, reabertura e janela compacta |
| L2 | LLDP/CDP, VLANs, cobertura parcial, texto de rede como PlainText e cancelamento |
| Navegador | 12 cenários de mapa HTML até 4.096 registros; layout compartilhado preservado, sem requisições externas |
| Build | Executável 2.1.0 autoverificado; fingerprint/SHA-256 e conteúdo dos recursos QML/JS conferidos com as fontes finais; captura da tela inicial gerada pelo executável |

Os seis testes gráficos exercitam controles Qt reais e terminaram sem avisos QML.
O teste de aparência manipula apenas o esquema Qt do processo de teste, sem
alterar o tema do Windows. A CI ganhou o smoke test de navegação; a execução
remota não foi verificada.

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/smoke_navigation.py --capture
.venv\Scripts\python.exe -B scripts/smoke_vault.py
.venv\Scripts\python.exe -B scripts/smoke_l2.py
.venv\Scripts\python.exe -B scripts/smoke_history.py --capture
.venv\Scripts\python.exe -B scripts/smoke_topology.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

Sem varredura da LAN, notificações, integrações externas, expurgo ou mudança das
regras de classificação. Homologação física e recursos diferidos estão descritos
no [guia da navegação](navigation-and-appearance.md).
