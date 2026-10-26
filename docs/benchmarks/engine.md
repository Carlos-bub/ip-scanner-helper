# Motor completo e identificação progressiva — 2.0.2

26/10/2026. Windows 10 x64, Python 3.14.6. O script executa o scanner e o coordenador reais, substituindo **todos os coletores de rede por fixtures**. Nenhum pacote é enviado a alvos. O teste de TCP não bloqueante continua documentado separadamente em [README.md](README.md).

## Método

Foi registrada uma referência do motor 2.0.1 antes da alteração do pipeline. Os mesmos seis cenários foram repetidos com publicação progressiva, com e sem diagnóstico detalhado, em 32, 254, 1.024 e 4.096 alvos e 32 workers:

- Sem resposta útil em nenhum coletor.
- Mistura de alvos sem resposta, ARP/ICMP, TCP e SNMP.
- ICMP bloqueado com portas TCP aceitas.
- SNMP como única evidência.
- DNS lento, com atraso artificial de 7 ms.
- Falhas intencionais de DNS em parte dos alvos.

As assinaturas dos registros **finais** (IP, nome, categoria, serviços, latência e origem do nome) e a contagem de erros foram iguais à referência em todos os cenários. Registros parciais de presença preservados após erro/interrupção são uma informação adicional, não um inventário final completo.

Os relatórios incluem duração total, CPU do processo, tempo até o primeiro registro, tempo até o primeiro registro completo, pico de alocações Python e encerramento após cancelamento. CPU do processo inclui todas as threads desse processo. `tracemalloc` não mede RSS/RAM total. São execuções locais únicas, sem estimativa de percentis ou garantia de tempos em rede real.

## Resultados e interpretação

No cenário de DNS lento com 254 alvos, a referência publicou o primeiro registro completo em **0,0333 s**. O pipeline publicou a primeira presença parcial em **0,0046 s** e o primeiro registro completo em **0,0511 s**. A duração total foi de **0,1288 s** na referência e **0,2012 s** no pipeline.

Portanto, este incremento demonstra antecipação da informação de presença na simulação, não redução da duração total. Publicar um registro parcial e enriquecê-lo tem custo de processamento. O diagnóstico detalhado acrescenta contadores, timestamps e sincronização; permanece desligado por padrão. A leitura nativa de interfaces foi validada separadamente, consultando apenas a configuração local do Windows.

Dados completos:

- [Referência 2.0.1](engine-baseline-2.0.1.json).
- [Pipeline 2.0.2, diagnóstico de sondas desligado](engine-progressive-2.0.2.json).
- [Pipeline 2.0.2, diagnóstico de sondas ligado](engine-observed-2.0.2.json).

Para reproduzir a implementação atual contra a referência salva:

A partir da versão 2.0.3, as fixtures são injetadas diretamente como `NetworkProbe` no serviço. O benchmark não importa os coletores concretos de rede. A reorganização manteve os registros finais e a contagem de erros da referência nos 24 cenários/tamanhos; o relatório de verificação local está em `build/benchmarks/architecture-2.0.3.json`, fora dos artefatos públicos. Os números das tabelas e JSONs acima continuam sendo os medidos na versão 2.0.2.

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts/benchmark_engine.py --output build/engine-current.json --compare docs/benchmarks/engine-baseline-2.0.1.json
.venv\Scripts\python.exe -X utf8 -B scripts/benchmark_engine.py --probe-metrics --output build/engine-diagnostic.json --compare docs/benchmarks/engine-baseline-2.0.1.json
```

## Contrato do diagnóstico

`ScanOptions(probe_metrics=True)` ativa observações agregadas no scanner padrão. O aplicativo usa o padrão desligado. Cada observação tem identificador da sonda, início UTC, duração e um estado:

| Estado | Significado |
| --- | --- |
| `result` | O coletor produziu resultado útil conforme seu contrato |
| `no_result` | O coletor retornou valor vazio; não equivale a host desligado ou timeout confirmado |
| `error` | Uma exceção foi propagada pelo coletor |
| `cancelled` | A execução foi cancelada antes ou durante a chamada |
| `timeout` | Prazo controlado da operação esgotado (adicionado em 2.0.4) |
| `budget_exhausted` | Prazo cooperativo do IP esgotado (adicionado em 2.0.4) |
| `not_run` | Sonda não executada, por modo, condição do serviço ou interrupção |

Os coletores existentes ainda agrupam algumas falhas tratadas, recusas e timeouts em valores vazios. A instrumentação não inventa distinções que esses contratos não fornecem. Durações por sonda são somadas entre threads/alvos e podem exceder o tempo de parede da sessão. Operações nunca agendadas não aparecem como sondas executadas.

O resumo fica no evento `finished.metrics`, sem credenciais ou payloads de respostas. Os registros exibidos/exportados usam `coleta_completa` para distinguir a identificação final da parcial. A confirmação de presença continua exigindo evidência atual de ARP, ICMP, TCP ou SNMP.

## Interfaces Windows

O adaptador nativo usa assinaturas e estruturas explícitas de [GetAdaptersAddresses](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getadaptersaddresses). A leitura mantém os buffers vivos durante a travessia, verifica comprimentos das estruturas, limita tentativas de redimensionamento e protege contra cadeias inválidas. Apenas interfaces ativas com IPv4 utilizável são oferecidas; endereços tentativos ou duplicados são excluídos da seleção. Isso não constitui um detector de conflitos da rede.

O fallback PowerShell é acionado em falha da API, não quando a enumeração válida retorna vazia. A interface selecionada sugere a faixa; as rotas do Windows continuam determinando a saída efetiva das sondas.

A versão 2.0.4 também manteve os registros finais e erros nos 24 cenários/tamanhos, com a política de tempo padrão. Relatório local: `build/benchmarks/deadlines-2.0.4.json`. Esta comparação verifica cobertura com fixtures e não demonstra ganho de duração total em rede real. Veja [prazos de coleta](../scan-timeouts.md).
