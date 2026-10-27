# Validação local — 2.0.5 — 27/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Suíte de regressão | 158 testes aprovados, incluindo regras de arquitetura e isolamento da CLI |
| Preferências | Tipos e limites, números QML, valores imutáveis, largura de colunas ocultas e posição em monitor com coordenadas negativas |
| Persistência | Duas instâncias recuperam os mesmos valores; ausência do arquivo não cria diretórios; schema desconhecido preservado mesmo após alteração externa |
| Recuperação | JSON truncado/inválido e arquivo excessivo preservados em backup; falhas de leitura e substituição não destroem a configuração anterior |
| Privacidade | Credenciais e inventário fora do JSON; demo/self-check não constroem armazenamento pessoal; alternar demo em testes não habilita gravação |
| Contexto | Mesma faixa sem ambiente explícito isolada por sessão; nomes distintos separados; alvos efetivos e interface capturados; cópias defensivas no serviço e na conclusão |
| Sessão ativa | Alterações nas preferências afetam a próxima coleta; opções capturadas permanecem intactas; interface posterior não reatribui gateway/contexto aos resultados |
| Teste gráfico geral | Cliques, teclado, seleção, filtros, rolagem, três larguras, switches, identificação progressiva e prazo por IP aprovados com fixtures |
| Teste gráfico de preferências | Restaurar campos, cancelar, rejeitar valor inválido, salvar, editar durante coleta, arrastar coluna na tabela vazia e preservar geometria normal ao maximizar aprovados; zero avisos QML |
| Build Windows | Executável 2.0.5, metadados 2.0.5.0 e autoverificação aprovados; impressão digital das fontes e hash do executável conferidos |
| Distribuição Python | Instalação editável 2.0.5 atualizada; wheel gerada, integridade e inclusão dos novos módulos e do diálogo QML conferidas |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

Os testes usam dados fictícios, serviços simulados e arquivos temporários explícitos. Não foi feita varredura da LAN nesta validação. Os casos de monitor removido/posição negativa são simulados por retângulos; a maximização foi exercitada em uma janela real. A CI foi ampliada para executar o teste gráfico de preferências, mas a execução remota não foi verificada nesta entrega.

Esta etapa entrega a base de contexto e as preferências básicas. Perfis de portas, cofre protegido, histórico SQLite, agrupamento do mapa e homologação física de rede continuam pendentes. Os contratos e limites de persistência estão em [preferências e contexto](preferences-and-context.md).
