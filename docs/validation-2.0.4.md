# Validação local — 2.0.4 — 26/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Suíte de regressão | 127 testes aprovados, incluindo limites de arquitetura |
| Política de tempo | Valores finitos/positivos, opções imutáveis, relógio monotônico e timeout reduzido ao prazo restante |
| Presença e cobertura | ARP tardio válido preservado; cache sozinho não confirma presença; TCP e SNMP continuam após falha do ping |
| Dados parciais | Nome/categoria SNMP e portas TCP aceitas preservados após limite; TCP não executado não é apresentado como ausência de portas abertas |
| Estados da sessão | Alvos inconclusivos separados de dispositivos e erros; conclusão tardia descartada após cancelamento; sessão ativa não aceita alteração das opções |
| TCP | Espera por capacidade limitada pelo prazo do lote; conexões pendentes fechadas, registros do selector retirados e slots liberados ao atingir o limite |
| DNS nativo simulado | Layout x64, resposta síncrona, callback antecipada/tardia, cancelamento, NXDOMAIN, falha da API, memória preservada após timeout e admissão limitada |
| DNS real do Windows | `DnsQueryEx` executado em modo somente cache para loopback, com resposta válida e zero contextos pendentes após liberação; sem consultas de rede nessa verificação |
| Fallback DNS | Resposta vazia e timeout nativo não iniciam `nslookup`; API indisponível aciona fallback com prazo restante; leitura PT/EN preservada |
| HTTP | Corpo enviado lentamente não renova o prazo; redirecionamentos restritos ao escopo, sem drenagem ilimitada; respostas de autenticação fechadas |
| Teste gráfico Qt | 960×640, 1100×720 e 1440×900, seleção/rolagem preservadas; prazo real do scanner com sondas simuladas; lista de três coletas incompletas aberta no rodapé |
| Benchmark de cobertura | Mesmos registros finais e contagem de erros da referência nos 24 cenários/tamanhos, incluindo ICMP bloqueado e SNMP isolado |
| Build Windows | Executável final 2.0.4 e metadados 2.0.4.0; autoverificação aprovada com código zero, QML/inventário/recursos/mapa offline |
| Distribuição Python | Wheel 2.0.4 gerada e conferida, incluindo módulos de prazos, DNS e recursos instaláveis; integridade ZIP aprovada |

O benchmark está em `build/benchmarks/deadlines-2.0.4.json` e pode ser reproduzido com:

```powershell
.venv\Scripts\python.exe -B scripts/benchmark_engine.py --output build/benchmarks/deadlines-current.json --compare docs/benchmarks/engine-baseline-2.0.1.json
```

Os testes usam relógio controlado, implementações simuladas ou cache local. Não foi feita varredura da LAN nem homologação em switches físicos. O benchmark verifica cobertura e erros; não demonstra redução da duração total em rede real.

Os prazos são cooperativos, especialmente em `SendARP`. A leitura inicial do cache ARP da sessão e a espera na fila ficam fora do orçamento do IP. As estruturas DNS canceladas continuam alocadas até a callback nativa, com admissão limitada, sem modificar o inventário após cancelamento.

Os [contratos de tempo](scan-timeouts.md) detalham padrões, limitações e indicadores das exportações. Preferências persistentes e contexto de rede continuam pendentes; esta entrega não conclui todo o roadmap.
