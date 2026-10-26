# Validação local — 2.0.2 — 26/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2.

| Verificação | Resultado |
| --- | --- |
| Suíte unitária/regressão | 92 testes aprovados; mantém detecção por SNMP isolado e por TCP com ICMP bloqueado; o teste exclusivo de Tkinter foi removido |
| Adaptador de interfaces | Fixtures com múltiplos endereços, prefixos distintos, VPN sem gateway, estado down, loopback, DAD inválido, estruturas curtas, ciclos, redimensionamento e falhas |
| Leitura nativa no Windows | Dois registros ativos retornados, com os mesmos endereços e prefixos da coleta anterior; quatro registros extras da coleta PowerShell estavam desconectados e com endereço tentativo, sendo corretamente filtrados pela API nativa |
| Pipeline | Presença publicada enquanto DNS permanece bloqueado; progresso não conclui antes do enriquecimento; resultado tardio descartado após cancelamento |
| Modelo Qt | Atualização do mesmo IP sem duplicação; inserções/remoções preservam índices persistentes; identificação incompleta mantém estado explícito |
| Instrumentação | Agregação concorrente, cópia isolada do resumo e distinção entre resultado útil, ausência de resultado, erro, cancelamento e sonda não executada |
| Benchmark do motor | 24 cenários/tamanhos por configuração; mesmos registros finais e erros da referência 2.0.1 |
| Smoke test gráfico | QML real, cliques, teclado, filtros, colunas, três larguras, switches e pipeline simulado; seleção, detalhes e rolagem preservados após chegar o nome, incluindo inventário com 96 registros |
| Executável Windows | Autoverificação concluída com código zero; Qt Quick, inventário fictício, recursos e mapa offline aprovados; versão do produto 2.0.2 e do arquivo 2.0.2.0 |

O teste gráfico aguarda o ciclo de renderização após `rowsInserted` antes de simular um clique nas células. As sondas dos testes são substituídas por fixtures; não foi feita varredura da rede do usuário ou homologação em switches físicos.

O [benchmark](benchmarks/engine.md) separa informação parcial antecipada de conclusão completa. Não foi demonstrada redução da duração total da varredura. Diagnóstico detalhado é opcional para evitar seu custo no uso normal.

Pendências da etapa de desempenho: orçamento cooperativo por alvo, revisão do PTR nativo com duração limitada e formalização de contexto de rede para histórico. Preferências persistentes e agrupamento do mapa pertencem às próximas entregas.
