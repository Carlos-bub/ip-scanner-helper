# Validação local — 2.0.8 — 27/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Regressão | 209 testes aprovados, incluindo fronteiras de arquitetura e os contratos anteriores do cofre |
| Política | Inteiros de 0 a 1.000; padrão sem limite; rejeição de booleanos, frações, valores não finitos e tipos inválidos; opções imutáveis |
| Admissão | Espaçamento uniforme com relógio controlado, sem créditos ociosos ou reservas futuras; admissão atômica entre oito threads |
| Sessão | Uma instância compartilhada pelos workers padrão e nova instância por coleta; resumo de admissões independente do diagnóstico detalhado |
| Prazos | Espera consome o prazo por IP; timeout específico começa após admissão; prazo esgotado preserva presença e informa incompletude; sem presença, alvo inconclusivo |
| Parada | Cancelamento durante espera não admite outra sonda; serviço com evento real encerra dentro do prazo do teste, sem acesso à rede |
| Cobertura | Equipamento com somente SNMP continua identificado quando há orçamento; cobertura e erros preservados nos 24 cenários/tamanhos do benchmark com o padrão sem limite |
| Persistência | Migração de schemas 1/2/3 para 4 com backup; schema 3 preserva referência do cofre, perfil e tempos; falha no backup mantém original |
| Interface | Três scripts Qt aprovados, sem avisos QML: tabela/detalhes, preferências e cofre; taxa restaurada, vazio rejeitado, cancelar descarta, salvar persiste e sessão ativa permanece intacta |
| Distribuição | Build Windows 2.0.8 com autoverificação aprovada; wheel gerada e recursos conferidos; ZIPs públicos e hashes verificados |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/smoke_vault.py
.venv\Scripts\python.exe -B scripts/benchmark_engine.py --output build/benchmarks/rate-2.0.8.json --compare docs/benchmarks/engine-baseline-2.0.1.json
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

Os testes gráficos usam serviços substitutos, credenciais sintéticas e configurações temporárias. A proteção DPAPI é real no teste do cofre; a taxa usa relógio controlado nos testes determinísticos e um evento real no teste de parada. A captura [Coleta](desktop-probe-rate.png) mostra o novo ajuste durante uma sessão simulada.

Não foi realizada varredura de LAN ou medição de pacotes. O benchmark compara o scanner/coordenador real com coletores simulados; confirma preservação de cobertura/erros com taxa desativada e não demonstra melhoria de duração em rede real. O ajuste controla admissões de coletores, com alcance e limites descritos no [contrato](probe-rate-limit.md). Homologação em laboratório físico e distinção completa de falhas tratadas pelos coletores continuam pendentes. A CI remota não foi verificada nesta etapa.
