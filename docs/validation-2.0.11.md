# Validação local — 2.0.11 — 28/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0, PyInstaller 6.22.2 e Edge 156.0.4314.50 headless. As alterações externas de classificação foram preservadas; o histórico armazena seus resultados sem reclassificação.

| Verificação | Resultado |
| --- | --- |
| Regressão | 289 testes aprovados; arquitetura, CLI instalada, scanner, preferências, cofre, L2 e histórico |
| Domínio | Sanitização sem mutar entrada, exclusão de segredos, datas com fuso, escopo, categorias preservadas, perfis incompatíveis, comparação e estados conservadores |
| Persistência | Reabertura por nova instância, upsert transacional, sessões e reservas separadas por ambiente; sessão sem encerramento não reescrita por outra instância |
| Migração | Esquema 1 para 2 com backup prévio; bancos futuros, estranhos e vazios recusados sem alteração |
| Worker | Fila limitada, rejeição explícita, cópia defensiva, thread separada, cancelamento de comando pendente e drenagem final mesmo com fila cheia |
| Backup/restauração | Cópia SQLite consistente, reservas preservadas, backup pré-restauração, falha de arquivo/substituição sem perda do atual, destino existente protegido e recusa diante de outra transação |
| Controlador | Gravação automática de conclusão/interrupção, erro por IP, contexto/opções sem segredo e abertura de histórico sem chamada de rede |
| Interface | Cinco scripts Qt aprovados: inventário, preferências, cofre, L2 e histórico; comparação, reservas, backup/restauração e 960×640, zero avisos QML |
| Navegador | 12 cenários de topologia até 4.096 registros, zero erros JavaScript e nenhuma requisição externa das páginas |
| Build | Executável 2.0.11 gerado e autoverificação aprovada; SQLite e componentes de histórico incluídos |
| Distribuição | Wheel com módulos/recursos comparados às fontes; ZIPs com CRC/SHA-256 conferidos, banco/cofre/estudos internos excluídos |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/smoke_vault.py
.venv\Scripts\python.exe -B scripts/smoke_l2.py
.venv\Scripts\python.exe -B scripts/smoke_history.py --capture
.venv\Scripts\python.exe -B scripts/smoke_topology.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

Os testes de histórico usam SQLite real em diretórios temporários, dados fictícios em `192.0.2.0/24` e cliques na interface QML real. O teste gráfico grava dois inventários, compara mudanças, cria reserva, faz backup, acrescenta uma sessão e restaura o backup, comprovando a recuperação e a preservação do banco anterior. Depois reabre o armazenamento por outra instância. O teste de restauração respeita os prazos das operações de cópia e pode levar mais tempo sob concorrência de build/antivírus.

Não houve varredura da LAN, homologação de switches, teste de queda de energia ou encerramento forçado do sistema. O comportamento sob interrupção abrupta se limita ao último checkpoint transacionado; não se afirma preservação dos dados ainda em memória. A CI inclui o novo smoke test, mas a execução remota não foi verificada. O banco local não é criptografado; o cofre continua separado.

Limites, localização do banco e operação estão no [guia de histórico](history.md). Homologação física de E5 e importação manual dos diagramas continuam pendentes.
