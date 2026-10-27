# Validação local — 2.0.6 — 27/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Regressão | 172 testes aprovados, incluindo limites de arquitetura |
| Perfis | Perfil padrão preservado, parser/roundtrip, portas inválidas/repetidas, limites, modelos imutáveis e separação TCP/UDP |
| Coleta | Perfil chega ao coletor TCP; tempos chegam às sondas; presença SNMP isolada preservada; descrição manual não confirma categoria ou habilita protocolo automaticamente |
| Recursos TCP | 128 portas em lotes, limite de 13 pendências por IP, ordem dos resultados e liberação de sockets/slots em prazo esgotado |
| Sessão ativa | Trocar perfil e tempos altera a próxima sessão; opções capturadas permanecem intactas; rascunho inválido não é aplicado parcialmente |
| Migração | Schema 1 carregado sem escrita antecipada; cópia exata antes da gravação schema 2; falha no backup preserva o original; schema futuro não é sobrescrito |
| Interface | Dois testes gráficos aprovados; abas, criar/duplicar/remover/cancelar perfis, tempos inválidos, restaurar tempos, persistência, janela compacta e maximizada; zero avisos QML |
| Cobertura simulada | Mesmos resultados e erros da referência em 24 cenários/tamanhos, incluindo ICMP bloqueado e SNMP isolado |
| Build Windows | Executável 2.0.6 com autoverificação aprovada, usando QML, inventário fictício e mapa offline |
| Distribuição Python | Instalação editável 2.0.6 e wheel final conferidas; módulos de perfis/política e recursos QML presentes e iguais às fontes |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/benchmark_engine.py --output build/benchmarks/profiles-2.0.6.json --compare docs/benchmarks/engine-baseline-2.0.1.json
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

O benchmark usa o perfil Padrão e coletores simulados. Ele verifica a preservação dos resultados, não comprova ganho de desempenho ou interoperabilidade em rede real. Não foi feita varredura da LAN nesta etapa. Os testes gráficos usam serviços simulados e diretórios temporários explícitos, sem carregar preferências pessoais. A CI existente passa a executar esses casos pelo script ampliado; sua execução remota não foi verificada.

Detalhes de formato, compatibilidade e limites em [perfis e tempos](port-profiles.md). O cofre de credenciais e o controle de sondas por segundo continuam pendentes de E2.
