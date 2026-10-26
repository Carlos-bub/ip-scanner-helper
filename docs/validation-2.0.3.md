# Validação local — 2.0.3 — 26/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0 e PyInstaller 6.22.2. A matriz remota Python 3.11/3.14 continua definida no CI; esta validação local foi executada com Python 3.14.

| Verificação | Resultado |
| --- | --- |
| Regressão | 96 testes aprovados na instalação editável e na wheel instalada |
| Arquitetura | Limites de importação e ausência de ciclos verificados; aplicação importada sem Qt nem implementações da infraestrutura |
| Pacote instalado | Wheel com 50 arquivos, incluindo QML, ícones, inventário fictício e template HTML; sem pacotes antigos `core`/`ui`, scripts ou estudos internos |
| Execução independente da raiz | Testes e smoke test executados a partir de `build/`, usando a wheel em `site-packages`; CLI também testada em diretório temporário isolado |
| Atalho | `scripts/executar.cmd --help` aprovado a partir de outra pasta, localizando o ambiente virtual pelo próprio caminho |
| Interface Qt | QML real, cliques, teclado, filtros, colunas, três larguras, switches, presença progressiva e seleção/rolagem preservadas; aprovado na instalação editável e na wheel |
| Cobertura do scanner | 24 cenários/tamanhos com coletor simulado injetado; mesmos registros finais e erros da referência 2.0.1, incluindo ICMP bloqueado e SNMP isolado |
| Build Windows | Executável 2.0.3, metadados 2.0.3.0, ícone, QML e recursos; autoverificação aprovada com código zero fora da pasta das fontes |
| Proteção do empacotamento | Identidade de fontes inválida e SHA-256 de executável inválido foram rejeitados antes de criar os ZIPs |
| Ambiente de desenvolvimento | Instalação editável restaurada após o teste da wheel |

O build Windows fica em `dist/portfolio/2.0.3/IP_Scanner_Helper/`; o registro da autoverificação em `build/windows/2.0.3/validated-build.json`. O benchmark de regressão desta reorganização fica em `build/benchmarks/architecture-2.0.3.json`. Esses caminhos são locais e ficam fora do Git.

As verificações usam dados fictícios ou respostas simuladas. Não foi feita varredura da LAN nem homologação em switches físicos. Os resultados verificam preservação de comportamento e distribuição; não demonstram melhoria de desempenho em rede real.

Os comandos `python main.py` e `python scanner_rede.py` foram substituídos por `python -m ip_scanner_helper`. O atalho passou a ser um auxiliar de desenvolvimento; o usuário final abre o executável do pacote Windows. Veja o [guia de contribuição](../CONTRIBUTING.md) para instalação e build.
