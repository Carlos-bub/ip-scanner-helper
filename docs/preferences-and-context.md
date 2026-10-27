# Preferências e contexto de rede

As preferências básicas da versão 2.0.5 ficam em `%LOCALAPPDATA%\IPScannerHelper\settings.json`. O aplicativo lembra tamanho/posição e maximização da janela, colunas visíveis e larguras, ordenação, última faixa, referência da interface, modo de consulta, concorrência e limite por IP. IP e nome permanecem visíveis. As larguras pertencem às chaves das colunas e sobrevivem à ocultação dos campos.

## Persistência

O arquivo possui `schema_version: 1` e um objeto `preferences` com campos permitidos explicitamente. Credenciais SNMP/Telnet, resultados, nomes de dispositivos e ambiente não são persistidos nesse arquivo. O caminho é resolvido na composição; o armazenamento recebe um caminho explícito e não faz I/O no construtor. `--demo` e `--self-check` não carregam nem gravam preferências pessoais.

As escritas usam arquivo temporário no mesmo diretório, `flush`, `fsync` e substituição atômica. A leitura tem limite de 64 KiB e valida tipos, limites, valores finitos e colunas conhecidas. Campos desconhecidos da versão atual são ignorados; campos reconhecidos ausentes usam padrões. Um arquivo inválido é preservado como `settings.invalid-<data>-<identificador>.json` antes de retornar aos padrões. Se não for possível preservá-lo, o aplicativo não o sobrescreve.

Uma versão de schema desconhecida permanece intacta e o armazenamento fica somente para leitura. Antes de salvar, o schema em disco é conferido novamente. Falhas são registradas e apresentadas na interface, sem impedir a varredura. Não há sincronização de preferências entre instâncias: quando duas instâncias gravam um schema compatível, prevalece a última gravação.

Para restaurar os padrões manualmente, feche o aplicativo e renomeie o `settings.json`; a próxima abertura usa os valores padrão. Mantenha o arquivo anterior para recuperação. Builds anteriores que não suportem o schema devem preservá-lo; as versões anteriores à implementação não o utilizam.

## Interface e sessão ativa

O diálogo trabalha com rascunho: Cancelar descarta a edição e Salvar valida os campos. Os controles de coleta também atualizam os valores para a próxima execução. Uma sessão já iniciada conserva seu `ScanOptions`, seus prazos e seu contexto, mesmo que o usuário salve novas preferências durante a coleta.

O adaptador lembrado é procurado por identificador; quando não existe identificador, usa-se o nome. Se o adaptador não estiver disponível, a seleção fica vazia. A descoberta não substitui a faixa manual/restaurada por uma rede arbitrária. Selecionar explicitamente uma interface continua sugerindo sua rede. A posição da janela é ajustada à área útil dos monitores presentes; coordenadas negativas válidas são mantidas. Maximizar conserva o último retângulo normal.

## Identidade da rede

Cada coleta recebe um `NetworkContext` imutável. Os metadados incluem expressão e hash dos alvos efetivos, contagem, interface/endereço/prefixo/gateway conhecidos, identificador de sessão e ambiente opcional. Uma interface escolhida descreve o contexto declarado: as sondas continuam usando as rotas do Windows, sem fixar o tráfego àquele adaptador.

Sem ambiente explícito, `comparison_scope` é exclusivo da sessão. A mesma faixa ou o mesmo adaptador não estabelece que duas coletas ocorreram na mesma rede física. Para declarar o ambiente, informe um nome exclusivo em Opções, como `Matriz — escritório`. O nome é normalizado em Unicode NFC e convertido em identificador estável; maiúsculas/minúsculas e espaços internos são significativos. Reutilize exatamente o nome apenas quando quiser declarar o mesmo ambiente. O campo começa vazio a cada abertura.

Quando o ambiente foi informado, o escopo combina seu identificador com o hash dos alvos. Dois ambientes com o mesmo CIDR permanecem distintos. Esses metadados preparam o histórico futuro; ainda não há banco SQLite ou comparação persistente. `ScanService.context` e o evento `finished` devolvem cópias defensivas. Alterar a interface após a coleta não reclassifica os resultados ou o gateway usado no mapa. CSV e JSON continuam no formato existente de lista de dispositivos, sem introduzir metadados de sessão no nível de cada equipamento.

## Próximos incrementos

As próximas partes de configurações são perfis de portas, limites específicos por sonda e credenciais em armazenamento protegido separado. Depois, preferências de agrupamento do mapa e histórico. Esta entrega não inclui cofre, tema escuro, agendamento ou vinculação automática de ambientes.
