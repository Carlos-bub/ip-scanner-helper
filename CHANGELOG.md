# Changelog

## 2.1.0 — 2026-10-28

- Quatro páginas principais: Inventário, Topologia, IPAM e histórico, e Configurações; tabela inicial com largura preservada, sem reiniciar a coleta ao navegar.
- Central de configurações com seções Geral, Varredura, Portas TCP, Tempos, Cofre SNMP e Dados e arquivos; backup/restauração e abertura de pastas dos arquivos existentes.
- Temas claro, escuro e automático, com paleta semântica e schema 5; migração dos schemas 1–4 com backup exato antes da gravação.
- Rascunhos protegidos ao navegar/fechar; preferências aplicadas somente após gravação bem-sucedida, conservando opções da sessão ativa.
- Mapa nativo QML com grupos recolhíveis, busca, pan, zoom e acesso ao equipamento no inventário; layout compartilhado com o HTML, sem WebEngine e sem inferir cabos.
- Grade virtualizada de endereços no IPAM, preservando estados de observação, parcialidade, reservas e ausência de resposta, sem afirmar IP livre.
- 315 testes, seis scripts gráficos Qt e 12 cenários de mapa HTML aprovados; topologia nativa exercitada com 4.096 registros fictícios.

## 2.0.12 — 2026-10-28

- Classificação por evidências independentes, priorizando assinaturas explícitas e mantendo conflitos do mesmo nível como inconclusivos, com origem e assinatura na justificativa.
- Correspondência por palavras completas e convenções de hostname delimitadas, eliminando falsos positivos como `pilot`, `administracao-01` e `apple-01`.
- Títulos Web, modelos e certificados deixam de ser usados como hostname na classificação; reconhecimento SNMP de câmeras e telefones corrigido.
- Fabricante, portas, banners genéricos SSH/FTP e distribuição Linux deixam de determinar categoria sozinhos; serviços e fabricante permanecem no inventário.
- Builds Windows compartilhadas entre cliente e servidor removidas das assinaturas de categoria (9600, 19041 e 19042).
- NetBIOS consultado independentemente de PTR, respeitando os limites existentes por sonda e IP; simulações de coleta atualizadas.
- Novos testes de regressão para conflitos, prioridade das evidências, nomes, serviços e integração do scanner. Critérios em `docs/classification.md`.
- 311 testes e teste gráfico Qt aprovados; executável 2.0.12 autoverificado, com as 18 regressões de classificação também aprovadas contra o módulo empacotado.

## 2.0.11 — 2026-10-28

- Histórico SQLite com sessões, contexto, alvos, opções não secretas, evidências e estado final; checkpoints e worker com fila limitada, mantendo a tabela como tela principal.
- Abertura offline de inventários anteriores e comparação por ambiente, alvos e opções compatíveis, com alterações de nome/MAC/serviços e ausências inconclusivas quando a cobertura é insuficiente.
- Visão dos endereços da coleta, reservas e tags manuais separadas por ambiente, sem afirmar que um IP está livre.
- Backup SQLite consistente e restauração validada com backup prévio, migração versionada e preservação de bancos desconhecidos ou futuros.
- Histórico sem comunidades/senhas; bancos e arquivos auxiliares excluídos do Git e pacotes; demonstração/autoverificação isoladas dos dados pessoais.
- Classificações preservadas conforme o inventário, mantendo o trabalho separado de distinção entre estações e servidores.
- 289 testes, cinco scripts gráficos e 12 cenários de topologia aprovados; executável 2.0.11 autoverificado.

## 2.0.10 — 2026-10-27

- Consulta L2 sob demanda nos detalhes e menu da linha: LLDP/CDP, portas locais/remotas e VLANs por porta, com abas de vizinhos, participação em VLANs e cobertura.
- GETBULK v2c adaptativo, tratamento de `tooBig`, fallback GETNEXT e validação de limites/ordem dos OIDs; proteção contra componentes BER excessivos.
- Orçamento global e cancelamento nas consultas SNMP de switches; credencial e contexto capturados antes da execução, com dados parciais explícitos.
- IDs de chassi/porta tipados; correlação unilateral, recíproca, ambígua, divergente ou fora da janela local, sem presumir cabo direto nem TTL.
- PVID/tagged/untagged por Q-BRIDGE-MIB; índices LLDP, bridge e ifIndex distintos, sem inferência de modo acesso/trunk ou nome de interface pelo número da bridge.
- Mapa e diagramas distinguem caminhos FDB de relatos LLDP/CDP e preservam parcialidade, cobertura e múltiplas portas; observadores genéricos navegáveis sem mudança de categoria.
- 259 testes aprovados, quatro scripts Qt e 12 cenários de navegador. Validação simulada; interoperabilidade com switches reais permanece pendente.

## 2.0.9 — 2026-10-27

- Mapa offline com cabeçalho compacto, árvore como visão inicial e foco no ramo selecionado; zoom animado, pan, enquadramento e navegação sequencial entre switches.
- Painel de dispositivos por switch com categorias, busca, paginação e evidências; retorno à visão geral, estados do inventário e exemplo separado com estados fictícios.
- Grupos recolhíveis por categoria ou observador, malha e paginação para grandes inventários; posições calculadas sem sobreposição entre grupos de alturas diferentes.
- Relações separadas da geometria; caminhos FDB preservados, inclusive múltiplas portas e observadores externos, sem criar hierarquia física a partir do gateway.
- Exportações Draw.io/XML e DOT pelo aplicativo, com containers, referências e metadados; texto seguro e inventário completo independente dos filtros.
- Exemplo JSON com 129 equipamentos, gateway, servidores e seis switches; HTML autocontido e capturas reproduzíveis.
- 227 testes de regressão e teste de navegador com 11 cenários até 4.096 registros. LLDP/CDP e VLANs ficam para a próxima etapa.

## 2.0.8 — 2026-10-27

- Controle do início de coletores por segundo em Preferências → Coleta, compartilhado entre os IPs da sessão; padrão desativado e valores de 1 a 1.000 quando habilitado.
- Admissões espaçadas, sem créditos acumulados; espera cancelável dentro do prazo por IP, preservando evidências e indicadores de coleta incompleta.
- Alcance explícito na interface e documentação: coletores, sem limite individual de pacotes, portas de um lote TCP ou tentativas internas. Mapeamento de switches permanece separado.
- Configuração imutável por sessão e resumo de admissões; schema 4 com backup exato antes da migração de schemas 1/2/3, mantendo perfis, tempos e referência do cofre.
- 209 testes aprovados e três scripts gráficos validados com dados temporários e rede simulada.

## 2.0.7 — 2026-10-27

- Cofre de até 32 comunidades SNMP v1/v2c, com nome, ambiente opcional e identificador estável; edição sem revelar o segredo e exclusão com confirmação.
- Proteção DPAPI por usuário do Windows em arquivo separado, gravação atômica e bloqueio entre instâncias; cofre inválido/inacessível preservado.
- Seleção explícita para varredura e mapeamento de switches, com validação do ambiente e bloqueio quando a referência estiver indisponível; sem cascata ou fallback automático.
- Comunidade capturada no início da operação; edição/exclusão não altera a sessão ativa. Entrada manual permanece disponível por escolha explícita.
- Schema 3 guarda somente a referência; migração de schemas 1/2 com backup. Demonstração/autoverificação isoladas do cofre pessoal.
- Representações e mensagens de erro sem segredo; arquivos de cofre excluídos do Git/ZIPs públicos. Sem alteração da proteção de transporte do SNMP.
- 195 testes e três scripts gráficos aprovados, incluindo DPAPI real com credenciais sintéticas, adulteração, concorrência e falhas de gravação.

## 2.0.6 — 2026-10-27

- Preferências divididas em Coleta, Perfis TCP e Tempos, mantendo a tabela como tela principal.
- Perfis Padrão, Infraestrutura, CFTV, Impressão e Servidores; criação, duplicação, edição e remoção de até oito perfis personalizados, com até 128 portas cada.
- Modelos imutáveis de protocolo, porta e serviço; consultas UDP específicas preservadas separadamente dos perfis TCP.
- Quinze limites por sonda/lote editáveis e persistentes, com restauração dos padrões e captura imutável na próxima sessão.
- Schema 2 com migração do schema 1 precedida de backup exato; configurações futuras preservadas para leitura e rollback documentado.
- Registros finais/exportações incluem perfil e portas TCP previstas, mantendo indicadores de consulta incompleta e portas aceitas antes do prazo.
- 172 testes aprovados, dois testes gráficos ampliados e cobertura/erros dos 24 cenários simulados preservados com o perfil Padrão.

## 2.0.5 — 2026-10-27

- Preferências básicas persistentes: janela, colunas e larguras, ordenação, última faixa, referência da interface, modo, concorrência e limite por IP.
- Tela de preferências com rascunho, validação, cancelar e salvar; alterações destinadas à próxima sessão, preservando a coleta em andamento.
- JSON versionado com substituição atômica, backup de arquivos inválidos e preservação de versões desconhecidas; credenciais e inventário excluídos.
- Contexto imutável por coleta com interface/prefixo, alvos e ambiente opcional informado explicitamente; a mesma faixa não vincula ambientes automaticamente.
- Resultados e gateway do mapa vinculados à coleta original, mesmo após mudar a interface para a próxima varredura.
- Restauração de adaptador por identificador, recuperação de janela após remover um monitor e largura das colunas mantida ao ocultar/exibir campos.
- Testes gráficos de preferências, rascunhos, sessão ativa, redimensionamento e janela maximizada; demonstração e autoverificação isoladas das preferências pessoais.

## 2.0.4 — 2026-10-26

- Política imutável de timeouts, prazos monotônicos por operação e orçamento cooperativo de 20 segundos por IP, ajustável em Opções.
- Dados válidos preservados ao atingir o limite; alvos sem presença confirmada ficam inconclusivos, sem dispositivos fictícios ou afirmação de IP livre.
- Contagem e lista de coletas incompletas separadas dos erros; motivos preservados na tabela, nos detalhes e nas exportações.
- PTR nativo com `DnsQueryEx`/`DnsCancelQuery`, limite de 64 contextos pendentes e liberação segura de respostas tardias; fallback limitado para `nslookup` somente quando a API estiver indisponível.
- Prazo total para o lote TCP, incluindo espera pela capacidade global, fechamento de pendências e preservação de portas já aceitas.
- Timeouts reduzidos ao tempo restante nas operações SNMP, UDP, banners, TLS/RDP e HTTP; campos SNMP válidos preservados quando uma consulta posterior for interrompida.
- Leitura HTTP em blocos e redirecionamentos limitados ao IP e às portas selecionadas, sem drenagem ilimitada de corpos; respostas HTTP de autenticação fechadas corretamente.
- 127 testes aprovados, teste gráfico ampliado e cobertura dos 24 cenários/tamanhos do benchmark preservada.

## 2.0.3 — 2026-10-26

- Aplicação instalada como `ip_scanner_helper` no layout `src/`, com domínio, aplicação, infraestrutura e apresentação separados.
- Coletor de rede e capacidades do desktop recebidos explicitamente; construção centralizada em `bootstrap.py`.
- Classificação e modelo de interface local no domínio; template HTML compartilhado fora da apresentação Qt.
- Entrada única por `python -m ip_scanner_helper` e comando instalado; atalho de desenvolvimento em `scripts/executar.cmd`.
- Configuração PyInstaller em `packaging/windows/`, metadados derivados da versão do projeto e build com autoverificação obrigatória.
- Empacotamento verifica fontes e executável validados antes de gerar os ZIPs públicos.
- Testes organizados por camada; verificações de dependências, ciclos e execução fora do repositório adicionadas.
- Guia de contribuição e decisão de arquitetura documentados; CI instala o pacote em vez de depender da árvore da raiz.

## 2.0.2 — 2026-10-26

- Descoberta IPv4 por `GetAdaptersAddresses`, incluindo prefixos, múltiplos endereços e gateway; PowerShell permanece como fallback.
- Publicação antecipada de presença, seguida da identificação completa no mesmo IP, preservando detecção TCP/SNMP com ICMP bloqueado.
- Modelo Qt atualiza células e insere/remove linhas sem reset quando a ordem relativa é preservada; seleção e detalhes continuam vinculados ao IP.
- Coleta interrompida ou incompleta explicitamente indicada no registro e nos detalhes.
- Métricas gerais de duração, CPU do processo, primeiro resultado e parada; diagnóstico detalhado opcional por sonda.
- Progresso consolidado por lote de futures concluídas, reduzindo eventos redundantes.
- Benchmark do scanner e coordenador com seis cenários simulados e quatro tamanhos, comparado com a referência 2.0.1.
- 92 testes aprovados e smoke test Qt ampliado para presença antes do DNS e enriquecimento posterior.
- Remoção dos módulos, scripts e teste exclusivos da antiga interface Tkinter; ponto de entrada de compatibilidade mantém o aplicativo Qt.
- Empacotamento de fonte exclui estudos internos e arquivos locais de agentes; convenções de fim de linha adicionadas ao repositório.

## 2.0.1 — 2026-10-23

- Primeiro incremento do plano de melhorias: coleta TCP não bloqueante do mesmo perfil de 13 portas.
- Limite global de 256 sockets pendentes compartilhado entre workers, com espera cancelável e liberação em erros/timeouts.
- ICMP nativo do Windows com assinaturas explícitas para handles/ponteiros; fallback limitado para `ping.exe` se a API estiver indisponível.
- Latência continua sendo o RTT recebido, incluindo o limite “< 1 ms”; erro de alcance não comprova presença.
- Benchmark TCP reproduzível com sockets simulados para 32, 254, 1.024 e 4.096 alvos, comparando cobertura com a implementação serial anterior.
- Teste real de ICMP e TCP restrito a loopback, novos testes de recursos/cancelamento e suíte de 76 testes aprovada.
- Detecção de equipamentos que respondem somente por SNMP preservada; nenhum descarte baseado apenas em falha de ping.


## 2.0.0 — 2026-10-23

- Migração da interface principal para PySide6 / Qt Quick com componentes QML próprios.
- Tabela virtualizada de IPs em toda a largura; detalhes abertos somente por ação explícita.
- Controles, tipografia, espaçamentos, cabeçalhos e estados de foco redesenhados.
- Layout validado em 960×640, 1100×720 e 1440×900, com opções de interface acessíveis na janela compacta.
- Navegação por setas, Enter, duplo clique, menu de contexto e ajuste de colunas.
- Fila de eventos consumida pelo loop Qt; resultados de tarefas antigas descartados.
- Telas de portas SNMP, importação MAC e Telnet migradas para QML.
- Exportação HTML independente do toolkit, com abertura no navegador padrão.
- 13 testes novos para contratos do controlador e smoke test com interação real na tela Qt.
- Build com módulos QML selecionados, sem runtime Tkinter, WebEngine ou módulos 3D.
- Interface e distribuições 1.2 preservadas para referência.

## 1.2.0 — 2026-10-23

- Tabela de IPs em toda a largura como foco principal, com IP na primeira coluna.
- Detalhes fechados por padrão; abertura apenas por ação explícita do usuário.
- Cabeçalho em grafite, paleta neutra, acento verde contido e indicadores em uma faixa compacta.
- Filtros em uma única linha, tipografia e espaçamentos revisados e barras de rolagem discretas.
- Remoção de emojis decorativos e revisão dos textos da interface.
- Marca geométrica própria e ícones para a janela e o executável Windows.
- Capturas atualizadas da tabela, dos detalhes sob demanda e da janela compacta.

## 1.1.0 — 2026-10-23

- Nova tela principal com configuração, indicadores e inventário em áreas distintas.
- Painel lateral com abas de identidade, serviços e evidências, separado da confiança da categoria.
- Painel recolhido automaticamente em janelas menores, com abertura manual e divisor ajustável.
- Filtros de identificação incompleta, pesquisa por serviço e normalização de acentos.
- Colunas configuráveis e ordenação numérica de IP e latência; medições ausentes ficam ao final.
- Opções avançadas recolhidas, tempo decorrido, contadores e visualização dos erros.
- Controles nativos com navegação por teclado e dimensionamento baseado na escala do Tk.
- Mapa com disposição por grupos e seleção do caminho para consultar a porta aprendida.
- Testes das novas regras de apresentação e smoke test ampliado com escalas Tk 125%/150%.
- Capturas desktop e exemplos atualizados para apresentação do projeto.

## 1.0.0 — 2026-10-23

### Correções

- Compatibilidade dos campos arredondados com as telas de switch e Telnet.
- Leitura compartilhada de BER/SNMP, incluindo comprimentos longos, OIDs e validação da resposta.
- Remoção da sondagem TCP/161 como indicador de SNMP UDP.
- Cancelamento por execução, prevenção de sobreposição e descarte de resultados antigos.
- Exceções de tarefas registradas e progresso que distingue conclusão, erros e interrupção.
- Atualização dos widgets pelo loop principal do Tk.
- Cache ARP deixa de comprovar presença atual e tempos fixos deixam de representar latência.
- Remoção da aproximação OUI por dois octetos e das classificações indevidas de MAC privado e AD.
- Remoção de cinco prefixos OUI conflitantes e da tentativa automática de comunidades alternativas.
- Identificação de certificados pelo subject e namespaces explícitos no probe ONVIF.
- Coleta de tabelas maiores com indicação de limites e resultados parciais.
- Mapa sem atribuição arbitrária de hosts a switches e serialização HTML segura.

### Organização

- Motor e coordenador independentes da interface, configuração imutável e eventos por sessão.
- Templates e demonstração fictícia incluídos como recursos do pacote.
- Modo `--demo`, exportação de demonstração e instruções de empacotamento.
- Metadados em `pyproject.toml`, `.gitignore`, testes e workflow de CI.
- Logs rotativos e documentação de arquitetura, evidências e limitações.
