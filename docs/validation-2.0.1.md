# Validação local — 2.0.1 — 23/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Suíte de testes | 76 aprovados; 11 testes novos de TCP e ICMP, além das regressões anteriores |
| Coleta TCP simulada | Conexões aceitas/recusadas, pendências Winsock, timeout, contenção, criação/seletor com erro, cancelamento e recursos liberados |
| Adaptador ICMP simulado | RTT, limite sub-ms, status de erro, origem divergente, handle inválido, exceções e fallback |
| `scripts/validate_loopback.py` | TCP real aberto/recusado e ICMP nativo aprovados, restritos a 127.0.0.1 |
| `scripts/benchmark_tcp.py` | 16 medições: duas variantes, dois cenários, quatro tamanhos; resultados por alvo iguais |
| `scripts/smoke_ui.py` | Interface QML real, seleção, teclado, filtros, detalhes, colunas, três larguras, switch e execução simulada aprovados |
| Executável com `--self-check` | Saída 0, sem avisos QML; metadados Windows 2.0.1 / 2.0.1.0 |
| Instalação editável | Pacote 2.0.1 instalado no ambiente local |

Executável: `dist/portfolio/2.0.1/IP_Scanner_Helper/IP_Scanner_Helper.exe`. O atalho da raiz inicia esse caminho; a distribuição 2.0 permanece preservada.

Não houve varredura da LAN nem homologação em switches físicos. O teste de integração real usou apenas loopback. Os tempos do benchmark representam o coletor TCP simulado, sem ARP, ICMP, DNS ou SNMP; não demonstram um ganho da mesma proporção no motor completo. A latência da parada registrada também se refere somente ao coletor TCP.

A instrumentação do motor completo, a descoberta nativa de interfaces e a publicação progressiva de presença/enriquecimento continuam pendentes. Consulte o [benchmark](benchmarks/README.md) para método e dados deste incremento.
