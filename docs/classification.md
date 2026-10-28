# Critérios de classificação

A categoria é uma inferência sobre os dados coletados. Confiança é qualitativa,
sem percentual estatístico nem garantia de identidade do equipamento. As respostas
da rede são declarações dos serviços; podem estar incompletas ou configuradas
incorretamente.

## Evidências e precedência

1. **Alta:** descrição SNMP ou assinatura específica de produto/gerência, PJL e
   ONVIF. As palavras e expressões são delimitadas: `ilo` não corresponde a `pilot`.
2. **Média:** convenções explícitas de hostname, função SIP ou assinatura SSDP de
   mídia. `SRV01`, `SRV-ARQUIVOS` e `FIN-PC01` são convenções reconhecidas;
   `administracao-01`, `apple-01` e números patrimoniais genéricos não são.
3. **Inconclusiva / baixa:** nenhuma evidência suficiente ou categorias distintas
   no nível mais forte disponível. A primeira regra encontrada não desempata um
   conflito. A justificativa preserva as fontes e as categorias conflitantes.

Uma descrição explícita de Windows 11 prevalece sobre o nome `SRV-LAB` ou uma
porta IPP aberta. Descrições explícitas de categorias distintas deixam a categoria
inconclusiva. Evidências concordantes do nível vencedor aparecem na justificativa.

São classificadas as descrições SNMP de câmeras e telefones, além das interfaces
Web e protocolos dedicados. Um banner de distribuição Linux ou software FTP
genérico informa software disponível, sem distinguir estação e servidor.

Fabricante por OUI, virtualização, DNS reverso e portas abertas **não definem
categoria sozinhos**. SMB/RDP não distinguem estações de servidores; HTTPS não
transforma um computador em servidor. Os serviços encontrados e o fabricante
continuam disponíveis nos campos próprios. SIP indica função de telefonia,
sem confirmar que se trata de um telefone físico.

## Identidade e coleta

O nome de exibição mantém sua prioridade de apresentação. Um título Web, modelo,
banner ou texto de certificado não passa às regras de hostname. Para classificação,
o scanner fornece separadamente sysName SNMP, PTR e NetBIOS. A presença de PTR não
suprime NetBIOS; a consulta adicional respeita os prazos por sonda/IP, cancelamento
e limitador de admissões. Pode consumir parte do orçamento disponível.

Resultados antigos no SQLite não são reclassificados ao abrir o histórico. Uma
nova coleta usa os critérios atuais. Não há alteração de esquema ou de preferências.
Mais registros podem ficar não identificados quando só houver fabricante/portas.

## Exemplos de regressão

| Observação | Resultado |
| --- | --- |
| `Windows 11 Pro pilot workstation`, portas 445/631 | Estação; alta |
| SSH OpenSSH Ubuntu, portas 22/80 | Não identificado |
| Título Web `Admin` ou `SRV-ADMIN`, sem hostname | Não identificado |
| SNMP `Hikvision Network Camera` | CFTV; alta |
| PTR `maquina-01.example` e NetBIOS `SRV-ARQUIVOS` | Servidor; média |
| Hostnames `PC-LAB` e `SRV-LAB` | Inconclusivo; baixa |
| Windows 11 por SNMP e Proxmox no título Web | Inconclusivo; baixa |
| MAC Dell/VMware, com ou sem HTTPS | Não identificado |

Os testes usam dados fictícios e coletores simulados. Não medem a taxa de acerto
em uma rede real. A implementação mantém os três campos categoria, confiança e
justificativa consumidos pelo inventário, mapa, exportações e histórico.

Somente builds Windows já reconhecidas e não compartilhadas são mantidas nas
regras. As builds 9600, 19041 e 19042 foram retiradas por não distinguir cliente
e servidor. Referências da Microsoft: [build 19041 em Windows cliente e servidor](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/d3d12video/ns-d3d12video-d3d12_feature_data_video_extension_commands.md),
[build 19042](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/ne-winsvc-service_shared_registry_state_type)
e a
[documentação Microsoft para Windows 8.1 e Server 2012 R2](https://support.microsoft.com/en-us/servicing/os/windows/2016/01/ms16-007-description-of-the-security-update-for-windows-january-12-2016-3).
Referências das builds preservadas: [Windows Server](https://learn.microsoft.com/en-us/windows-server/get-started/windows-server-release-info)
e [Windows 11](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information).
