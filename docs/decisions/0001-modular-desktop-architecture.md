# 0001 — Pacote src e separação de responsabilidades

Status: aceita e implementada em 26/10/2026, versão 2.0.3.

## Contexto

O diretório `core/` reunia classificação, agendamento e implementações de rede. O scanner importava o coletor concreto, e o controlador Qt construía serviços diretamente. Recursos HTML usados na exportação ficavam dentro da interface. Os scripts alteravam `sys.path`, o que podia esconder erros de instalação. Havia dois pontos de entrada na raiz e configuração de build misturada com scripts de desenvolvimento.

## Decisão

Manter um único aplicativo desktop modular, instalado como `ip_scanner_helper` a partir de `src/`. Separar domínio, aplicação, infraestrutura e apresentação. Usar contratos Python `Protocol` e injeção por construtor ou parâmetro; `bootstrap.py` conecta os contratos às implementações existentes.

O scanner depende de `NetworkProbe`. O controlador recebe o serviço de varredura e um conjunto explícito de capacidades do desktop. O domínio não conhece sockets, Qt ou detalhes do Windows. A aplicação conhece seus contratos e o domínio. A apresentação não importa a infraestrutura. A construção dos objetos não inicia sondagens de rede.

Recursos compartilhados ficam no pacote `resources/`; QML e ícones ficam na apresentação. `pyproject.toml` declara os dados instaláveis. Os caminhos internos são relativos aos módulos, sem depender do diretório de trabalho.

`python -m ip_scanner_helper` e o comando instalado `ip-scanner-helper` chamam a mesma função CLI. O atalho de desenvolvimento fica em `scripts/executar.cmd`. O executável usa o mesmo ponto de entrada; o `.spec` e o hook Qt ficam em `packaging/windows/`.

## Consequências

A instalação editável é necessária para desenvolvimento. Os comandos antigos `python main.py` e `python scanner_rede.py` foram substituídos pelo comando do pacote. Imports antigos de `core` e `ui` também foram atualizados; não há promessa de API pública para esses módulos.

Testes de arquitetura fazem parte da suíte e impedem dependências entre camadas proibidas e ciclos de importação. Testes existentes preservam os contratos da varredura e da interface. A distribuição wheel é verificada com os recursos Qt e HTML e executada fora da árvore do projeto.

Os registros de inventário continuam usando o formato existente de dicionários para preservar as exportações e os vínculos QML. O controlador ainda coordena operações visuais, e os coletores especializados permanecem agrupados no adaptador de rede atual. Extrair novos casos de uso ou coletores separados deverá acompanhar uma necessidade concreta e seus testes.

## Referências

- [PyPA: src layout e flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).
- [PyInstaller: configuração por spec e inclusão de dados](https://pyinstaller.org/en/stable/spec-files.html).
