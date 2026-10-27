# Topologia interativa — 2.0.9

O botão **Mapa da rede** abre uma página local no navegador padrão. A tabela continua sendo a tela principal do aplicativo. O mapa é um snapshot do inventário e das observações disponíveis na exportação; não consulta equipamentos nem usa serviços externos.

## Explorar a árvore

A página abre em **Árvore**, com cabeçalho compacto, equipamentos principais visíveis e dispositivos finais recolhidos. Selecionar um switch abre seu ramo, aproxima a visualização com uma transição e mostra um painel com os dispositivos observados por ele. O foco mantém somente esse ramo no canvas, evitando cruzamentos com outros switches.

- **Próximo switch** e a seta anterior percorrem os switches/observadores da visualização, mantendo o painel aberto. Sem filtros, todos os switches do inventário são acessíveis nessa sequência; a ordem segue o inventário, sem afirmar que os switches possuem ligação física entre si.
- **Visão geral** fecha o painel, recolhe ramos, limpa os filtros e restaura o enquadramento inicial.
- O painel permite buscar entre todos os dispositivos do switch e acessar páginas de 24 resultados. O canvas mostra até 12 dispositivos por ramo; os demais continuam acessíveis pelo painel. As categorias e quantidades aparecem acima da lista.
- **Evidências** preserva origem, confiança, identificação parcial e os caminhos registrados. Selecionar um dispositivo da lista abre suas evidências; **Voltar ao switch** retorna à lista.
- **Ajustes** reúne filtros, exibição de relações e expansão/recolhimento. As opções de **Grupos** mantêm agrupamento por categoria ou por observador FDB. **Malha** mostra as relações entre os nós visíveis.
- Arrastar move o mapa; a roda e os botões ajustam o zoom. **Enquadrar** ajusta a visualização atual. `Ctrl+F` busca, `Tab` percorre controles, `Enter`/espaço ativa nós, as setas movem o canvas focado e `Esc` fecha os detalhes. O foco por teclado reposiciona o canvas quando necessário. A preferência de movimento reduzido desativa a animação.

Em telas menores, o cabeçalho reflui e o painel funciona como sobreposição. Fechá-lo devolve a área ao mapa. Labels possuem fundo próprio e recorte visual; nome completo e evidências permanecem no título e no painel.

## Relações e estados

Na coleta real, o gateway é uma **referência da interface**. Sua existência não cria ligações com servidores ou switches. A disposição em níveis organiza a leitura; não constitui uma hierarquia física descoberta. Servidores só recebem essa categoria quando o inventário a informa: um registro “Estação / Servidor” não é promovido automaticamente a servidor.

FDB informa onde um MAC foi aprendido. As linhas são tracejadas e identificadas como caminhos; podem existir equipamentos intermediários. Vários caminhos e portas para o mesmo IP são preservados, sem escolher um switch pai. Observadores fora do inventário ficam como referências explícitas, sem acrescentar equipamentos confirmados. Os demais ficam em **Sem associação registrada**, sem linhas fictícias para o gateway.

Novos resultados de mapeamento registram origem (SNMP, Telnet ou texto importado) e instante de registro. Observações antigas sem esses campos informam a ausência; não recebem uma data inventada. Os detalhes preservam todos os caminhos do equipamento, inclusive quando um extremo não aparece na página atual.

No inventário, verde indica equipamento inventariado nesta coleta; âmbar indica identificação parcial. Isso não garante presença contínua após o snapshot. Ausência de resposta, cancelamento ou tempo esgotado não produz um estado offline. A coleta física LLDP/CDP e a identificação de VLANs ficam para a próxima etapa, conforme o recorte escolhido pelo usuário.

## Exemplo de hierarquia completa

Abra [o exemplo interativo](demo-topology-tree.html) ou veja a [visão geral](topology-overview.png) e o [foco de um switch](topology-switch-focus.png).

O arquivo `resources/demo_topology.json` contém **129 equipamentos**: gateway, dois servidores, seis switches e 120 dispositivos finais. As relações descrevem explicitamente gateway → servidores → switches e interligações de switches. Estados online/offline e relações são **fictícios**, exibidos com essa identificação. Esse conjunto fica separado do inventário coletado; não ensina o aplicativo a presumir essas conexões em uma rede real.

Para alterar o exemplo, edite `nodes` (IP, nome, tipo e `state`) e `links` (`from`/`to`), mantendo os IPs de origem/destino presentes. Execute `python scripts/export_demo.py` para gerar novamente o HTML autocontido. Esse exemplo não cria um gateway de roteamento ou um serviço web.

## Grandes inventários

Grupos começam recolhidos. A busca revela os resultados e mantém o contexto necessário, incluindo ancestrais declarados no exemplo e observadores FDB. Grupos e equipamentos principais são paginados em conjuntos de até 12. Cada grupo aberto renderiza até 12 cartões, e a malha usa até 12 resultados mais quatro observadores de contexto por página, com até 200 caminhos desenhados. O painel preserva acesso ao conjunto completo.

O layout usa a maior altura real de cada linha e reposiciona os elementos ao mudar o viewport. O cálculo de posições fica separado das relações. Foram verificados inventários vazios, 1, 10, 100, 500 e 4.096 registros, grupos desiguais e milhares de grupos de observadores. Não há meta de tempo de renderização homologada para todas as máquinas; os testes e seus limites estão na [validação](validation-2.0.9.md).

## Exportação editável

Em **Exportar**, o aplicativo oferece:

- **Draw.io / Diagrams.net (`.drawio` ou `.xml`)**: XML não comprimido, com páginas **Categorias** e **Árvore FDB**, containers recolhíveis, equipamentos, referências externas e caminhos. A árvore pode representar o mesmo IP em mais de um grupo para preservar múltiplos caminhos. Origem, instante e `direct_link_confirmed=false` ficam nos dados das relações.
- **Graphviz (`.dot`)**: grafo dirigido com clusters de categoria, nós únicos por IP e todas as relações FDB, incluindo observadores externos. Não é `strict`, preservando caminhos paralelos. O gateway informado aparece como contexto do diagrama, sem criar uma aresta.

Os formatos exportam o inventário completo, independentemente dos filtros da tabela. A paginação do navegador não recorta esses arquivos. Diagramas não herdam posição, zoom ou ramo aberto no HTML; o usuário pode reorganizá-los no editor de destino.

Exemplos com o inventário fictício pequeno: [Draw.io](demo-topology.drawio), [XML](demo-topology.xml) e [DOT](demo-topology.dot). A página Categorias do XML usa uma representação de cada IP; a página Árvore usa referências quando necessário.

Os arquivos seguem a [estrutura XML documentada pelo Draw.io](https://www.drawio.com/docs/reference/diagram-generation/) e a [linguagem DOT do Graphviz](https://graphviz.org/doc/info/lang.html). A validação local verifica estrutura, referências, dados, escape e cobertura; importação manual nos editores e renderização pelo executável Graphviz não foram realizadas neste ambiente.

## Segurança e arquitetura

Os scripts e ícones SVG são locais e incorporados no HTML final. Texto coletado entra no DOM por `textContent`, com JSON protegido contra fechamento de `script`. O XML usa labels de texto simples (`html=0`) e tooltips escapados; o DOT usa strings entre aspas com escape. Segredos não são atributos exportados pelo modelo da topologia.

`domain/topology.py` mantém os nós, grupos e relações tipadas, sem posições. `topology-layout.js` contém a geometria; `topology-map.js` controla a interação. HTML e diagramas são gerados na infraestrutura, conectada ao Qt pela composição do aplicativo. Não foram acrescentadas bibliotecas de grafos, navegador embutido, Node ou dependências npm ao executável. Node.js 24 e Edge/Chrome são usados somente pelo teste de desenvolvimento.
