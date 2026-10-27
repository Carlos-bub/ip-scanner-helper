"""
Motor Multi-Protocolo de Descoberta de Rede e Resolução de Nomes.
Suporta: SNMP (v1/v2c), RDP (TLS :3389), SSL/TLS (:443/:8443),
Web Apps & Form Extractors, NetBIOS (UDP 137), DNS PTR e Port Scan.
"""

import socket
import struct
import ssl
import subprocess
import re
import urllib.request
import urllib.error
import ctypes
import logging
import os
import math
from uuid import uuid4
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urljoin, urlsplit

from ip_scanner_helper.infrastructure.network.certificates import certificate_name
from ip_scanner_helper.application.errors import ProbeTimeout
from ip_scanner_helper.application.timing import DEFAULT_TIMEOUTS, ProbeContext, operation_context
from ip_scanner_helper.infrastructure.network.tcp_probe import scan_tcp_ports
from ip_scanner_helper.infrastructure.network.windows_network import ping_ipv4
from ip_scanner_helper.infrastructure.network.windows_dns import query_ptr

from ip_scanner_helper.infrastructure.network.snmp import (encode_oid as encode_oid_value, encode_tlv, build_request, query, SnmpError)

logger = logging.getLogger(__name__)


class _ScopedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, ip, ports, timeout, context):
        self.ip, self.ports, self.timeout, self.context = ip, set(ports), timeout, context
        self.followed = 0

    def redirect_request(self, request, fp, code, message, headers, newurl):
        self.context.check()
        try:
            address = urlsplit(newurl)
            port = address.port or (443 if address.scheme == "https" else 80)
            if (self.followed >= 3 or address.scheme not in ("http", "https")
                    or address.hostname != self.ip or port not in self.ports
                    or address.username is not None or address.password is not None):
                return None
        except ValueError:
            return None
        self.followed += 1
        return super().redirect_request(request, fp, code, message, headers, newurl)

    def http_error_302(self, request, fp, code, message, headers):
        location = headers.get("Location") or headers.get("URI")
        if not location:
            return None
        redirect = self.redirect_request(request, fp, code, message, headers, urljoin(request.full_url, location))
        if redirect is None:
            return None
        # The stdlib handler drains fp.read() before following redirects. Close
        # instead, so a slow redirect body cannot bypass our per-IP deadline.
        fp.close()
        return self.parent.open(redirect, timeout=self.context.timeout(self.timeout))

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _read_http_body(response, timeout, context, limit=65536):
    chunks, received = [], 0
    while received < limit:
        context.check()
        transport = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        if transport is not None:
            transport.settimeout(context.timeout(timeout))
        chunk = response.read1(min(4096, limit - received))
        if not chunk:
            break
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


class NetworkResolver:
    """Motor avançado de resolução de nomes e identificação de equipamentos."""

    @staticmethod
    def encode_oid(oid_str):
        return encode_tlv(6, encode_oid_value(oid_str))

    encode_tlv = staticmethod(encode_tlv)

    @classmethod
    def build_snmp_get(cls, oid, community="public", version=0, req_id=101):
        return build_request(oid, community, version, req_id)

    @classmethod
    def query_snmp(cls, ip, custom_community="public", timeout=DEFAULT_TIMEOUTS.snmp, *, context=None):
        """Read the configured community; a missing field does not discard the other."""
        context = operation_context(timeout, context, factor=4)
        community = custom_community.strip() or "public"
        fields, version = [], 1
        try:
            for version in (1, 0):
                fields = []
                for oid in ("1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.1.0"):
                    value = None
                    context.check()
                    try:
                        for returned_oid, tag, raw in query(ip, oid, community, version, context.timeout(timeout), context=context):
                            if returned_oid == oid and tag == 4:
                                value = raw.decode("utf-8", errors="replace").strip() or None
                    except (OSError, SnmpError):
                        context.check()
                        logger.debug("SNMP sem resposta válida: %s / %s", ip, oid, exc_info=True)
                    fields.append(value)
                if any(fields):
                    return fields[0], fields[1], "SNMP v2c" if version == 1 else "SNMP v1"
        except ProbeTimeout as exc:
            if any(fields):
                exc.partial = (fields[0] if fields else None, fields[1] if len(fields) > 1 else None,
                               "SNMP v2c" if version == 1 else "SNMP v1")
            raise
        return None, None, None

    @staticmethod
    def query_rdp_hostname(ip, timeout=DEFAULT_TIMEOUTS.rdp, *, context=None):
        """Extrai o nome do host Windows diretamente do certificado TLS do RDP (Porta 3389)."""
        context = operation_context(timeout, context, factor=4)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((ip, 3389), timeout=context.timeout(timeout)) as s:
                s.settimeout(context.timeout(timeout))
                s.sendall(b'\x03\x00\x00\x13\x0e\xe0\x00\x00\x00\x00\x00\x01\x00\x08\x00\x03\x00\x00\x00')
                s.settimeout(context.timeout(timeout))
                _ = s.recv(1024)
                s.settimeout(context.timeout(timeout))
                with ctx.wrap_socket(s, server_hostname=ip) as ssock:
                    name = certificate_name(ssock.getpeercert(binary_form=True) or b"")
                    if name and name != ip:
                        return name
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_ssl_certificate(ip, ports=(443, 8443), timeout=DEFAULT_TIMEOUTS.tls, *, context=None):
        """Extrai o Subject CN, Organization ou Unit do certificado SSL/TLS (Portas 443 / 8443)."""
        context = operation_context(timeout, context, factor=max(1, len(ports)) * 2)
        for port in ports:
            context.check()
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                with socket.create_connection((ip, port), timeout=context.timeout(timeout)) as s:
                    s.settimeout(context.timeout(timeout))
                    with ctx.wrap_socket(s, server_hostname=ip) as ssock:
                        name = certificate_name(ssock.getpeercert(binary_form=True) or b"")
                        if name and name != ip:
                            return name, port
            except (OSError, ValueError):
                context.check()
                logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None, None

    @staticmethod
    def query_http_title(ip, ports=(80, 8080, 8000, 8443, 443), timeout=DEFAULT_TIMEOUTS.http, *, context=None):
        """Captura o hostname real embutido, modelo ou título da interface Web do equipamento (HTTP/HTTPS)."""
        context = operation_context(timeout, context, factor=max(1, len(ports)) * 2)
        for port in ports:
            context.check()
            try:
                proto = "https" if port in (443, 8443) else "http"
                url = f"{proto}://{ip}:{port}"
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                # Garante conexão DIRETA na LAN (ignora proxy S4/Squid/Sophos/Windows)
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}),
                    _ScopedRedirect(ip, ports, timeout, context),
                    urllib.request.HTTPSHandler(context=ctx)
                )

                with opener.open(req, timeout=context.timeout(timeout)) as resp:
                    server = resp.headers.get("Server", "")
                    raw = _read_http_body(resp, timeout, context).decode('latin1', errors='ignore')

                    # 1. TP-Link Archer / Roteadores com modelName embutido
                    m_tplink_model = re.search(r'modelName\s*=\s*["\']([^"\']+)["\']', raw)
                    m_tplink_desc = re.search(r'modelDesc\s*=\s*["\']([^"\']+)["\']', raw)
                    if m_tplink_model:
                        nome_tp = f"TP-Link {m_tplink_model.group(1).strip()}"
                        if m_tplink_desc:
                            nome_tp += f" ({m_tplink_desc.group(1).strip()})"
                        return nome_tp, port

                    # 2. Intelbras DVR / NVR (CFTV)
                    if 'projectPath.js' in raw and 'Intelbras' in raw:
                        return "Intelbras DVR / NVR (CFTV)", port
                    if 'PROJECT_URL="/nvr/"' in raw or 'devType="DVR"' in raw:
                        return "Intelbras DVR / NVR (CFTV)", port

                    # 3. Grandstream VoIP / Telefone IP / PABX
                    if "webapp/webapp.nocache.js" in raw:
                        return "Grandstream Telefone IP / VoIP", port

                    # 4. Switches Aruba Instant On (sysName / sysDescr)
                    m_sysname = re.search(r'name=["\']sysName["\'][^>]*value=["\']([^"\']+)["\']', raw, re.I)
                    if not m_sysname:
                        m_sysname = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']sysName["\']', raw, re.I)
                    if m_sysname:
                        name = m_sysname.group(1).replace("&nbsp;", " ").strip()
                        if name:
                            return name, port

                    m_sysdescr = re.search(r'name=["\']sysDescr["\'][^>]*value=["\']([^"\']+)["\']', raw, re.I)
                    if not m_sysdescr:
                        m_sysdescr = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']sysDescr["\']', raw, re.I)

                    # 5. Extração da tag <title>
                    m = re.search(r'<title[^>]*>(.*?)</title>', raw, re.IGNORECASE | re.DOTALL)
                    title = ""
                    if m:
                        title = re.sub(r'\s+', ' ', m.group(1)).strip()

                    # Filtra títulos genéricos de login ou loading
                    titulos_genericos = (
                        "loading...", "loading web application", "login", "index", "home", "document",
                        "404 not found", "welcome", "aruba - login form", "login form", "web switch",
                        "h3c httpd", "intelbras | login", "web image monitor", "intelbras"
                    )

                    if title and not any(gen == title.lower() or gen in title.lower() for gen in titulos_genericos):
                        return title, port
                    elif m_sysdescr:
                        descr_clean = m_sysdescr.group(1).replace("&nbsp;", " ").split(",")[0].strip()
                        if descr_clean:
                            return descr_clean, port

                    servidores_genericos = (
                        "apache", "nginx", "goahead", "goahead-webs", "embedded", "boa",
                        "micro_httpd", "lighttpd", "mini_httpd", "httpd", "microsoft-iis"
                    )
                    if server and len(server) > 2 and not any(gen in server.lower() for gen in servidores_genericos):
                        return server.strip(), port
            except urllib.error.HTTPError as e:
                try:
                    # 6. Extração via cabeçalho WWW-Authenticate (ex: Telefone IP Intelbras)
                    auth_hdr = e.headers.get("WWW-Authenticate", "")
                    m_realm = re.search(r'realm=["\']([^"\']+)["\']', auth_hdr, re.I)
                    if m_realm:
                        realm = m_realm.group(1).strip()
                        if "ip phone" in realm.lower() or "intelbras" in realm.lower():
                            return "Intelbras Telefone IP (VoIP)", port
                        elif len(realm) > 3 and not realm.lower().startswith("192."):
                            return realm, port
                finally:
                    e.close()
            except (OSError, ValueError):
                context.check()
                logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None, None

    @staticmethod
    def _udp_exchange(ip, port, payload, timeout, *, context=None):
        context = operation_context(timeout, context)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(context.timeout(timeout))
            sock.connect((ip, port))
            sock.send(payload)
            sock.settimeout(context.timeout(timeout))
            return sock.recv(65535)

    @staticmethod
    def query_netbios(ip, timeout=DEFAULT_TIMEOUTS.netbios, *, context=None):
        """Consulta de alta velocidade NetBIOS Name Service (UDP 137)."""
        context = operation_context(timeout, context, factor=1)
        try:
            query = (
                b'\x82\x28\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00'
                b'\x20\x43\x4b\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41'
                b'\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41'
                b'\x41\x41\x41\x41\x41\x00\x00\x21\x00\x01'
            )
            data = NetworkResolver._udp_exchange(ip, 137, query, timeout, context=context)
            if data[:2] != query[:2]:
                return None

            if len(data) > 56:
                num_names = data[56]
                for i in range(num_names):
                    offset = 57 + i * 18
                    if offset + 18 <= len(data):
                        name_bytes = data[offset : offset + 15]
                        name_type = data[offset + 15]
                        flags = int.from_bytes(data[offset + 16 : offset + 18], 'big')
                        is_group = bool(flags & 0x8000)
                        if name_type in (0x00, 0x20) and not is_group:
                            name = name_bytes.decode('latin1', errors='ignore').strip()
                            if name:
                                return name
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_dns_ptr(ip, timeout=DEFAULT_TIMEOUTS.dns_ptr, *, context=None):
        """Native PTR with cancellation; CLI only when the native API is unavailable."""
        context = operation_context(timeout, context).child(timeout)
        context.check()
        if os.name == "nt":
            try:
                return query_ptr(ip, timeout=timeout, context=context)
            except (OSError, AttributeError):
                logger.debug("DNS nativo indisponível; usando nslookup", exc_info=True)
        return NetworkResolver.query_dns_ptr_cli(ip, timeout=timeout, context=context)

    @staticmethod
    def query_dns_ptr_cli(ip, timeout=DEFAULT_TIMEOUTS.dns_ptr, *, context=None):
        """Bounded compatibility fallback for nslookup output in Portuguese/English."""
        context = operation_context(timeout, context).child(timeout)
        try:
            result = subprocess.run(
                ["nslookup", "-timeout=1", "-retry=1", ip], capture_output=True,
                timeout=context.timeout(timeout), creationflags=0x08000000 if os.name == "nt" else 0)
            text = result.stdout.decode("utf-8", errors="replace")
            match = re.search(r"^\s*(?:Name|Nome):\s*(\S+)", text, re.I | re.M)
            if result.returncode == 0 and match:
                name = match.group(1).rstrip(".")
                return name if name != ip else None
        except (OSError, subprocess.TimeoutExpired):
            context.check()
            logger.debug("DNS PTR indisponível: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_pjl_printer_model(ip, timeout=DEFAULT_TIMEOUTS.pjl, *, context=None):
        """Consulta o modelo exato da impressora via PJL (Porta RAW 9100)."""
        context = operation_context(timeout, context, factor=3)
        try:
            with socket.create_connection((ip, 9100), timeout=context.timeout(timeout)) as s:
                s.settimeout(context.timeout(timeout))
                s.sendall(b'\x1b%-12345X@PJL INFO ID\r\n\x1b%-12345X\r\n')
                s.settimeout(context.timeout(timeout))
                resp = s.recv(1024).decode('latin1', errors='ignore')
                m = re.search(r'"([^"]+)"', resp)
                if m:
                    model = m.group(1).strip()
                    if len(model) > 2 and model != "ID":
                        return model
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_ssh_banner(ip, timeout=DEFAULT_TIMEOUTS.ssh, *, context=None):
        """Lê o banner inicial de identificação SSH (Porta 22) para identificar SO / Equipamento."""
        context = operation_context(timeout, context, factor=2)
        try:
            with socket.create_connection((ip, 22), timeout=context.timeout(timeout)) as s:
                s.settimeout(context.timeout(timeout))
                banner = s.recv(256).decode('latin1', errors='ignore').strip()
                if banner.startswith("SSH-"):
                    if "mikrotik" in banner.lower():
                        return "MikroTik RouterOS (SSH)"
                    elif "cisco" in banner.lower():
                        return "Cisco Switch / Router (SSH)"
                    elif "ubuntu" in banner.lower():
                        return "Linux Ubuntu Server (SSH)"
                    elif "debian" in banner.lower():
                        return "Linux Debian Server (SSH)"
                    elif "dropbear" in banner.lower():
                        return "Linux Embedded / OpenWrt (SSH)"
                    elif "freebsd" in banner.lower() or "truenas" in banner.lower() or "freenas" in banner.lower():
                        return "FreeBSD / TrueNAS (SSH)"
                    elif len(banner) > 8:
                        partes = banner.split("-", 2)
                        if len(partes) >= 3:
                            return partes[2].strip()
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_ftp_banner(ip, timeout=DEFAULT_TIMEOUTS.ftp, *, context=None):
        """Lê o banner de boas-vindas do FTP (Porta 21) para identificar SO ou dispositivo."""
        context = operation_context(timeout, context, factor=2)
        try:
            with socket.create_connection((ip, 21), timeout=context.timeout(timeout)) as s:
                s.settimeout(context.timeout(timeout))
                banner = s.recv(256).decode('latin1', errors='ignore').strip()
                if banner.startswith("220"):
                    if "mikrotik" in banner.lower():
                        return "MikroTik RouterOS (FTP)"
                    elif "filezilla" in banner.lower():
                        return "FileZilla FTP Server"
                    elif "vsftpd" in banner.lower():
                        return "vsftpd Linux Server"
                    elif "proftpd" in banner.lower():
                        return "ProFTPD Linux Server"
                    elif "microsoft" in banner.lower():
                        return "Microsoft IIS FTP Service"
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_ssdp_device(ip, timeout=DEFAULT_TIMEOUTS.ssdp, *, context=None):
        """Envia probe SSDP (UDP 1900) para descobrir TVs, Roteadores, NAS e APs."""
        context = operation_context(timeout, context, factor=1)
        try:
            msg = (
                b'M-SEARCH * HTTP/1.1\r\n'
                b'HOST: 239.255.255.250:1900\r\n'
                b'MAN: "ssdp:discover"\r\n'
                b'MX: 1\r\n'
                b'ST: ssdp:all\r\n\r\n'
            )
            data = NetworkResolver._udp_exchange(ip, 1900, msg, timeout, context=context)
            txt = data.decode('utf-8', errors='ignore')

            m_srv = re.search(r'SERVER:\s*([^\r\n]+)', txt, re.IGNORECASE)
            if m_srv:
                srv = m_srv.group(1).strip()
                if "tizen" in srv.lower():
                    return "Samsung Smart TV (Tizen)"
                elif "webos" in srv.lower():
                    return "LG Smart TV (webOS)"
                elif "roku" in srv.lower():
                    return "Roku TV / Streaming Device"
                elif len(srv) > 3 and not srv.lower().startswith("upnp/"):
                    return srv
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_onvif_ws_discovery(ip, timeout=DEFAULT_TIMEOUTS.onvif, *, context=None):
        """Unicast WS-Discovery with explicit SOAP, WS-A and discovery namespaces."""
        context = operation_context(timeout, context, factor=1)
        probe = (
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
            'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
            'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
            f'<s:Header><a:MessageID>urn:uuid:{uuid4()}</a:MessageID>'
            '<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>'
            '<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>'
            '</s:Header><s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types>'
            '</d:Probe></s:Body></s:Envelope>'
        ).encode("utf-8")
        try:
            data = NetworkResolver._udp_exchange(ip, 3702, probe, timeout, context=context)
            root = ET.fromstring(data)
            scopes = " ".join(node.text or "" for node in root.iter()
                              if node.tag == "{http://schemas.xmlsoap.org/ws/2005/04/discovery}Scopes")
            model = re.search(r"onvif://www\.onvif\.org/hardware/(\S+)", scopes)
            name = re.search(r"onvif://www\.onvif\.org/name/(\S+)", scopes)
            values = [unquote(match.group(1)) for match in (name, model) if match]
            if values:
                return "Câmera ONVIF: " + " · ".join(values)
        except (OSError, ET.ParseError):
            context.check()
            logger.debug("ONVIF sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def query_sip_voip(ip, timeout=DEFAULT_TIMEOUTS.sip, *, context=None):
        """Envia ping SIP OPTIONS (UDP 5060) para identificar telefones IP e centrais PABX."""
        context = operation_context(timeout, context, factor=1)
        try:
            sip_msg = (
                f'OPTIONS sip:{ip} SIP/2.0\r\n'
                f'Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-scanner\r\n'
                f'Max-Forwards: 70\r\n'
                f'From: <sip:scanner@127.0.0.1>;tag=scan101\r\n'
                f'To: <sip:{ip}>\r\n'
                f'Call-ID: scan-call-{ip}@127.0.0.1\r\n'
                f'CSeq: 1 OPTIONS\r\n'
                f'Contact: <sip:scanner@127.0.0.1>\r\n'
                f'Accept: application/sdp\r\n'
                f'Content-Length: 0\r\n\r\n'
            ).encode('utf-8')
            data = NetworkResolver._udp_exchange(ip, 5060, sip_msg, timeout, context=context)
            txt = data.decode('utf-8', errors='ignore')

            m_ua = re.search(r'User-Agent:\s*([^\r\n]+)', txt, re.IGNORECASE)
            m_srv = re.search(r'Server:\s*([^\r\n]+)', txt, re.IGNORECASE)
            if m_ua:
                return m_ua.group(1).strip()
            elif m_srv:
                return m_srv.group(1).strip()
        except (OSError, ValueError):
            context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None

    @staticmethod
    def scan_ports(ip, timeout=DEFAULT_TIMEOUTS.tcp, cancel_event=None, *, ports=None, context=None):
        """Testa o mesmo perfil de portas com concorrência e sockets limitados."""
        return scan_tcp_ports(ip, ports=ports, timeout=timeout, cancel_event=cancel_event, context=context)

    @staticmethod
    def obter_mac_e_presenca_windows(ip, *, context=None):
        """Consulta SendARP; a API não oferece timeout nem cancelamento da chamada."""
        if context is not None:
            context.check()
        if os.name != "nt":
            return None, False
        try:
            ip_bytes = socket.inet_aton(ip)
            dest_ip_c = ctypes.c_ulong(struct.unpack('<I', ip_bytes)[0])
            mac_addr = (ctypes.c_byte * 6)()
            mac_len = ctypes.c_ulong(6)
            res = ctypes.windll.iphlpapi.SendARP(dest_ip_c, 0, ctypes.byref(mac_addr), ctypes.byref(mac_len))
            if res == 0:
                mac_str = ":".join(f"{(b & 0xFF):02X}" for b in mac_addr)
                return mac_str, True
        except (OSError, ValueError):
            if context is not None:
                context.check()
            logger.debug("Sonda sem resposta válida: %s", ip, exc_info=True)
        return None, False

    @staticmethod
    def carregar_arp_cache():
        """Lê o cache ARP do Windows antecipadamente sem abrir janelas de console."""
        tabela_arp = {}
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            proc = subprocess.Popen(
                ["arp", "-a"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=0x08000000,
                startupinfo=si
            )
            saida, _ = proc.communicate(timeout=3)
            linhas = saida.splitlines()
            for l in linhas:
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]{17})', l)
                if m:
                    ip_achado = m.group(1)
                    mac_achado = m.group(2).upper().replace("-", ":")
                    tabela_arp[ip_achado] = mac_achado
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            logger.debug("Timeout ao ler cache ARP")
        except OSError:
            logger.debug("Cache ARP indisponível", exc_info=True)
        return tabela_arp

    @staticmethod
    def ping_measurement(ip, timeout=DEFAULT_TIMEOUTS.icmp, *, context=None):
        """Return presence and the RTT reported by ping, never process startup time."""
        context = context if context is not None else ProbeContext.standalone(timeout + 1)
        if os.name == "nt":
            try:
                return ping_ipv4(ip, timeout_ms=max(1, min(30000, math.ceil(context.timeout(timeout) * 1000))))
            except OSError:
                logger.debug("ICMP nativo indisponível; usando ping CLI", exc_info=True)
        return NetworkResolver.ping_measurement_cli(ip, timeout=timeout, context=context)

    @staticmethod
    def ping_measurement_cli(ip, timeout=DEFAULT_TIMEOUTS.icmp, *, context=None):
        """Bounded compatibility fallback for unavailable native ICMP APIs."""
        context = context if context is not None else ProbeContext.standalone(timeout + 1)
        millis = max(1, math.ceil(context.timeout(timeout) * 1000))
        command = ["ping", "-n", "1", "-w", str(millis), ip] if os.name == "nt" else ["ping", "-c", "1", "-W", "1", ip]
        try:
            result = subprocess.run(command, capture_output=True, timeout=context.timeout(timeout + 1),
                                    creationflags=0x08000000 if os.name == "nt" else 0)
            text = result.stdout.decode("latin1", errors="replace")
            active = result.returncode == 0 and "ttl=" in text.lower()
            match = re.search(r"(?:time|tempo)\s*([=<])\s*(\d+(?:[.,]\d+)?)\s*ms", text, re.I)
            latency = None
            if active and match:
                latency = (f"< {match.group(2)} ms" if match.group(1) == "<"
                           else float(match.group(2).replace(",", ".")))
            return active, latency
        except (OSError, subprocess.TimeoutExpired):
            context.check()
            logger.debug("Ping indisponível: %s", ip, exc_info=True)
            return False, None

    @staticmethod
    def ping_silencioso(ip):
        return NetworkResolver.ping_measurement(ip)[0]
