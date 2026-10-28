# Validação local — 2.0.12 — 28/10/2026

Correção das regras de classificação e da entrega de evidências pelo scanner.
Ambiente: Windows 10 x64, Python 3.14.6 e PySide6 Essentials 6.12.0.

| Verificação | Resultado |
| --- | --- |
| Suíte completa | 311 testes aprovados; 22 novos testes de regressão de domínio e integração |
| Correspondência | Fragmentos `ilo`/`pilot`, abreviações `ad`/`administracao` e `ap`/`apple` separados |
| Serviços e fabricante | Portas isoladas/combinadas, OUI e SSH/FTP genéricos não determinam função |
| Evidências explícitas | Descrições SNMP de câmeras e telefones reconhecidas; evidência forte prevalece sobre hostname/portas |
| Conflitos | Categorias distintas no nível mais forte deixam resultado inconclusivo, com as fontes na justificativa |
| Coleta | PTR e NetBIOS independentes; título Web de aparência `SRV-ADMIN` não entra como hostname |
| Builds Windows | 9600, 19041 e 19042 não estabelecem categoria; builds reconhecidas não ambíguas preservadas |
| Interface | Teste Qt de inventário aprovado: filtros, detalhes, três larguras, identificação progressiva e limite por IP; zero avisos QML |
| Build | Executável 2.0.12 gerado com PyInstaller 6.22.2 e autoverificação aprovada; 18 testes de domínio repetidos contra o módulo extraído do próprio executável |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

O primeiro teste gráfico revelou que a fixture ainda não substituía NetBIOS após
PTR. Os mocks dos cenários do serviço e da interface foram completados; a suíte
e o teste gráfico passaram depois da correção. Os endereços de teste são fictícios,
em `192.0.2.0/24`; não foi realizada varredura da LAN ou homologação de equipamentos.

Os [critérios](classification.md) explicam a precedência, os casos inconclusivos e
a redução intencional de categorias baseadas apenas em fabricante ou serviços.
Os inventários já armazenados permanecem como foram coletados.

A homologação em rede autorizada segue pendente, incluindo classificação com
referência conhecida, persistência/backup em uso normal e LLDP/CDP/VLANs em switches
reais. Depois dessa validação, o próximo incremento funcional previsto é E6,
começando pelo agendamento local sem sobreposição.
