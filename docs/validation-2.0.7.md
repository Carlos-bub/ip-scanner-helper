# Validação local — 2.0.7 — 27/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Regressão | 195 testes aprovados, incluindo limites de arquitetura |
| Modelos | Identificador/nome/ambiente, limites UTF-8, comunidade sem caracteres de controle, representações sem segredo e metadados públicos |
| DPAPI real | Gravação/leitura entre instâncias no mesmo usuário, comunidade Unicode e rejeição de arquivo adulterado, com dados sintéticos |
| Fronteira nativa | Flags por usuário sem escopo de máquina, prompts nulos, liberação de memória e limpeza do buffer nativo de texto claro |
| Arquivos | Ausência não cria cofre; edição preservando/trocando segredo; duplicatas e limite de 32; arquivo inválido/futuro/inacessível preservado; falha de proteção/substituição e contenção de bloqueio |
| Sessão/contexto | Seleção explícita resolve uma credencial; referência restaurada não confirma ambiente; divergência bloqueia; editar/excluir mantém sessão ativa e não aciona fallback |
| Privacidade | JSON contém somente referência; estado/rascunhos/metadados sem comunidade; exceções sintéticas com segredo não aparecem nos logs de SNMP/coordenador ou nos eventos de erro |
| Migração | Schemas 1/2 preservados em backup antes do schema 3; perfis e tempos anteriores mantidos |
| Interface | Três scripts gráficos aprovados: inventário, preferências e cofre; criar/editar/excluir com confirmação, campo não revelado, sessão ativa, janela compacta, configurações/logs/exportações sem as comunidades sintéticas; zero avisos QML |
| Build Windows | Executável 2.0.7 com autoverificação aprovada; QML, inventário fictício e recursos/mapa offline carregados |
| Distribuição | Wheel 2.0.7 conferida, módulos/QML iguais às fontes, identidade do executável validada e filtro de arquivos do cofre verificado também para nomes em maiúsculas e cópias |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/smoke_vault.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

Os testes usam comunidades sintéticas e diretórios temporários explícitos. A DPAPI foi executada de verdade no usuário local; falhas de contexto estrangeiro foram simuladas e adulteração do arquivo foi testada com a API real. Não foi realizado ensaio entre duas contas/máquinas nem varredura de LAN. Os coletores dos testes gráficos são substituídos; a proteção de arquivo é real no teste do cofre.

A CI foi ampliada para o script do cofre em Windows/Python 3.11 e 3.14, mas sua execução remota não foi verificada. Esta etapa não afirma proteção contra processos no mesmo contexto de usuário, limpeza de todas as cópias em memória ou criptografia do protocolo SNMP na rede. Consulte [contrato do cofre](credential-vault.md).
