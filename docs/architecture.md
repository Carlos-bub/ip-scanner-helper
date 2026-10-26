# Arquitetura e decisões

## Separação entre coleta e interface

`ScanOptions` é uma configuração imutável capturada antes da execução. Nenhuma tarefa de rede lê `StringVar`, `IntVar` ou widgets. `scan_device` recebe um endereço, opções, evento de cancelamento e um snapshot do cache ARP; retorna um registro ou `None`.

`ScanService` agenda até duas vezes o número de workers em tarefas pendentes. A lista de endereços é validada antes da alocação e possui limite de 4.096 destinos. Assim, a aplicação não materializa uma rede `/8` e não cria uma fila ilimitada de futures.

Cada execução recebe um identificador próprio e seu próprio evento de cancelamento. O serviço não aceita sobreposição. O consumidor descarta eventos de outras sessões. A parada cancela tarefas pendentes e solicita cancelamento às demais entre as operações de rede. Ela não interrompe uma função nativa no meio da chamada.

Todas as exceções das futures são lidas e transformadas em eventos de erro. A conclusão informa endereços analisados, total, erros e estado de cancelamento. Nenhuma parada é promovida artificialmente a 100%.

Um `QTimer` do `ScannerController` consome até 200 eventos de varredura e 20 conclusões auxiliares por ciclo. Apenas a thread principal altera o estado Qt e o modelo da tabela. Tarefas auxiliares entregam dados por fila, com tokens que descartam resultados substituídos. A interface declara seus vínculos em QML e não executa sondas de rede.

## Evidências e identificação

`ui/qml/Main.qml` concentra o layout e os detalhes; tema e controles reutilizáveis ficam em arquivos separados. `InventoryModel`, derivado de `QAbstractTableModel`, fornece as células para o `TableView`, que reutiliza os delegados visíveis. O controlador mantém a seleção por IP, por isso ordenar ou configurar colunas não altera o equipamento associado às ações. `core/inventory.py` implementa busca, filtros e ordenação sem depender de Qt. Latências ausentes ficam ao final nas duas direções.

O painel lateral usa abas roláveis e começa fechado em qualquer largura de janela. A seleção simples não o abre; o usuário escolhe abrir pelo botão, duplo clique ou Enter. A tabela de IPs ocupa a largura disponível, e o painel só divide esse espaço enquanto estiver aberto. As opções de sondagem são capturadas no início da sessão, e seus controles ficam desativados durante a execução.

Uma entrada no cache ARP fornece somente um MAC anterior. O equipamento precisa responder agora a ARP, ICMP, TCP ou SNMP antes de entrar no inventário. Um MAC aproveitado do cache recebe essa origem explicitamente.

O nome prioriza `sysName`, DNS reverso, NetBIOS e certificado RDP, seguido das assinaturas de aplicação. Títulos de páginas e modelos não são tratados como comprovação de hostname. A origem permanece disponível no registro.

As regras de categoria são conservadoras e separadas do nome. Portas de impressão produzem confiança média; descrições SNMP específicas ou respostas PJL/ONVIF/SIP produzem confiança alta; RDP/SMB sozinhos indicam estação/servidor com confiança baixa. Não existe regra que declare Active Directory apenas pelo hostname ou por RDP.

A confiança é qualitativa. Não é uma avaliação de autenticidade criptográfica nem uma probabilidade calibrada. `visto_em` é registrado em UTC em formato ISO 8601.

## Protocolos

O codec SNMP compartilhado suporta comprimentos BER curtos e longos, OIDs com componentes em base 128, inteiros e os valores necessários às MIBs consultadas. Ele rejeita mensagens truncadas, comprimento indefinido, tags inesperadas e erros do agente.

As requisições usam IDs aleatórios e sockets UDP conectados ao destino. Uma resposta precisa ter o ID, versão e comunidade esperados. `sysName` e `sysDescr` são independentes: timeout de um não elimina o outro. Somente a comunidade configurada é consultada.

O walk compara componentes numéricos de OID, exige avanço estrito e verifica o limite da subárvore. Limites: 4.096 interfaces, 10.000 entradas de FDB e orçamento de 15 segundos por árvore. Resultados interrompidos são sinalizados como parciais. GETBULK e contextos por VLAN continuam no roadmap.

Certificados são lidos pela estrutura do subject ASN.1, sem confundir o CN do emissor com o nome do equipamento. A coleta TLS permite certificados locais não confiáveis; ela não autentica o equipamento.

## Mapas e exportações

`core/topology.py` modela agrupamentos lógicos e caminhos aprendidos em tabelas MAC. Não cria switches fictícios ou distribui hosts arbitrariamente entre switches. Uma observação FDB não prova adjacência física direta.

O HTML incorpora um template local e JSON escapado contra fechamento de `script`. O JavaScript usa `textContent` e elementos SVG criados pela API do DOM, sem inserir dados coletados em `innerHTML`. Não há recursos de CDN. O mapa permite filtro, busca, pan, zoom e seleção por teclado.

CSV neutraliza células que poderiam ser interpretadas como fórmulas. Listas e dicionários são serializados como JSON nas células. A exportação JSON mantém os tipos e campos de evidência.

## Validação e fronteiras

Os testes de regressão exercitam pacotes e falhas simuladas, concorrência, cancelamento, coleta parcial, entradas hostis e contratos do controlador Qt. O smoke test carrega QML real e usa `QTest` para cliques e teclas, com fixtures no lugar dos coletores. Também verifica a tela de switches e três tamanhos de janela. Não representa uma homologação de fabricantes.

## Distribuição

`ui/qt_app.py` resolve recursos a partir do próprio módulo, tanto no código quanto no diretório `_internal` do PyInstaller. O hook local de QtQml inclui os módulos de QML, modelos, controles Basic, templates e layouts usados pela tela. Navegador embutido, multimídia, 3D e Tkinter ficam fora do executável. O HTML abre no navegador padrão do sistema. PySide6 Essentials é a única dependência de execução declarada; Shiboken é instalado por ela.

A interface e o ponto de entrada utilizam Qt Quick. Os módulos da antiga interface Tkinter foram removidos, junto com seus scripts e testes exclusivos.

A interface local informa faixa e gateway, mas as sondas seguem o roteamento do sistema operacional. A base OUI é curada e incompleta. SNMP v1/v2c e Telnet são protocolos legados; SNMP v3 e um coletor SSH são evoluções previstas, sem prometer suporte existente.
