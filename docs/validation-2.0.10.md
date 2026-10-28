# Validação local — 2.0.10 — 27/10/2026

Ambiente: Windows 10 x64, Python 3.14.6, PySide6 Essentials 6.12.0, PyInstaller 6.22.2, Node.js 24.18.0 e Edge 156.0.4314.42 headless.

| Verificação | Resultado |
| --- | --- |
| Regressão | 259 testes aprovados, incluindo arquitetura, contratos do inventário, preferências e cofre |
| GETBULK | PDU BER com non-repeaters/repetições corretos; 30 variáveis em quatro chamadas no agente simulado; redução por tooBig, fallback GETNEXT, v1 com GETNEXT, orçamento, cancelamento e limite de entradas |
| Pacotes inválidos | OID repetido, fora de ordem, externo inferior ao cursor, subárvore numérica, excesso de bindings, componentes de mais de 32 bits/128 arcos e OID binário hostil tratados como erro de protocolo |
| LLDP/CDP | Índices remotos e endereços de gerenciamento, subtipos arbitrários, portas sem correspondência, protocolos separados e idade desde alteração sem inventar TTL |
| Correlação | Dois lados e portas exatas, contexto, janela temporal, nome fraco, candidato duplicado, chassi divergente, porta ausente/divergente e múltiplas portas; sem conversão de FDB em cabo |
| VLANs | Bitmaps MSB-first, porta bridge diferente de ifIndex, PVID separado, tagged/untagged, bitmap inconsistente/ausente e versões de linha sem mistura; modo acesso/trunk não inferido |
| Controlador | IP, comunidade, prazo e contexto capturados; cancelamento e descarte de tarefa antiga; erro/tentativa vazia parcial preservam observação anterior; segredo ausente do estado e snapshot |
| Qt Quick | Inventário, preferências, cofre e diálogo L2 aprovados; vizinhos/VLAN/cobertura, refresh, Interromper e fechamento, janela 960×640; zero avisos QML |
| Navegador | 12 cenários até 4.096 registros, incluindo árvore/malha L2, observador genérico sem reclassificação, dois protocolos/portas, FDB distinto, vizinho sem IP, VLAN parcial e texto hostil; zero erros JS e nenhuma requisição externa da página |
| Diagramas | Relações reported_neighbor e fdb_path distintas, origem, instante, porta remota, situação, expiração desconhecida e direct_link_confirmed=false; cobertura/parcialidade nos detalhes |
| Build | Executável 2.0.10 com autoverificação aprovada; hash/fingerprint correspondentes às fontes; módulos L2 no PYZ e arquivos QML novos conferidos |
| Wheel | Pacote 2.0.10 gerado; todos os módulos e recursos do pacote comparados byte a byte às fontes |
| Distribuição | ZIPs de fonte e Windows gerados, integridade CRC e SHA-256 conferidas; estudos internos, cofre e configurações locais excluídos |

Reprodução:

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -q
.venv\Scripts\python.exe -B scripts/smoke_ui.py
.venv\Scripts\python.exe -B scripts/smoke_preferences.py
.venv\Scripts\python.exe -B scripts/smoke_vault.py
.venv\Scripts\python.exe -B scripts/smoke_l2.py --capture
.venv\Scripts\python.exe -B scripts/smoke_topology.py
.venv\Scripts\python.exe -B scripts/export_demo.py
.venv\Scripts\python.exe -B scripts/build_windows.py
.venv\Scripts\python.exe -B scripts/package_release.py
```

O teste L2 renderiza o diálogo real e usa cliques de mouse com um coletor substituído. Um nome SNMP com tags HTML permanece literal e o componente confirma `Text.PlainText`. Os testes SNMP usam respostas/pacotes em memória; não houve varredura de LAN, captura de tráfego ou consulta a switches reais. O cofre foi verificado com DPAPI real e segredos sintéticos em arquivos temporários. A CI inclui o novo smoke test, mas sua execução remota não foi verificada.

O resultado de 30 variáveis em quatro chamadas demonstra batching no agente simulado; não mede duração real, PPS ou compatibilidade entre fabricantes. O coletor L2 exige v2c e permissões para as MIBs. Não oferece v3, descoberta recursiva, modo de porta proprietário ou TTL restante. A janela de cinco minutos é política local de correlação. A presença de dados em tabelas não certifica cabeamento nem estado contínuo da rede.

XML/DOT foram conferidos estruturalmente, com referências, escape e metadados. Não houve importação manual no Draw.io, validação XSD ou renderização Graphviz nesta etapa. Homologação física e laboratório com suporte incompleto/tabelas grandes continuam pendentes. Consulte o [guia L2](l2-discovery.md) e o [guia do mapa](topology.md).
