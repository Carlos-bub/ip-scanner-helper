# Primeiro incremento de desempenho — 2.0.1

23/10/2026. Windows 10 x64, Python 3.14.6. Este é um benchmark da **etapa TCP com sockets e seletor simulados**, não uma medição de varredura completa ou da rede do usuário.

O script `scripts/benchmark_tcp.py` compara a sequência serial de 13 portas da versão 2.0 com a nova coleta concorrente. Usa os mesmos alvos e respostas, 32 workers e timeout simulado de 2 ms por conexão sem resposta. A quantidade de futures é limitada a lotes de duas vezes os workers. Na versão concorrente, há no máximo 13 sockets pendentes por alvo e 256 no processo. Um timeout começa após a admissão do socket; falta temporária de capacidade não descarta portas.

O cenário `filtered` não oferece resposta em nenhuma porta. No cenário `mixed`, parte dos hosts aceita HTTP/HTTPS e recusa as demais portas; o restante não responde. A igualdade de todos os resultados entre variantes e a quantidade de tentativas são verificadas pelo script. Isso não simula todos os comportamentos de Winsock, ARP, DNS ou SNMP.

| Cenário | Alvos | Referência serial | Concorrente |
| --- | ---: | ---: | ---: |
| Sem resposta TCP | 32 | 0,044 s | 0,013 s |
| Sem resposta TCP | 254 | 0,268 s | 0,098 s |
| Sem resposta TCP | 1.024 | 1,210 s | 0,469 s |
| Sem resposta TCP | 4.096 | 4,604 s | 1,209 s |
| Misto | 32 | 0,036 s | 0,011 s |
| Misto | 254 | 0,246 s | 0,075 s |
| Misto | 1.024 | 1,027 s | 0,367 s |
| Misto | 4.096 | 4,360 s | 1,807 s |

Tempos arredondados de uma execução local; variam conforme máquina e carga. O timeout reduzido acelera os ensaios e não é o padrão de produção (200 ms por conexão). Os números não devem ser extrapolados para “/24 em X segundos”. Não foi calculado percentil estatístico com repetições.

O [JSON desta execução](tcp-first-stage.json) também registra CPU, tempo até o primeiro host com TCP aceito, tentativas, pico de sockets, latência da parada e pico de alocações Python via `tracemalloc`. Essa medida de alocação **não é RAM total/RSS do processo**. Em cenário sem resposta, o primeiro resultado fica nulo. A medição da parada cobre o coletor TCP, não a sessão inteira com as outras sondas.

Para reproduzir, sem enviar pacotes:

```powershell
.venv\Scripts\python.exe -X utf8 -B scripts/benchmark_tcp.py
```

Os testes unitários usam respostas controladas para conexões imediatas, recusadas, pendentes Winsock, timeout, falta de capacidade, erro de criação/seletor e cancelamento. A suíte completa passou com 76 testes.

Também foi executado `scripts/validate_loopback.py`: conexões TCP reais em portas locais aberta/recusada e ICMP nativo para `127.0.0.1` passaram no Windows. Nenhum alvo da LAN foi consultado. Esse teste verifica a integração básica, sem homologar firewalls, VPNs ou equipamentos físicos.

As APIs foram implementadas a partir de [IcmpSendEcho](https://learn.microsoft.com/en-us/windows/win32/api/icmpapi/nf-icmpapi-icmpsendecho), do [cabeçalho de resposta ICMP](https://learn.microsoft.com/en-us/windows/win32/api/ipexport/ns-ipexport-icmp_echo_reply) e da documentação de [selectors](https://docs.python.org/3.14/library/selectors.html). O adaptador lê somente o prefixo de tamanho fixo da resposta; não dereferencia ponteiros de dados/opções que diferem entre layouts de 32/64 bits.

O [registro de validação 2.0.1](../validation-2.0.1.md) inclui os testes da interface e do executável.
