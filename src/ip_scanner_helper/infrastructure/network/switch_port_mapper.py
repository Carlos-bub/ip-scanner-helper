"""
Mapeador Multi-Protocolo de Portas e Hosts de Switches (Switch Port & MAC Table Mapper).
Suporta Múltiplos Métodos de Descoberta:
1. SNMP Bridge-MIB / Q-BRIDGE / IF-MIB (com comunidade configurada).
2. Telnet / CLI Scraper Automatizado (comandos show mac address-table / display mac-address).
3. Importador e Parser Inteligente Universal de Texto e Tabelas Web (copiar/colar de qualquer switch).
4. Diagnóstico em Tempo Real de Portas de Gerenciamento (HTTP, HTTPS, SSH, Telnet, SNMP).
Implementado em Python puro sem dependências externas.
"""

import socket
import time
import re
import logging

from ip_scanner_helper.infrastructure.network.snmp import (encode_oid, decode_oid, build_request, parse_response, query, oid_parts, SnmpError)

from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.infrastructure.network.snmp_walk import walk_tree, WalkResult

logger = logging.getLogger(__name__)
from ip_scanner_helper.domain.oui_database import identificar_fabricante_e_tipo


# ==============================================================================
# 1. MOTOR SNMP (Bridge-MIB & IF-MIB)
# ==============================================================================

def build_snmp_getnext(community, req_id, oid_str):
    return build_request(oid_str, community, request_id=req_id, next_oid=True)


def parse_snmp_response(data):
    """Compatibility wrapper; all callers share the strict BER implementation."""
    try:
        response = parse_response(data)
        return response.values[0] if response.values else (None, None, None)
    except SnmpError:
        logger.debug("Pacote SNMP inválido")
        return None, None, None


def snmp_walk_tree(ip, community, root_oid, timeout=0.8, max_reps=10000, budget=15, *, context=None, version=1):
    result = walk_tree(ip, community, root_oid, timeout, max_reps, budget,
                       context=context, version=version, query_fn=query)
    if result.partial:
        logger.debug("Coleta SNMP parcial em %s (%s): %s", ip, root_oid, result.reason)
    return result


# ==============================================================================
# 2. DIAGNÓSTICO DE PORTAS E AUTODESCOBERTA DE COMUNIDADE SNMP
# ==============================================================================

def testar_porta_tcp(ip, port, timeout=0.15):
    """Verifica se uma porta TCP está aberta e respondendo."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        res = s.connect_ex((ip, port))
        s.close()
        return res == 0
    except Exception:
        return False


def testar_snmp_comunidade(ip, community, timeout=0.35):
    try:
        values = query(ip, "1.3.6.1.2.1.1.1.0", community, timeout=timeout)
        return any(oid == "1.3.6.1.2.1.1.1.0" and tag == 4 for oid, tag, _ in values)
    except (OSError, SnmpError):
        return False


def diagnosticar_servicos_switch(ip, community="public"):
    """
    Executa um diagnóstico rápido em paralelo das portas de gerência do switch.
    Testa apenas a comunidade configurada, sem adivinhar credenciais.
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_http = ex.submit(testar_porta_tcp, ip, 80, 0.15)
        f_https = ex.submit(testar_porta_tcp, ip, 443, 0.15)
        f_ssh = ex.submit(testar_porta_tcp, ip, 22, 0.15)
        f_telnet = ex.submit(testar_porta_tcp, ip, 23, 0.15)
        f_comm = ex.submit(testar_snmp_comunidade, ip, community, 0.35)

        http_ok = f_http.result()
        https_ok = f_https.result()
        ssh_ok = f_ssh.result()
        telnet_ok = f_telnet.result()
        comm_encontrada = community if f_comm.result() else None

    return {
        "http": http_ok,
        "https": https_ok,
        "ssh": ssh_ok,
        "telnet": telnet_ok,
        "snmp": comm_encontrada is not None,
        "comunidade_snmp": comm_encontrada
    }


# ==============================================================================
# 3. PARSER INTELIGENTE UNIVERSAL DE TEXTO / TABELAS DE SWITCHES
# ==============================================================================

def normalizar_mac(mac_raw):
    """Padroniza qualquer formato de MAC para XX:XX:XX:XX:XX:XX."""
    mac_clean = re.sub(r'[^0-9A-Fa-f]', '', mac_raw).upper()
    if len(mac_clean) == 12:
        return ':'.join(mac_clean[i:i+2] for i in range(0, 12, 2))
    return None


def extrair_tabela_mac_texto(texto):
    """
    Analisa qualquer saída de texto ou tabela copiada de CLI/Web de switches
    (Cisco, Intelbras, Aruba/HP, TP-Link, Mikrotik, UniFi, Huawei, Dell, etc.)
    e extrai pares (mac_normalizado, nome_porta).
    """
    linhas = texto.strip().splitlines()
    resultados = []

    regex_mac = re.compile(
        r'([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}|'
        r'[0-9A-Fa-f]{4}[\.-][0-9A-Fa-f]{4}[\.-][0-9A-Fa-f]{4}|\b[0-9A-Fa-f]{12}\b)'
    )

    # Expressões para identificar nomes explícitos de portas
    regex_interface_forte = re.compile(
        r'\b(Gi(?:gabitEthernet)?[\d/]+|Fa(?:stEthernet)?[\d/]+|Te(?:nGigabitEthernet)?[\d/]+|'
        r'eth(?:er)?\d+|lan\d+|ge-?[\d/]+|xe-?[\d/]+|\d+/\d+(?:/\d+)?|'
        r'Port\s*\d+|Porta\s*\d+|swp\d+|trunk\d+|agg\d+)\b',
        re.IGNORECASE
    )

    ignorar_tokens = {
        'dynamic', 'static', 'learned', 'aging', 'secure', 'active', 'forwarding',
        'vlan', 'self', 'permanent', 'status', 'type', 'action', 'enabled', 'disabled',
        'true', 'false', 'yes', 'no', 'up', 'down', 'inactive', 'ok', 'normal',
        'bridged', 'unicast', 'multicast', 'broadcast', 'none', 'learned-dynamic',
        'vlan1', 'vlan10', 'vlan100', 'vlan20', 'mac', 'address', 'port', 'ports'
    }

    for linha in linhas:
        linha_str = linha.strip()
        if not linha_str or linha_str.startswith('---') or linha_str.startswith('==='):
            continue

        m_mac = regex_mac.search(linha_str)
        if not m_mac:
            continue

        mac_raw = m_mac.group(1)
        mac_norm = normalizar_mac(mac_raw)
        if not mac_norm:
            continue

        # 1. Tenta identificar por regex de interface forte
        m_port = regex_interface_forte.search(linha_str)
        if m_port:
            porta = m_port.group(1).strip()
            # Corrige espaçamento como "Port 1"
            porta = re.sub(r'\s+', ' ', porta)
        else:
            # 2. Divide tokens da linha
            tokens = [t.strip() for t in re.split(r'[\t,;\s]+', linha_str) if t.strip()]
            porta = "Porta Desconhecida"

            # Prioridade para número de porta explícito (ex: "Port", "12" ou token numérico final)
            candidatos_num = []
            candidatos_palavra = []
            for t in tokens:
                if t == mac_raw:
                    continue
                t_clean = t.lower().strip(',;()[]')
                if t_clean in ignorar_tokens or t_clean.startswith('vlan'):
                    continue
                if t.isdigit() and 1 <= int(t) <= 128:
                    candidatos_num.append(f"Porta {t}")
                elif len(t) <= 24:
                    candidatos_palavra.append(t)

            if candidatos_num:
                # Se tiver número, pega o último número não-vlan
                porta = candidatos_num[-1]
            elif candidatos_palavra:
                porta = candidatos_palavra[-1]

        resultados.append((mac_norm, porta))

    return resultados


def processar_macs_para_portas(pares_mac_porta, lista_dispositivos_rede=None):
    """
    Recebe lista de tuplas (mac, nome_porta) e cruza com a lista de dispositivos escaneados,
    retornando a lista padronizada de portas formatada para a UI.
    """
    mapa_hosts = {}
    if lista_dispositivos_rede:
        for d in lista_dispositivos_rede:
            mac = d.get("mac", "").upper().replace("-", ":")
            if mac and mac != "DESCONHECIDO":
                mapa_hosts[mac] = d

    # Agrupa MACs por Porta
    porta_para_macs = {}
    for mac, porta in pares_mac_porta:
        if porta not in porta_para_macs:
            porta_para_macs[porta] = []
        if mac not in porta_para_macs[porta]:
            porta_para_macs[porta].append(mac)

    def chave_ordenacao_porta(nome_p):
        """Ordena portas naturalmente (ex: Porta 1, Porta 2, Porta 10, Gi1/0/1)."""
        nums = re.findall(r'\d+', nome_p)
        if nums:
            return (0, [int(n) for n in nums], nome_p)
        return (1, [], nome_p)

    portas_ordenadas = sorted(porta_para_macs.keys(), key=chave_ordenacao_porta)
    resultado = []

    for idx, p_nome in enumerate(portas_ordenadas, start=1):
        macs_conectados = porta_para_macs[p_nome]

        hosts_detalhados = []
        for mac in macs_conectados:
            if mac in mapa_hosts:
                hosts_detalhados.append(mapa_hosts[mac])
            else:
                fab, tipo = identificar_fabricante_e_tipo(mac)
                hosts_detalhados.append({
                    "ip": "IP Não escaneado / Outra Subrede",
                    "nome": f"[{fab}] {tipo}",
                    "fabricante": fab,
                    "tipo": tipo,
                    "mac": mac,
                    "origem": "Tabela MAC Switch"
                })

        eh_uplink = len(macs_conectados) >= 3

        resultado.append({
            "numero": idx,
            "nome": p_nome,
            "status": "Link UP",
            "qtd_macs": len(macs_conectados),
            "eh_uplink": eh_uplink,
            "macs": macs_conectados,
            "hosts": hosts_detalhados
        })

    return resultado


# ==============================================================================
# 4. CLIENTE TELNET / CLI EM PYTHON PURO (SEM BIBLIOTECAS EXTERNAS)
# ==============================================================================

IAC = bytes([255])
DONT = bytes([254])
DO = bytes([253])
WONT = bytes([252])
WILL = bytes([251])

def telnet_iac_handler(sock, data):
    """Responde negociacoes Telnet (IAC) para manter sessao aberta sem bloqueio."""
    res = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 255 and i + 2 < len(data):
            cmd = data[i+1]
            opt = data[i+2]
            if cmd == 253:  # DO -> WONT
                sock.sendall(IAC + WONT + bytes([opt]))
            elif cmd == 251:  # WILL -> DONT
                sock.sendall(IAC + DONT + bytes([opt]))
            i += 3
        else:
            res.append(data[i])
            i += 1
    return bytes(res)


def coletar_via_telnet(ip, usuario="admin", senha="", porta=23, timeout=6.0, lista_dispositivos=None):
    """
    Conecta via Telnet (porta 23) ao switch, envia credenciais e comandos
    'show mac address-table' / 'display mac-address' / 'show fdb', e analisa a resposta.
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(timeout, 1.0))
        sock.connect((ip, porta))

        buffer = bytearray()
        hora_inicio = time.time()

        # Le ate receber prompt de login ou password
        login_enviado = False
        senha_enviada = False
        comando_enviado = False
        saida_acumulada = ""

        while time.time() - hora_inicio < timeout:
            try:
                chunk = sock.recv(2048)
                if not chunk:
                    break
                limpo = telnet_iac_handler(sock, chunk)
                buffer.extend(limpo)
                texto_atual = buffer.decode('utf-8', 'ignore').lower()

                if not login_enviado and ("login:" in texto_atual or "username:" in texto_atual or "user:" in texto_atual):
                    sock.sendall(usuario.encode('utf-8') + b'\r\n')
                    login_enviado = True
                    buffer.clear()
                    time.sleep(0.3)
                    continue

                if not senha_enviada and ("password:" in texto_atual or "senha:" in texto_atual):
                    sock.sendall(senha.encode('utf-8') + b'\r\n')
                    senha_enviada = True
                    buffer.clear()
                    time.sleep(0.5)
                    continue

                # Detecta prompt de comando pronto (>, #, ], $)
                if (senha_enviada or login_enviado or not ("login" in texto_atual or "password" in texto_atual)) and not comando_enviado:
                    if any(p in texto_atual for p in [">", "#", "]", "$"]):
                        # Envia comandos de desabilitar paginacao e consultar tabela MAC
                        sock.sendall(b"terminal length 0\r\n")
                        time.sleep(0.2)
                        sock.sendall(b"screen-length 0 temporary\r\n")
                        time.sleep(0.2)
                        sock.sendall(b"show mac address-table\r\n")
                        time.sleep(0.3)
                        sock.sendall(b"show mac-address-table\r\n")
                        time.sleep(0.3)
                        sock.sendall(b"display mac-address\r\n")
                        time.sleep(0.3)
                        sock.sendall(b"show fdb\r\n")
                        comando_enviado = True
                        buffer.clear()
                        continue

                if comando_enviado:
                    saida_acumulada += limpo.decode('utf-8', 'ignore')

            except socket.timeout:
                if comando_enviado and saida_acumulada:
                    break
                continue
            except Exception:
                break

        sock.close()

        if saida_acumulada:
            pares = extrair_tabela_mac_texto(saida_acumulada)
            if pares:
                return processar_macs_para_portas(pares, lista_dispositivos)

    except OSError:
        logger.debug("Falha na coleta Telnet: %s", ip, exc_info=True)
    finally:
        if sock is not None:
            sock.close()

    return []


# ==============================================================================
# 5. CLASSE PRINCIPAL SWITCH PORT MAPPER
# ==============================================================================

class SwitchPortMapper:
    """Motor Unificado de Descoberta de Portas e Hosts de Switches."""

    @staticmethod
    def mapear_switch(ip_switch, community="public", lista_dispositivos_rede=None, *, context=None):
        """
        Consulta o Switch via SNMP Bridge-MIB.
        Usa exclusivamente a comunidade informada pelo usuário.
        """
        mapa_hosts = {}
        if lista_dispositivos_rede:
            for d in lista_dispositivos_rede:
                mac = d.get("mac", "").upper().replace("-", ":")
                if mac and mac != "DESCONHECIDO":
                    mapa_hosts[mac] = d

        comm_ativa = community
        context = context or ProbeContext.standalone(30)
        walks = []

        def collect(root, timeout=0.5, max_reps=10000):
            result = snmp_walk_tree(ip_switch, comm_ativa, root, timeout, max_reps, budget=5, context=context)
            walks.append(result)
            return result

        # 1. Nomes das Interfaces / Portas (IF-MIB)
        port_names = {}
        if_names = collect("1.3.6.1.2.1.31.1.1.1.1", timeout=0.4, max_reps=4096)
        if not if_names:
            if_names = collect("1.3.6.1.2.1.2.2.1.2", timeout=0.4, max_reps=4096)

        for oid, val in if_names.items():
            try:
                if_idx = int(oid.split('.')[-1])
                nome = val.decode('utf-8', 'ignore') if isinstance(val, bytes) else str(val)
                port_names[if_idx] = nome
            except Exception:
                pass

        # 2. Status das Portas (IF-MIB: 1.3.6.1.2.1.2.2.1.8 - ifOperStatus: 1=up, 2=down)
        port_status = {}
        oper_status = collect("1.3.6.1.2.1.2.2.1.8", timeout=0.5, max_reps=4096)
        for oid, val in oper_status.items():
            try:
                if_idx = int(oid.split('.')[-1])
                port_status[if_idx] = "Link UP" if val == 1 else ("Link DOWN" if val == 2 else "Outro estado")
            except Exception:
                pass

        # 3. Mapeamento BridgePort -> IfIndex (1.3.6.1.2.1.17.1.4.1.2: dot1dBasePortIfIndex)
        bridge_to_if = {}
        base_ports = collect("1.3.6.1.2.1.17.1.4.1.2", timeout=0.5, max_reps=4096)
        for oid, val in base_ports.items():
            try:
                b_port = int(oid.split('.')[-1])
                if_idx = int(val)
                bridge_to_if[b_port] = if_idx
            except Exception:
                pass

        # 4. Tabela de Enderecos MAC Aprendidos (Bridge-MIB: 1.3.6.1.2.1.17.4.3.1.2 - dot1dTpFdbPort)
        fdb_entries = collect("1.3.6.1.2.1.17.4.3.1.2", timeout=0.8, max_reps=10000)

        # Bridge ports and ifIndex are distinct namespaces. Missing mappings
        # remain explicit and cannot collide with an interface with the same number.
        porta_para_macs = {}

        def add_fdb(entries, root, suffix_size):
            for oid, bridge_port in entries.items():
                if type(bridge_port) is not int or not 1 <= bridge_port <= 65535:
                    continue  # port zero means the learned port is not known.
                if not oid.startswith(root + "."):
                    continue
                try:
                    suffix = tuple(int(item) for item in oid[len(root) + 1:].split("."))
                except ValueError:
                    continue
                if len(suffix) != suffix_size or any(not 0 <= item <= 255 for item in suffix[-6:]):
                    continue
                mac = ":".join(f"{item:02X}" for item in suffix[-6:])
                interface = bridge_to_if.get(bridge_port)
                key = interface if type(interface) is int and interface > 0 else -bridge_port
                porta_para_macs.setdefault(key, []).append(mac)

        add_fdb(fdb_entries, "1.3.6.1.2.1.17.4.3.1.2", 6)
        if not porta_para_macs:
            root = "1.3.6.1.2.1.17.7.1.2.2.1.2"
            qfdb_entries = collect(root, timeout=0.8, max_reps=10000)
            add_fdb(qfdb_entries, root, 7)  # FDB ID is not necessarily a VLAN ID.

        # Monta a estrutura final organizada
        resultado_portas = []
        todas_portas = sorted(list(set(list(port_names.keys()) + list(porta_para_macs.keys()))))

        for p_idx in todas_portas:
            nome_p = port_names.get(p_idx, f"ifIndex {p_idx}") if p_idx > 0 else f"Bridge porta {-p_idx} (ifIndex não mapeado)"
            status_p = port_status.get(p_idx, "Status não consultado")
            macs_conectados = sorted(set(porta_para_macs.get(p_idx, [])))

            if ("vlan" in nome_p.lower() or "null" in nome_p.lower() or "loopback" in nome_p.lower()) and not macs_conectados:
                continue

            hosts_detalhados = []
            for mac in macs_conectados:
                if mac in mapa_hosts:
                    hosts_detalhados.append(mapa_hosts[mac])
                else:
                    fab, tipo = identificar_fabricante_e_tipo(mac)
                    hosts_detalhados.append({
                        "ip": "IP Não escaneado / Outra Subrede",
                        "nome": f"[{fab}] {tipo}",
                        "fabricante": fab,
                        "tipo": tipo,
                        "mac": mac,
                        "origem": "Switch FDB (Bridge MIB)"
                    })

            eh_uplink = len(macs_conectados) >= 3

            resultado_portas.append({
                "numero": p_idx if p_idx > 0 else -p_idx,
                "if_index": p_idx if p_idx > 0 else None,
                "nome": nome_p,
                "status": status_p,
                "qtd_macs": len(macs_conectados),
                "eh_uplink": eh_uplink,
                "uplink_confirmado": False,
                "coleta_parcial": any(getattr(walk, "partial", False) for walk in walks),
                "macs": macs_conectados,
                "hosts": hosts_detalhados
            })

        return resultado_portas

    @staticmethod
    def mapear_por_texto(texto_bruto, lista_dispositivos_rede=None):
        """Mapeia portas e dispositivos a partir de texto bruto colado pelo usuário."""
        pares = extrair_tabela_mac_texto(texto_bruto)
        return processar_macs_para_portas(pares, lista_dispositivos_rede)

    @staticmethod
    def mapear_por_telnet(ip_switch, usuario="admin", senha="", porta=23, lista_dispositivos_rede=None):
        """Conecta via Telnet e mapeia portas automaticamente."""
        return coletar_via_telnet(ip_switch, usuario, senha, porta, lista_dispositivos=lista_dispositivos_rede)
