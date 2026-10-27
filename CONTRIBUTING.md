# Desenvolvimento

O projeto usa Python 3.11+ no Windows e um pacote instalado a partir de `src/`.

## Preparar o ambiente

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m ip_scanner_helper --demo
```

`scripts\executar.cmd --demo` é um atalho para o mesmo ambiente virtual. Ele localiza o Python a partir da própria pasta e não depende do diretório do terminal. Não instala dependências automaticamente. Para usuários finais, distribua o ZIP Windows completo gerado pelo build.

## Antes de abrir uma alteração

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/smoke_ui.py
.venv\Scripts\python.exe scripts/smoke_preferences.py
.venv\Scripts\python.exe scripts/smoke_vault.py
git diff --check
```

Os testes de domínio, aplicação, infraestrutura e apresentação ficam em pastas correspondentes. `tests/test_architecture.py` verifica os limites de importação, ciclos e execução do pacote instalado fora do repositório. O smoke test usa QML real e sondas simuladas; requer sessão gráfica.

Inclua testes que exercitem o comportamento alterado e atualize a documentação correspondente. Preserve as evidências dos dispositivos, a identidade das linhas por IP e o isolamento entre sessões de varredura. Uma ausência de resposta ICMP não permite descartar os outros métodos de presença.

## Onde colocar código novo

Consulte [arquitetura](docs/architecture.md) e a [decisão sobre a estrutura](docs/decisions/0001-modular-desktop-architecture.md).

- Regras de classificação, filtros e modelos sem I/O: `domain/`.
- Casos de uso, coordenação e contratos: `application/`.
- Windows, protocolos, arquivos e implementações dos contratos: `infrastructure/`.
- Estado Qt, modelo visual e QML: `presentation/`.
- Construção das dependências concretas: `bootstrap.py`.

Mantenha o domínio e a aplicação independentes de Qt e das implementações de rede. Não altere `sys.path` para fazer imports funcionarem. O ambiente de desenvolvimento usa instalação editável; uma distribuição instalada precisa funcionar sem a árvore do repositório.

## Build e distribuição

```powershell
.venv\Scripts\python.exe -m pip install -e ".[build]"
.venv\Scripts\python.exe scripts/build_windows.py
.venv\Scripts\python.exe scripts/package_release.py
```

A versão é definida em `pyproject.toml`. O build usa esse valor para a pasta de saída e os metadados do executável. A autoverificação usa dados fictícios. O empacotamento exige o executável validado e verifica se as fontes ou o binário mudaram desde a validação.

Execute builds em uma pasta por versão e distribua toda a pasta do aplicativo, incluindo `_internal`. Os ZIPs e `SHA256SUMS.txt` ficam em `dist/portfolio/`; são artefatos para anexar a uma GitHub Release, fora do versionamento do código.

Backups, ambientes virtuais, inventários privados, logs, estudos em `docs/melhorias/` e arquivos locais de agentes permanecem fora do Git e do ZIP de fonte. A distribuição Python também inclui somente o pacote declarado em `src/`.
