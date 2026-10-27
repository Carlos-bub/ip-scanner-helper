# Ritmo de coleta — 2.0.8

Em **Preferências → Coleta → Sondas por segundo**, informe um inteiro de **0 a 1.000**. O padrão **0** desativa o limite, preservando a execução anterior. O valor é salvo para a próxima varredura; editar durante uma coleta mantém a configuração que ela capturou ao iniciar.

O ajuste espaça a admissão dos coletores de todos os IPs da sessão. Por exemplo, com 20 sondas/s, há ao menos 50 ms entre admissões. Os workers compartilham um único controlador; aumentar a quantidade de workers não multiplica essa taxa. Não há créditos acumulados durante períodos ociosos nem reserva antecipada de vagas. Cada instância do aplicativo e cada nova sessão possuem seu próprio controlador.

## Alcance

Uma sonda corresponde a uma chamada do scanner para ARP, ICMP, lote TCP, SNMP, PTR, NetBIOS ou um dos coletores de identificação (PJL, ONVIF, HTTP, SIP, RDP, SSH, FTP, TLS e SSDP). A contagem considera a admissão do coletor, inclusive quando ele consulta um cache ou não obtém resposta. O sistema operacional pode atrasar a execução após a admissão; o ajuste não é um temporizador de precisão.

**Este ajuste não controla pacotes por segundo.** Um lote TCP pode iniciar várias conexões; uma consulta SNMP pode fazer várias requisições. Portas do lote, tentativas internas, redirecionamentos e retransmissões do Windows não recebem uma admissão individual. Permanecem os limites existentes de até 13 conexões TCP pendentes por IP e 256 sockets globais. O perfil Padrão mantém 13 portas e a concorrência padrão continua em 32 workers, com máximo de 128.

Descoberta de interfaces, leitura inicial do cache ARP, mapeamento de switches, ações manuais e exportações ficam fora desse controle. A demonstração não realiza sondagens.

## Prazos e cancelamento

A espera pela admissão **consome o orçamento por IP**, contado desde o início do worker. O timeout específico do coletor começa depois da admissão, limitado ao tempo restante do IP. A espera não renova esses prazos e não mantém um socket ou um bloqueio compartilhado ocupado. Cancelar acorda a espera pelo evento da sessão; as verificações periódicas respeitam também o prazo original.

Uma taxa baixa com muitos workers pode consumir o prazo antes de algumas sondas começarem. Nesse caso, o aplicativo mantém os dados confirmados e informa a coleta incompleta; sem evidência de presença, registra o alvo como inconclusivo. Não conclui que o equipamento está desligado ou que o IP está livre. ARP/ICMP sem resposta continuam permitindo TCP e SNMP enquanto houver tempo. A ordem de admissão entre workers não tem garantia de equidade.

O limite é cooperativo e não interrompe uma operação nativa já iniciada, como SendARP. Consulte os [contratos de tempo](scan-timeouts.md).

## API e diagnóstico

```python
from ip_scanner_helper.application.scanner import ScanOptions

options = ScanOptions(workers=32, probe_rate_limit=40)
```

`ScanService` cria um controlador por sessão e o passa a todos os workers padrão. Uma chamada isolada a `scan_device` cria seu próprio controlador; integrações que chamam essa função em paralelo precisam fornecer o mesmo `rate_limiter` para compartilhar a taxa. Workers substitutos do serviço mantêm o contrato anterior e são responsáveis por sua própria coleta/admissão.

O evento `finished` contém `metrics.probe_rate`, com `limit_per_second`, `scope="collector_starts"` e `started` (total de admissões). Essa contagem independe do diagnóstico por sonda. Quando `probe_metrics=True`, a duração por etapa inclui a espera pela admissão; ela não representa somente o tempo de rede. Nenhuma comunidade ou resposta coletada entra nesses contadores.

## Persistência e retorno de versão

O JSON passa ao **schema 4**, com `preferences.probe_rate_limit`. Arquivos de schemas 1, 2 e 3 são carregados com taxa desativada quando o campo está ausente; perfis, tempos e referência do cofre são preservados. A primeira gravação cria um backup exato `settings.v<versão>-backup-<identificador>.json` antes da substituição. Se esse backup falhar, o arquivo anterior permanece intacto. O cofre não é alterado por essa migração.

Ao retornar à 2.0.7, feche o aplicativo, preserve o `settings.json` atual e restaure o backup `settings.v3-backup-*.json` como `settings.json`. A versão anterior preserva schemas desconhecidos e usa os padrões; ela não aplica o limite de taxa. Veja a [validação local](validation-2.0.8.md) e a [tela de coleta](desktop-probe-rate.png).
