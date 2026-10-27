# Perfis TCP e tempos por sonda

A versão 2.0.6 amplia Preferências com as abas **Coleta**, **Perfis TCP** e **Tempos**. A tabela continua como tela principal. Salvar valida o rascunho inteiro; Cancelar descarta a edição. Uma sessão ativa mantém seu perfil, seus tempos e sua concorrência.

## Perfis incluídos

| Perfil | Portas TCP |
| --- | --- |
| Padrão | 21, 22, 23, 53, 80, 443, 445, 5060, 515, 3389, 8080, 8443, 9100 |
| Infraestrutura | Padrão + 179, 8291, 8728, 8729 |
| CFTV | 80, 443, 554, 8000, 8080, 8443, 37777 |
| Impressão | 80, 443, 515, 631, 9100 |
| Servidores | 21, 22, 80, 443, 445, 3389, 1433, 1521, 3306, 5432, 6379, 8080, 8443 |

O perfil Padrão conserva as 13 portas, a ordem e os rótulos anteriores. Os nomes dos perfis indicam um recorte de consulta; não confirmam a categoria do dispositivo. As descrições das portas indicam serviços esperados. Uma conexão TCP aceita confirma a aceitação da conexão, sem provar o protocolo, a versão ou uma vulnerabilidade.

## Perfis personalizados

Selecione **Novo perfil** ou **Duplicar** para editar. Os perfis incluídos são somente para leitura. O aplicativo aceita até oito perfis personalizados e 128 portas por perfil. Cada entrada contém protocolo, número e descrição; este editor aceita somente TCP. Identificadores permanecem estáveis ao renomear. Portas repetidas, zero, valores acima de 65535 e descrições inválidas são rejeitados.

Use uma porta por linha, com descrição opcional:

```text
8088 Minha aplicação
9000 Serviço interno
```

Remover afeta o rascunho; a exclusão só é persistida ao salvar. O perfil Padrão passa a ser a seleção do rascunho após a remoção. Não há expansão de faixas de portas neste editor.

SNMP permanece uma consulta específica em UDP/161, inclusive quando não houver resposta ICMP ou TCP. NetBIOS/137, WS-Discovery/3702, SIP/5060 e SSDP/1900 também permanecem sondas UDP específicas, executadas conforme as condições do pipeline. Não há varredura genérica UDP nem inclusão automática dessas portas nos perfis TCP.

O modo Completo continua usando os coletores existentes: HTTP/TLS e banners nas portas reconhecidas, PJL em 9100, entre outros. Cadastrar `8088 Minha aplicação` acrescenta a tentativa TCP, sem habilitar automaticamente um protocolo de identificação nessa porta. DNS reverso, ICMP, ARP e as consultas específicas mantêm seus contratos.

## Tempos

A aba Tempos permite editar os limites de ICMP, conexão TCP, lote TCP por IP, SNMP, DNS reverso, NetBIOS, PJL, ONVIF, HTTP, SIP, RDP, SSH, FTP, TLS e SSDP. Os valores são em segundos, finitos, maiores que zero e até 300. Use ponto decimal. Restaurar tempos repõe os padrões no rascunho; Cancelar ainda descarta essa alteração.

O orçamento total por IP continua sendo 20 segundos por padrão. O limite do lote TCP continua sendo 2 segundos, e o de cada conexão, 0,2 segundo. São limites diferentes: o orçamento do lote inclui espera por capacidade e todos os grupos de portas; o orçamento do IP limita o conjunto da coleta. As demais sondas podem ter tentativas e etapas internas, conforme os [contratos de tempo](scan-timeouts.md).

Perfis maiores podem atingir o limite do lote antes de consultar todas as portas. O resultado fica explicitamente incompleto e preserva as portas já aceitas. Permanecem no máximo 13 conexões pendentes por IP e 256 sockets TCP globais. Esses valores não representam pacotes por segundo. O controle de sondas iniciadas por segundo permanece pendente.

Os registros finais incluem `perfil_portas` com ID/nome e `portas_previstas_tcp` com o escopo planejado. Essa lista não comprova que cada porta foi consultada: confira `coleta_completa` e `sondas_incompletas`. CSV e JSON mantêm o formato existente e acrescentam esses metadados. Uma ausência de resposta fora do perfil nunca estabelece que um serviço está fechado.

## Persistência e retorno de versão

O arquivo de preferências usa schema 2 e limite de 512 KiB. Ao carregar um arquivo schema 1, os campos antigos são preservados e os campos novos recebem os padrões. A gravação só o substitui após salvar uma cópia exata como `settings.v1-backup-<identificador>.json`. Se o backup falhar, o original permanece intacto. Schemas desconhecidos continuam somente para leitura.

Ao voltar à versão 2.0.5, seu leitor preserva o schema 2 e usa valores padrão. Para recuperar a configuração anterior, feche o aplicativo, guarde o `settings.json` atual e restaure o backup schema 1 como `settings.json`. Os perfis e tempos novos não existem no schema antigo. Credenciais continuam fora de ambos os arquivos.

Veja as capturas de [perfis](desktop-port-profiles.png) e [tempos](desktop-probe-timeouts.png) e o [registro de validação](validation-2.0.6.md). Desde a 2.0.7, o [cofre SNMP](credential-vault.md) usa schema 3 nas preferências e preserva o schema 2 em backup antes da gravação. A 2.0.8 acrescenta [controle de taxa de coletores](probe-rate-limit.md) e migração ao schema 4. Tema escuro e histórico permanecem incrementos separados.
