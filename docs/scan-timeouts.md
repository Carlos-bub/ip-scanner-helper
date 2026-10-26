# Prazos de coleta e DNS reverso — 2.0.4

## Contrato de tempo

Cada IP recebe um orçamento cooperativo de **20 segundos**, contado quando seu worker começa a executar. Em **Opções → Limite por IP (s)**, a interface aceita de 1 a 120 segundos. A política Python aceita números positivos até 300 segundos e fica imutável durante a sessão.

Fila de agendamento, descoberta inicial de interfaces e leitura do cache ARP da sessão não fazem parte desse prazo por IP. O tempo total da varredura depende do número de alvos, workers, capacidade de sockets e respostas dos equipamentos.

`application/timing.py` centraliza os timeouts em `ScanTimeouts`. `ProbeContext` usa relógio monotônico, evento de cancelamento e prazos absolutos. O timeout entregue ao socket ou subprocesso é limitado pelo tempo restante. Requisições, portas e etapas de I/O subsequentes não renovam o orçamento.

O limite é cooperativo: `SendARP` não oferece parâmetro de timeout nem cancelamento. Se essa chamada já estiver executando, pode retornar depois do prazo. Nesse caso, uma resposta válida é preservada e as etapas seguintes são interrompidas. ICMP, operações de sockets e encerramento de subprocessos também dependem do sistema operacional; não há garantia de interrupção exata no milissegundo indicado.

## Política padrão

| Sonda | Timeout básico | Prazo da operação composta |
| --- | --- | --- |
| ICMP | 500 ms | Até 1,5 s incluindo inicialização do CLI, somente quando o fallback é necessário |
| TCP | 200 ms por conexão | Até 2 s por lote/IP, incluindo espera por capacidade global |
| SNMP | 350 ms por requisição | Até quatro consultas para dois OIDs e duas versões, com prazo total de 1,45 s |
| PTR | 2,5 s | Compartilhado entre implementação nativa e fallback; não é reiniciado |
| NetBIOS / ONVIF / SIP / SSDP | 400 / 500 / 350 / 350 ms | Uma operação, limitada também pelo prazo do IP |
| PJL / SSH / FTP | 350 ms por I/O | Sequência de conexão/escrita/leitura, limitada por operação e por IP |
| HTTP / TLS | 600 ms por I/O | Prazo total conforme o número de portas selecionadas |
| RDP | 800 ms por I/O | Prazo total da negociação e leitura do certificado |

Os prazos compostos incluem uma pequena margem de coordenação de 50 ms, onde aplicável. Nenhum deles aumenta o prazo total do alvo.

O perfil TCP continua usando as mesmas 13 portas, até 13 conexões pendentes por IP e limite global de 256 sockets. Os modos Rápido e Completo permanecem. Falha de ARP/ICMP continua permitindo TCP e SNMP enquanto houver tempo disponível.

Exemplo para testes ou integração Python:

```python
from ip_scanner_helper.application.scanner import ScanOptions
from ip_scanner_helper.application.timing import ScanTimeouts

options = ScanOptions(
    workers=32,
    mode="Completo",
    timeouts=ScanTimeouts(target_s=30, dns_ptr=2, tcp=.2),
)
```

Preferências persistentes e edição de todos os timeouts pela interface pertencem à próxima etapa. A comunidade SNMP continua sendo capturada somente na configuração da sessão.

## Resultados incompletos

Presença só é confirmada por evidência atual de ARP, ICMP, TCP ou SNMP. O cache ARP não comprova presença. O esgotamento de tempo não caracteriza dispositivo desligado ou endereço livre.

- **Presença confirmada, identificação limitada:** a mesma linha mantém MAC, nome, categoria, serviços e evidências já obtidos. O registro usa `coleta_completa=false`, `motivo_coleta_incompleta="tempo"` e `sondas_incompletas` com o motivo por etapa.
- **Prazo esgotado sem presença confirmada:** o endereço aparece na lista de coletas incompletas, sem criar um dispositivo fictício no inventário.
- **TCP não concluído:** o campo de portas informa a coleta incompleta; não afirma que todas as portas foram testadas ou estavam fechadas. Portas aceitas antes do limite são preservadas.
- **Cancelamento do usuário:** resultados posteriores à solicitação são descartados; a linha de presença já publicada permanece explicitamente interrompida.

O rodapé oferece **N incompletas**, com a lista dos IPs e motivos. Esses casos são contados separadamente dos erros. O progresso informa alvos processados, inclusive inconclusivos; atingir 100% não significa que todos os alvos responderam ou tiveram identificação completa.

As exportações CSV/JSON mantêm os indicadores de incompletude e suas evidências. Uma coleta completa também pode ter campos sem resposta: completude não garante nome, categoria ou acesso a todos os serviços.

## DNS nativo e liberação de recursos

`infrastructure/network/windows_dns.py` utiliza `DnsQueryEx` assíncrono para PTR e `DnsCancelQuery` para solicitar cancelamento. Estruturas, ponteiros, convenção da callback e assinaturas da DLL são explícitos para o Windows x64. Os registros retornados são liberados com `DnsFree`/`DnsFreeRecordList`.

Um timeout libera o worker, mas a memória da consulta permanece viva até a callback nativa, inclusive quando ela chega depois do cancelamento. Há no máximo **64 contextos DNS pendentes**, incluindo consultas canceladas que aguardam callback. Se esse limite estiver ocupado, a admissão espera de forma cancelável dentro do mesmo prazo; não cria mais threads ou processos.

Resposta vazia, NXDOMAIN ou timeout nativo não iniciam uma segunda consulta pelo CLI. O `nslookup` é usado apenas quando a API estiver indisponível ou rejeitar o pedido. O fallback respeita o tempo restante e mantém a leitura de saída em português/inglês. Não se usa `socket.gethostbyaddr()` sem controle de duração.

O adaptador nativo usa as configurações DNS do Windows, sem fixar servidor externo e sem consultas multicast/NetBIOS nesse caminho. `cache_only=True` é reservado à validação local da API, sem envio de consultas para a rede.

## Operações HTTP

O corpo HTTP é lido em blocos, até 64 KiB, verificando e reajustando o prazo entre leituras. Um servidor que envia poucos bytes continuamente não pode renovar indefinidamente o orçamento.

Até três redirecionamentos são aceitos para o mesmo IP e para as portas HTTP(S) selecionadas. Destinos com hostname, outro IP, porta fora do perfil ou credenciais na URL não são seguidos. Isso evita introduzir resolução DNS sem prazo por meio de um redirecionamento. O corpo de uma resposta de redirecionamento é fechado sem drenagem ilimitada; respostas de autenticação também são fechadas quando seu cabeçalho identifica o equipamento.

## Diagnóstico e validação

Com `ScanOptions(probe_metrics=True)`, o resumo distingue `timeout` de operação e `budget_exhausted` do alvo. Ambos são diferentes de `error`, `cancelled` e `not_run`. `no_result` ainda pode agrupar recusas e timeouts tratados pelos coletores antigos; esta entrega não promete distinguir todos os resultados de pacote.

Veja [validação 2.0.4](validation-2.0.4.md). A cobertura dos 24 cenários do motor foi preservada com os padrões de tempo. Os testes de prazos usam relógio controlado ou implementações simuladas; a API real foi verificada em modo somente cache. Não foi demonstrada redução da duração total em rede real.

Referências oficiais:

- [Microsoft: DnsQueryEx e vida útil das estruturas](https://learn.microsoft.com/en-us/windows/win32/api/windns/nf-windns-dnsqueryex).
- [Microsoft: DnsCancelQuery e callbacks pendentes](https://learn.microsoft.com/en-us/windows/win32/api/windns/nf-windns-dnscancelquery).
- [Microsoft: DNS_RECORDW](https://learn.microsoft.com/en-us/windows/win32/api/windnsdef/ns-windnsdef-dns_recordw).
- [Microsoft: DnsRecordListFree](https://learn.microsoft.com/en-us/windows/win32/api/windns/nf-windns-dnsrecordlistfree).
