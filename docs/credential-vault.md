# Cofre de credenciais SNMP

A versão 2.0.7 acrescenta a aba **Cofre SNMP** em Preferências. É possível cadastrar, renomear, trocar a comunidade e excluir até 32 credenciais SNMP v1/v2c. Cada credencial tem identificador estável, nome, comunidade e ambiente opcional.

## Como usar

1. Abra Preferências → Cofre SNMP e escolha Nova.
2. Informe nome e comunidade. Opcionalmente, vincule a um ambiente com nome exclusivo.
3. Use Salvar credencial. O campo de comunidade é limpo após a gravação e não é preenchido ao editar.
4. Escolha Usar na próxima coleta ou selecione a credencial em Opções → Credencial SNMP.
5. Para digitar uma comunidade sem guardá-la, selecione Entrada manual. Somente nesse modo o campo manual é utilizado.

Ao editar, comunidade vazia mantém o valor existente; preencher o campo substitui o segredo. Excluir pede confirmação na própria aba. As operações do cofre são gravadas pelos seus botões e são independentes dos rascunhos de coleta/perfis/tempos. Fechar a aba não desfaz uma credencial já salva ou excluída. O campo de segredo é limpo ao fechar o diálogo.

Uma credencial vinculada preenche o ambiente quando o usuário a seleciona explicitamente. A referência da credencial é lembrada, mas o ambiente não é confirmado automaticamente na próxima abertura. Informe o ambiente correspondente ou selecione novamente a credencial. Um ambiente divergente bloqueia a coleta. A comparação usa o mesmo nome normalizado em Unicode NFC, preservando maiúsculas/minúsculas e espaços internos.

Se o cofre estiver indisponível, a credencial tiver sido excluída ou não puder ser aberta, a coleta com essa referência é bloqueada. Não há substituição automática por `public`, tentativa em cascata de comunidades ou escolha por CIDR/interface. O mapeamento de switches resolve a mesma seleção explícita ao iniciar sua operação.

## Armazenamento e proteção

O arquivo fica em `%LOCALAPPDATA%\IPScannerHelper\credentials.vault`, separado de `settings.json`. Todo o conteúdo, incluindo nomes e ambientes, é protegido com DPAPI no contexto do usuário. Apenas um cabeçalho de formato permanece legível. O arquivo é limitado a 128 KiB e a comunidade, a 255 bytes UTF-8. Espaços significativos da comunidade são preservados.

A implementação usa `CryptProtectData`/`CryptUnprotectData`, sem `CRYPTPROTECT_LOCAL_MACHINE`, com `CRYPTPROTECT_UI_FORBIDDEN` e prompt nulo. Usa um identificador fixo do aplicativo como entropia adicional, que não é uma senha secreta. Buffers nativos de saída são liberados com `LocalFree`; buffers nativos de texto claro são limpos antes da liberação.

A proteção normalmente depende do usuário e do computador/perfil do Windows; há exceções descritas pela Microsoft, como perfis móveis. Ela não cria isolamento contra outros processos que já executem no mesmo contexto de usuário. A API e suas condições estão na documentação de [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata) e [CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata).

O segredo é descriptografado em memória para uso pelo coletor. A aplicação não garante eliminação de todas as cópias de strings da memória do Python/Qt. DPAPI protege o armazenamento local; SNMP v1/v2c mantém seu formato de transmissão existente. Esta entrega não implementa SNMP v3 nem armazenamento de senhas Telnet.

## Gravação, falhas e recuperação

O cofre é validado antes de qualquer alteração. A proteção acontece antes de abrir o arquivo temporário, que recebe somente dados protegidos. A escrita usa `flush`, `fsync` e substituição atômica no mesmo diretório. Um bloqueio cooperativo de arquivo serializa alterações entre instâncias; outra gravação concorrente falha com mensagem para tentar novamente. O arquivo auxiliar `.vault.lock` não contém credenciais, e o bloqueio é liberado quando o handle é fechado.

Arquivo inválido, adulterado, versão desconhecida ou falha de descriptografia não faz o aplicativo apagar/recriar o cofre. Falhas de proteção ou substituição preservam o arquivo anterior. Não existe reset automático nem exportação do cofre nesta entrega.

Uma cópia pode não abrir em outra conta ou máquina. Para restaurar uma cópia compatível, feche o aplicativo, preserve o arquivo atual e restaure `credentials.vault` no mesmo perfil do Windows. Se o contexto de proteção não estiver disponível, recadastre as credenciais. Guardar/restaurar um arquivo antigo também recupera segredos que tenham sido substituídos ou excluídos depois dessa cópia.

## Sessões, configurações e distribuição

A comunidade é resolvida uma vez ao iniciar a varredura e capturada em `ScanOptions` imutável, com representação que omite o segredo. Editar/excluir uma credencial afeta operações futuras; a sessão ativa mantém o valor capturado. `state`, rascunhos de preferências e listagem de credenciais recebem somente metadados públicos. Credenciais não são copiadas para registros de dispositivos ou exportações.

O `settings.json` passa ao schema 3 e contém somente `credential_id`, além das preferências existentes. Arquivos schema 1/2 recebem backup exato antes da primeira gravação no novo schema. Ao retornar à 2.0.6, feche o app, preserve o settings atual e restaure o backup `settings.v2-backup-*.json` como `settings.json`. O cofre permanece separado; a versão anterior não o utiliza.

Mensagens brutas de exceções nas etapas de SNMP, coordenação e tarefas auxiliares não são registradas/exibidas; os logs mantêm contexto e tipo de falha. Isso reduz o detalhamento desses erros em favor da proteção dos parâmetros. Demonstração e autoverificação não constroem nem acessam o cofre pessoal. Arquivos `.vault`/`.vault.lock` ficam fora do Git e dos ZIPs de fonte/Windows.

Veja a [tela do cofre](desktop-credential-vault.png) e a [validação 2.0.7](validation-2.0.7.md). A 2.0.8 entrega o [controle de sondas por segundo](probe-rate-limit.md), com schema 4 e backup do schema 3. O cofre mantém seu formato separado. Agrupamento lógico do mapa segue como próximo incremento.
