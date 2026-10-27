# Validação local — 2.0.9 — 27/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0, PyInstaller 6.22.2, Node.js 24.18.0 e Edge 156.0.4314.42 headless.

| Verificação | Resultado |
| --- | --- |
| Regressão | 227 testes aprovados, incluindo arquitetura e contratos existentes do scanner, preferências e cofre |
| Modelo | Grupos sem posições; nenhum nó central ou aresta de associação fictícia; gateway como contexto; múltiplos caminhos/portas preservados; observador externo explícito |
| Origem | Novos mapeamentos registram fonte e instante; observações antigas mantêm ausência explícita; referência FDB não se converte em vizinhança física |
| Layout | Geometria pura de grupos, árvore e malha verificada em cinco larguras; grupos desiguais sem sobreposição; posições reais do DOM também verificadas |
| Navegador | 11 cenários: vazio, 1, 10, 100, 500 e 4.096 registros; grupo de 4.096 membros; 4.096 grupos de observadores; múltiplos caminhos; inventário pequeno de exemplo; hierarquia com 129 equipamentos |
| Fluxo da árvore | Cabeçalho até 60 px no desktop, clique real por CDP, aproximação animada, ramo enquadrado sem corte dos cartões, painel de dispositivos, busca local, sequência dos seis switches e retorno à visão geral |
| Acessibilidade | Ativação por teclado, manutenção do foco após renderização/paginação e acompanhamento do nó focado após zoom em janela compacta |
| Escala | Grupos/pais paginados; cartões de dispositivos limitados por visualização; busca encontra o último registro de 4.096; paginação de malha e de milhares de grupos |
| Segurança do HTML | Nome com tentativa de fechar script/inserir imagem permanece texto; nenhuma imagem injetada, exceção JS ou requisição externa da página |
| Exemplo | JSON separado com gateway, servidores, seis switches e dispositivos; estados online/offline e relações fictícios não entram no modelo de coleta real |
| Diagramas | XML parseável com duas páginas, IDs/referências válidos e relações completas; DOT com strings escapadas, múltiplos caminhos e referências externas; dados de 500 dispositivos preservados |
| Integração Qt | CSV/JSON/HTML/Draw.io/XML/DOT exportam inventário completo após filtro; diálogo Draw.io gera arquivo editável; scripts de inventário, preferências e cofre aprovados, sem avisos QML |
| Build | Executável 2.0.9 com autoverificação aprovada; recursos JS/JSON/XML e wheel conferidos; fingerprint e hash do executável correspondem às fontes |
| Pacotes | ZIPs de código e Windows com integridade/hashes conferidos; estudos internos, dados pessoais, cofre, caches e configurações de agentes fora dos artefatos públicos |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/smoke_vault.py
.venv\Scripts\python.exe -B scripts/smoke_topology.py --capture
.venv\Scripts\python.exe -B scripts/export_demo.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

O teste de topologia cria HTMLs sintéticos em `build/topology-smoke/`, abre o navegador com perfil temporário e usa CDP local. O relatório identifica versão do navegador, duração do conjunto de ações por cenário, erros JS e quantidade de requisições de arquivo. As durações incluem navegação, cliques, esperas e capturas; não representam um benchmark isolado de renderização. O código verifica contenção dos caminhos temporários antes da limpeza; arquivos ainda bloqueados pelo Windows são identificados pelo teste.

Não houve varredura de LAN, coleta LLDP/CDP ou validação de VLANs. A posição do gateway e dos demais elementos não comprova conectividade física. Não há medição de desempenho para toda combinação de hardware/driver/navegador. A CI foi ampliada com Node e o teste headless, mas sua execução remota não foi verificada.

XML/DOT foram validados por estrutura, referências, escape e metadados; não houve importação manual no Draw.io nem renderização pelo binário Graphviz. A consulta à especificação oficial orientou os formatos. A tentativa de baixar o XSD oficial para validação adicional foi bloqueada pelo proxy local; não se afirma validação por XSD. Consulte o [guia de topologia](topology.md) para uso, limites e exemplos.
