"""连接测试页面 - 包含DNS查询、DNS优选、站点测试、Telnet端口、MTU测试、SSL检查等功能

本页面所有耗时网络操作均通过 QThread 后台线程执行，避免阻塞 UI 主线程。
页面切换时会调用 cleanup()/stop_all() 终止所有后台线程并断开信号连接，
防止访问已删除的 C++ 对象导致程序闪退。
"""
import socket
import subprocess
import platform
import ssl
import datetime
import time
import random
import string
import psutil
from threading import Event
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTextEdit, QStackedWidget,
    QSpinBox, QComboBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal

from app.core.logger import Logger

logger = Logger("ConnectionTest")


# ---------------------------------------------------------------------------
# 公共 DNS 服务器列表（完整列表，与 DNS 优选图片对应）
# ---------------------------------------------------------------------------
COMMON_DNS_SERVERS = [
    ("自动（系统默认）", ""),
    ("阿里云 DNS", "223.5.5.5"),
    ("阿里云 DNS 备用", "223.6.6.6"),
    ("腾讯云 DNS", "119.29.29.29"),
    ("114 DNS", "114.114.114.114"),
    ("Google DNS", "8.8.8.8"),
    ("Cloudflare DNS", "1.1.1.1"),
    ("百度 DNS", "180.76.76.76"),
    ("运营商自动", "DHCP"),
]

DNS_SERVERS_FULL = [
    ("阿里DNS(主)", "223.5.5.5"),
    ("百度DNS", "180.76.76.76"),
    ("阿里DNS(备)", "223.6.6.6"),
    ("上海联通DNS", "210.22.70.3"),
    ("腾讯DNS(主)", "119.29.29.29"),
    ("CNNIC DNS", "1.2.4.8"),
    ("OneDNS(备)", "117.50.22.22"),
    ("OneDNS(主)", "117.50.11.11"),
    ("114DNS(备)", "114.114.115.115"),
    ("114DNS(主)", "114.114.114.114"),
    ("上海电信DNS", "202.96.209.133"),
    ("Google DNS(主)", "8.8.8.8"),
    ("Cloudflare(主)", "1.1.1.1"),
    ("OpenDNS(主)", "208.67.222.222"),
    ("OpenDNS(备)", "208.67.220.220"),
    ("Google DNS(备)", "8.8.4.4"),
    ("Quad9", "9.9.9.9"),
    ("Level3 DNS", "4.2.2.1"),
    ("Cloudflare(备)", "1.0.0.1"),
]


# ---------------------------------------------------------------------------
# 网络操作函数（尽量保持无状态，便于在线程中调用）
# ---------------------------------------------------------------------------
def dns_lookup(domain, dns_server=None, record_type='A'):
    """DNS查询，优先使用 dnspython，未安装时回退到系统 socket。"""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        if dns_server:
            resolver.nameservers = [dns_server]
        answers = resolver.resolve(domain, record_type)
        results = [str(rdata) for rdata in answers]
        return {'success': True, 'records': results, 'server': dns_server or '系统默认'}
    except ImportError:
        try:
            if record_type == 'A':
                ip = socket.gethostbyname(domain)
                return {'success': True, 'records': [ip], 'server': '系统默认'}
            return {'success': False, 'error': f'未安装 dnspython，无法查询 {record_type} 记录'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def test_single_dns(domain, server, timeout=2):
    """测试单个 DNS 服务器一次，返回 (elapsed_ms, ip) 或 None。"""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [server]
        resolver.timeout = timeout
        resolver.lifetime = timeout
        start = time.time()
        answers = resolver.resolve(domain, 'A')
        elapsed = (time.time() - start) * 1000
        return elapsed, str(answers[0])
    except Exception:
        return None


def http_test(url, timeout=5):
    """HTTP 站点测试，返回状态码、耗时和页面大小。"""
    try:
        import requests
        start = time.time()
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        elapsed = (time.time() - start) * 1000
        return {
            'success': True,
            'status': resp.status_code,
            'time': f"{elapsed:.1f}ms",
            'size': len(resp.content),
            'title': 'N/A',
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def telnet_test(host, port, timeout=3):
    """Telnet 端口连通性测试。"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.time()
        result = sock.connect_ex((host, int(port)))
        elapsed = (time.time() - start) * 1000
        if result == 0:
            return {'success': True, 'time': f"{elapsed:.1f}ms"}
        return {'success': False, 'error': f"连接失败 (错误码: {result})"}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        if sock:
            sock.close()


def mtu_test_detailed(host):
    """MTU 详细测试，返回每个测试点的可达性结果。"""
    test_sizes = [1500, 1472, 1400, 1300, 1200, 1000, 576]
    results = []
    max_mtu = None
    try:
        for size in test_sizes:
            if platform.system() == 'Windows':
                cmd = ['ping', '-f', '-l', str(size - 28), '-n', '1', '-w', '2000', host]
                result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
                out = result.stdout or ''
                success = ('需要拆分数据包但是 DF 置位' not in out and
                           'Packet needs to be fragmented' not in out)
            else:
                cmd = ['ping', '-M', 'do', '-s', str(size - 28), '-c', '1', '-W', '2', host]
                result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
                success = result.returncode == 0

            results.append({'mtu': size, 'success': success})
            if success and max_mtu is None:
                max_mtu = size  # 从大到小测试，第一个可达即为最大

        return {'success': True, 'results': results, 'max_mtu': max_mtu}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def ssl_check(host, port=443, timeout=5):
    """SSL 证书检查，返回 TLS 版本、证书过期时间等信息。"""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                version = ssock.version()

                output = [
                    "✅ SSL证书检查成功",
                    f"TLS版本: {version}",
                    f"加密套件: {cipher[0] if cipher else 'N/A'}",
                    f"证书域名: {cert.get('subject', 'N/A')}",
                    f"颁发者: {cert.get('issuer', 'N/A')}",
                ]

                not_after = cert.get('notAfter')
                if not_after:
                    expire = datetime.datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                    days = (expire - datetime.datetime.utcnow()).days
                    output.append(f"过期时间: {not_after}")
                    output.append(f"剩余天数: {days} 天")

                return {'success': True, 'output': "\n".join(output)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def ssl_check_enhanced(host, port=443, timeout=10):
    """SSL证书检查增强版，返回详细的证书信息。"""
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                version = ssock.version()

                result = {
                    'success': True,
                    'tls_version': version,
                    'cipher': cipher[0] if cipher else 'N/A',
                    'cipher_bits': cipher[2] if cipher else 'N/A',
                }

                subject = dict(x[0] for x in cert.get('subject', []))
                issuer = dict(x[0] for x in cert.get('issuer', []))
                result['subject'] = subject.get('commonName', 'N/A')
                result['issuer'] = issuer.get('commonName', 'N/A')
                result['issuer_country'] = issuer.get('countryName', 'N/A')
                result['issuer_org'] = issuer.get('organizationName', 'N/A')

                not_before = cert.get('notBefore')
                not_after = cert.get('notAfter')
                if not_before:
                    result['valid_from'] = not_before
                if not_after:
                    try:
                        expire = datetime.datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                        days_left = (expire - datetime.datetime.utcnow()).days
                        result['valid_to'] = not_after
                        result['days_left'] = days_left
                    except Exception:
                        result['valid_to'] = not_after
                        result['days_left'] = '未知'

                sans = cert.get('subjectAltName', [])
                result['alt_names'] = [name for _, name in sans]

                return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


def generate_password(length=16, include_upper=True, include_lower=True, 
                      include_digits=True, include_special=True):
    """生成随机密码。"""
    chars = ''
    if include_upper:
        chars += string.ascii_uppercase
    if include_lower:
        chars += string.ascii_lowercase
    if include_digits:
        chars += string.digits
    if include_special:
        chars += '!@#$%^&*()_+-=[]{}|;:,.<>?'

    if not chars:
        return {'success': False, 'error': '至少选择一种字符类型'}

    password = ''.join(random.choice(chars) for _ in range(length))
    strength = _calculate_password_strength(password)
    
    return {'success': True, 'password': password, 'strength': strength}


def _calculate_password_strength(password):
    """计算密码强度。"""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if len(password) >= 16:
        score += 1
    if any(c.isupper() for c in password):
        score += 1
    if any(c.islower() for c in password):
        score += 1
    if any(c.isdigit() for c in password):
        score += 1
    if any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        score += 1

    if score <= 2:
        return ('弱', '#e74c3c')
    elif score <= 4:
        return ('中', '#f39c12')
    elif score <= 6:
        return ('强', '#3498db')
    else:
        return ('极强', '#2ecc71')


def get_network_connections():
    """获取网络连接统计信息。"""
    try:
        connections = []
        for conn in psutil.net_connections(kind='inet'):
            connections.append({
                'type': 'TCP' if conn.type == socket.SOCK_STREAM else 'UDP',
                'laddr': f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else '',
                'raddr': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else '',
                'status': conn.status,
                'pid': conn.pid,
            })

        tcp_count = sum(1 for c in connections if c['type'] == 'TCP')
        udp_count = sum(1 for c in connections if c['type'] == 'UDP')
        
        tcp_states = {}
        for c in connections:
            if c['type'] == 'TCP':
                tcp_states[c['status']] = tcp_states.get(c['status'], 0) + 1

        remote_ips = {}
        for c in connections:
            if c['raddr']:
                remote_ips[c['raddr'].split(':')[0]] = remote_ips.get(c['raddr'].split(':')[0], 0) + 1

        top_ips = sorted(remote_ips.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            'success': True,
            'total': len(connections),
            'tcp_count': tcp_count,
            'udp_count': udp_count,
            'tcp_states': tcp_states,
            'top_ips': top_ips,
            'connections': connections,
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_port_processes():
    """获取端口占用信息，包含进程名。"""
    try:
        results = []
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr and conn.pid:
                try:
                    process = psutil.Process(conn.pid)
                    results.append({
                        'protocol': 'TCP' if conn.type == socket.SOCK_STREAM else 'UDP',
                        'local_ip': conn.laddr.ip,
                        'local_port': conn.laddr.port,
                        'remote_ip': conn.raddr.ip if conn.raddr else '',
                        'remote_port': conn.raddr.port if conn.raddr else '',
                        'status': conn.status,
                        'pid': conn.pid,
                        'process_name': process.name(),
                        'process_path': process.exe(),
                    })
                except Exception:
                    results.append({
                        'protocol': 'TCP' if conn.type == socket.SOCK_STREAM else 'UDP',
                        'local_ip': conn.laddr.ip,
                        'local_port': conn.laddr.port,
                        'remote_ip': conn.raddr.ip if conn.raddr else '',
                        'remote_port': conn.raddr.port if conn.raddr else '',
                        'status': conn.status,
                        'pid': conn.pid,
                        'process_name': '未知',
                        'process_path': '',
                    })

        return {'success': True, 'data': results}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# 后台线程类
# ---------------------------------------------------------------------------
class DNSQueryThread(QThread):
    """DNS 查询后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, domain, dns_server, record_type):
        super().__init__()
        self.domain = domain
        self.dns_server = dns_server
        self.record_type = record_type

    def run(self):
        result = dns_lookup(self.domain, self.dns_server, self.record_type)
        self.result_signal.emit(result)


class DNSSelectThread(QThread):
    """DNS 优选后台线程，支持多次测试和停止。"""
    progress_signal = Signal(str, int)  # (状态文本, 当前进度索引)
    result_signal = Signal(list)
    finished_signal = Signal()

    def __init__(self, domain, test_count, stop_event):
        super().__init__()
        self.domain = domain
        self.test_count = test_count
        self.stop_event = stop_event

    def run(self):
        results = []
        total = len(DNS_SERVERS_FULL)
        for idx, (name, server) in enumerate(DNS_SERVERS_FULL):
            if self.stop_event.is_set():
                break

            self.progress_signal.emit(f"正在测试 {name} ({server})...", idx)

            times = []
            success_count = 0
            ip_result = '-'

            for _ in range(self.test_count):
                if self.stop_event.is_set():
                    break
                r = test_single_dns(self.domain, server)
                if r is not None:
                    elapsed, ip = r
                    times.append(elapsed)
                    success_count += 1
                    ip_result = ip

            avg_time = sum(times) / len(times) if times else 99999
            results.append({
                'name': name,
                'server': server,
                'avg_time': avg_time,
                'success_rate': f"{success_count}/{self.test_count}",
                'ip': ip_result if success_count > 0 else '-',
                'success': success_count > 0,
                'partial': 0 < success_count < self.test_count,
            })

        # 按平均延迟排序（成功的排前面）
        results.sort(key=lambda x: (not x['success'], x['avg_time']))
        self.result_signal.emit(results)
        self.finished_signal.emit()


class SiteTestThread(QThread):
    """站点测试后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        result = http_test(self.url)
        self.result_signal.emit(result)


class TelnetTestThread(QThread):
    """Telnet 端口测试后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, host, port, timeout):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self):
        result = telnet_test(self.host, self.port, self.timeout)
        self.result_signal.emit(result)


class MTUTestThread(QThread):
    """MTU 测试后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, host):
        super().__init__()
        self.host = host

    def run(self):
        result = mtu_test_detailed(self.host)
        self.result_signal.emit(result)


class SSLCheckThread(QThread):
    """SSL 证书检查后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        result = ssl_check(self.host, self.port)
        self.result_signal.emit(result)


class SSLEnhancedThread(QThread):
    """SSL证书检查增强版后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        result = ssl_check_enhanced(self.host, self.port)
        self.result_signal.emit(result)


class PasswordGenThread(QThread):
    """密码生成后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, length, include_upper, include_lower, include_digits, include_special):
        super().__init__()
        self.length = length
        self.include_upper = include_upper
        self.include_lower = include_lower
        self.include_digits = include_digits
        self.include_special = include_special

    def run(self):
        result = generate_password(
            self.length, self.include_upper, self.include_lower,
            self.include_digits, self.include_special
        )
        self.result_signal.emit(result)


class NSLookupThread(QThread):
    """NSLookup 查询后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, domain, dns_server, record_type):
        super().__init__()
        self.domain = domain
        self.dns_server = dns_server
        self.record_type = record_type

    def run(self):
        result = dns_lookup(self.domain, self.dns_server, self.record_type)
        self.result_signal.emit(result)


class ConnectionStatsThread(QThread):
    """连接统计后台线程。"""
    result_signal = Signal(dict)

    def __init__(self):
        super().__init__()

    def run(self):
        result = get_network_connections()
        self.result_signal.emit(result)


class PortProcessThread(QThread):
    """端口进程后台线程。"""
    result_signal = Signal(dict)

    def __init__(self, filter_port=None):
        super().__init__()
        self.filter_port = filter_port

    def run(self):
        result = get_port_processes()
        if self.filter_port and result['success']:
            result['data'] = [
                item for item in result['data']
                if str(item['local_port']) == str(self.filter_port)
            ]
        self.result_signal.emit(result)


# ---------------------------------------------------------------------------
# 主页面
# ---------------------------------------------------------------------------
class ConnectionTestPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.threads = []
        self.dns_stop_event = Event()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 顶部 Tab 导航
        self.tab_frame = QFrame()
        self.tab_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        tab_layout = QHBoxLayout(self.tab_frame)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        self.tab_buttons = {}
        tabs = [
            ("DNS查询", "dns_query"),
            ("DNS优选", "dns_select"),
            ("站点测试", "site_test"),
            ("Telnet端口", "telnet"),
            ("MTU测试", "mtu"),
            ("SSL检查", "ssl"),
            ("SSL增强版", "ssl_enhanced"),
            ("密码生成", "password_gen"),
            ("NSLookup", "nslookup"),
            ("连接统计", "connection_stats"),
            ("端口进程", "port_process"),
        ]
        for name, key in tabs:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #555;
                    border: none;
                    padding: 12px 18px;
                    font-size: 12px;
                    border-bottom: 2px solid transparent;
                }
                QPushButton:checked {
                    background-color: #e3f2fd;
                    color: #00bcd4;
                    border-bottom: 2px solid #00bcd4;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #f5f5f5; }
            """)
            btn.clicked.connect(lambda checked, k=key: self.switch_tab(k))
            tab_layout.addWidget(btn)
            self.tab_buttons[key] = btn
        tab_layout.addStretch()
        main_layout.addWidget(self.tab_frame)

        # 内容区域
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        self.stack.addWidget(self._build_dns_query_page())
        self.stack.addWidget(self._build_dns_select_page())
        self.stack.addWidget(self._build_site_test_page())
        self.stack.addWidget(self._build_telnet_page())
        self.stack.addWidget(self._build_mtu_page())
        self.stack.addWidget(self._build_ssl_page())
        self.stack.addWidget(self._build_ssl_enhanced_page())
        self.stack.addWidget(self._build_password_gen_page())
        self.stack.addWidget(self._build_nslookup_page())
        self.stack.addWidget(self._build_connection_stats_page())
        self.stack.addWidget(self._build_port_process_page())

        self.switch_tab("dns_query")

    # -----------------------------------------------------------------------
    # Tab 切换
    # -----------------------------------------------------------------------
    def switch_tab(self, key):
        for k, btn in self.tab_buttons.items():
            btn.setChecked(k == key)
        index_map = {
            "dns_query": 0, "dns_select": 1, "site_test": 2,
            "telnet": 3, "mtu": 4, "ssl": 5,
            "ssl_enhanced": 6, "password_gen": 7, "nslookup": 8,
            "connection_stats": 9, "port_process": 10
        }
        self.stack.setCurrentIndex(index_map[key])

    # -----------------------------------------------------------------------
    # 通用结果框样式
    # -----------------------------------------------------------------------
    def _make_result_text(self, parent):
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("""
            QTextEdit {
                background-color: white; color: #333;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px; line-height: 1.6;
                border: 1px solid #f0f0f0; border-radius: 3px;
                padding: 10px;
            }
        """)
        return text

    def _make_input_frame(self, title_text):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        title = QLabel(title_text)
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        layout.addWidget(title)
        return frame, layout

    # -----------------------------------------------------------------------
    # DNS 查询 Tab
    # -----------------------------------------------------------------------
    def _build_dns_query_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🔍 DNS查询")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("域名:"))
        self.dns_domain_input = QLineEdit("baidu.com")
        self.dns_domain_input.setMinimumWidth(300)
        row.addWidget(self.dns_domain_input)

        row.addWidget(QLabel("DNS服务器:"))
        self.dns_server_combo = QComboBox()
        self.dns_server_combo.setMinimumWidth(180)
        for name, server in COMMON_DNS_SERVERS:
            self.dns_server_combo.addItem(name, server)
        row.addWidget(self.dns_server_combo)

        row.addWidget(QLabel("记录类型:"))
        self.dns_type_combo = QComboBox()
        self.dns_type_combo.addItems(["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"])
        row.addWidget(self.dns_type_combo)

        query_btn = QPushButton("🔍 查询")
        query_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        query_btn.clicked.connect(self.do_dns_query)
        row.addWidget(query_btn)

        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 查询结果")
        self.dns_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.dns_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # DNS 优选 Tab（按图片样式：表格、多次测试、排序、最优推荐）
    # -----------------------------------------------------------------------
    def _build_dns_select_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🌐 DNS优选")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("测试域名:"))
        self.dns_select_input = QLineEdit("baidu.com")
        row.addWidget(self.dns_select_input)

        row.addWidget(QLabel("测试次数:"))
        self.dns_test_count_combo = QComboBox()
        for i in range(1, 6):
            self.dns_test_count_combo.addItem(str(i), i)
        self.dns_test_count_combo.setCurrentIndex(2)  # 默认 3
        row.addWidget(self.dns_test_count_combo)

        self.dns_select_start_btn = QPushButton("🚀 开始优选")
        self.dns_select_start_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        self.dns_select_start_btn.clicked.connect(self.do_dns_select)
        row.addWidget(self.dns_select_start_btn)

        self.dns_select_stop_btn = QPushButton("⏹ 停止")
        self.dns_select_stop_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        self.dns_select_stop_btn.clicked.connect(self.stop_dns_select)
        self.dns_select_stop_btn.setEnabled(False)
        row.addWidget(self.dns_select_stop_btn)

        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        # 结果表格
        result_frame = QFrame()
        result_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(10, 10, 10, 10)
        result_layout.setSpacing(8)

        table_title = QLabel("📋 测试结果（按延迟排序）")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(table_title)

        self.dns_select_table = QTableWidget()
        self.dns_select_table.setColumnCount(7)
        self.dns_select_table.setHorizontalHeaderLabels(
            ["排名", "提供商", "DNS地址", "平均延迟", "成功率", "解析结果", "状态"]
        )
        self.dns_select_table.setAlternatingRowColors(True)
        self.dns_select_table.setStyleSheet("""
            QTableWidget { font-size: 12px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 6px; font-weight: bold; }
            QTableWidget::item { padding: 4px; }
        """)
        header = self.dns_select_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.dns_select_table.verticalHeader().setVisible(False)
        result_layout.addWidget(self.dns_select_table)

        # 进度条
        self.dns_select_progress = QProgressBar()
        self.dns_select_progress.setRange(0, len(DNS_SERVERS_FULL))
        self.dns_select_progress.setValue(0)
        self.dns_select_progress.setTextVisible(True)
        result_layout.addWidget(self.dns_select_progress)

        # 最优推荐
        self.dns_recommend_label = QLabel("")
        self.dns_recommend_label.setStyleSheet("""
            QLabel {
                color: #27ae60; font-weight: bold; font-size: 12px;
                background-color: #e8f8f5; padding: 8px 12px; border-radius: 3px;
            }
        """)
        self.dns_recommend_label.setVisible(False)
        result_layout.addWidget(self.dns_recommend_label)

        layout.addWidget(result_frame, 1)
        return page

    # -----------------------------------------------------------------------
    # 站点测试 Tab
    # -----------------------------------------------------------------------
    def _build_site_test_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🌐 站点测试")

        row = QHBoxLayout()
        row.addWidget(QLabel("URL:"))
        self.site_url_input = QLineEdit("https://www.baidu.com")
        row.addWidget(self.site_url_input)

        test_btn = QPushButton("🚀 测试")
        test_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        test_btn.clicked.connect(self.do_site_test)
        row.addWidget(test_btn)
        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 测试结果")
        self.site_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.site_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # Telnet 端口 Tab（按图片样式：目标主机占宽、端口、超时、开始测试）
    # -----------------------------------------------------------------------
    def _build_telnet_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🔌 Telnet端口测试")

        row = QHBoxLayout()
        row.setSpacing(10)

        row.addWidget(QLabel("目标主机:"))
        self.telnet_host_input = QLineEdit("127.0.0.1")
        row.addWidget(self.telnet_host_input, 1)

        row.addWidget(QLabel("端口:"))
        self.telnet_port_input = QSpinBox()
        self.telnet_port_input.setRange(1, 65535)
        self.telnet_port_input.setValue(23)
        self.telnet_port_input.setFixedWidth(70)
        row.addWidget(self.telnet_port_input)

        row.addWidget(QLabel("超时(秒):"))
        self.telnet_timeout_input = QSpinBox()
        self.telnet_timeout_input.setRange(1, 30)
        self.telnet_timeout_input.setValue(3)
        self.telnet_timeout_input.setFixedWidth(70)
        row.addWidget(self.telnet_timeout_input)

        test_btn = QPushButton("🚀 开始测试")
        test_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        test_btn.clicked.connect(self.do_telnet_test)
        row.addWidget(test_btn)

        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 Telnet测试结果")
        self.telnet_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.telnet_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # MTU 测试 Tab（输出格式按图片详细展示）
    # -----------------------------------------------------------------------
    def _build_mtu_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("📦 MTU测试")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("目标主机:"))
        self.mtu_host_input = QLineEdit("8.8.8.8")
        row.addWidget(self.mtu_host_input, 1)

        test_btn = QPushButton("🚀 开始测试")
        test_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        test_btn.clicked.connect(self.do_mtu_test)
        row.addWidget(test_btn)
        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 测试结果")
        self.mtu_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.mtu_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # SSL 检查 Tab
    # -----------------------------------------------------------------------
    def _build_ssl_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🔒 SSL检查")

        row = QHBoxLayout()
        row.addWidget(QLabel("域名:"))
        self.ssl_host_input = QLineEdit("baidu.com")
        row.addWidget(self.ssl_host_input)

        row.addWidget(QLabel("端口:"))
        self.ssl_port_input = QSpinBox()
        self.ssl_port_input.setRange(1, 65535)
        self.ssl_port_input.setValue(443)
        row.addWidget(self.ssl_port_input)

        test_btn = QPushButton("🚀 检查")
        test_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        test_btn.clicked.connect(self.do_ssl_check)
        row.addWidget(test_btn)
        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 检查结果")
        self.ssl_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.ssl_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # SSL检查增强版 Tab
    # -----------------------------------------------------------------------
    def _build_ssl_enhanced_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🔐 SSL检查（增强版）")

        row = QHBoxLayout()
        row.addWidget(QLabel("域名:"))
        self.ssl_enhanced_host_input = QLineEdit("baidu.com")
        row.addWidget(self.ssl_enhanced_host_input)

        row.addWidget(QLabel("端口:"))
        self.ssl_enhanced_port_input = QSpinBox()
        self.ssl_enhanced_port_input.setRange(1, 65535)
        self.ssl_enhanced_port_input.setValue(443)
        self.ssl_enhanced_port_input.setFixedWidth(100)
        row.addWidget(self.ssl_enhanced_port_input)

        test_btn = QPushButton("🚀 检查")
        test_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        test_btn.clicked.connect(self.do_ssl_enhanced_check)
        row.addWidget(test_btn)
        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 证书详情")
        self.ssl_enhanced_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.ssl_enhanced_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # 密码生成 Tab
    # -----------------------------------------------------------------------
    def _build_password_gen_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        # 紧凑的输入配置区域
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        input_layout = QGridLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)
        input_layout.setColumnStretch(1, 1)

        # 第一行：标题 + 密码长度
        title = QLabel("🔑 密码生成")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        input_layout.addWidget(title, 0, 0)

        length_layout = QHBoxLayout()
        length_layout.setSpacing(6)
        length_layout.addWidget(QLabel("长度:"))
        self.password_length_input = QSpinBox()
        self.password_length_input.setRange(6, 64)
        self.password_length_input.setValue(16)
        self.password_length_input.setFixedWidth(75)
        length_layout.addWidget(self.password_length_input)
        length_layout.addStretch()
        input_layout.addLayout(length_layout, 0, 1)

        # 第二行：字符类型按钮
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        btn_style = """
            QPushButton { background-color: #f0f0f0; color: #333; border: 1px solid #ddd; padding: 4px 8px; border-radius: 3px; }
            QPushButton:checked { background-color: #e3f2fd; color: #1976d2; border-color: #1976d2; }
        """
        self.password_upper_check = QPushButton("大写字母 (A-Z)")
        self.password_upper_check.setCheckable(True)
        self.password_upper_check.setChecked(True)
        self.password_upper_check.setFixedWidth(120)
        self.password_upper_check.setStyleSheet(btn_style)
        row2.addWidget(self.password_upper_check)

        self.password_lower_check = QPushButton("小写字母 (a-z)")
        self.password_lower_check.setCheckable(True)
        self.password_lower_check.setChecked(True)
        self.password_lower_check.setFixedWidth(120)
        self.password_lower_check.setStyleSheet(btn_style)
        row2.addWidget(self.password_lower_check)

        self.password_digit_check = QPushButton("数字 (0-9)")
        self.password_digit_check.setCheckable(True)
        self.password_digit_check.setChecked(True)
        self.password_digit_check.setFixedWidth(120)
        self.password_digit_check.setStyleSheet(btn_style)
        row2.addWidget(self.password_digit_check)

        self.password_special_check = QPushButton("特殊字符")
        self.password_special_check.setCheckable(True)
        self.password_special_check.setChecked(True)
        self.password_special_check.setFixedWidth(120)
        self.password_special_check.setStyleSheet(btn_style)
        row2.addWidget(self.password_special_check)
        row2.addStretch()
        input_layout.addLayout(row2, 1, 0, 1, 2)

        # 第三行：生成/复制按钮
        row3 = QHBoxLayout()
        row3.setSpacing(10)
        generate_btn = QPushButton("🚀 生成密码")
        generate_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 6px 16px; border-radius: 3px;")
        generate_btn.clicked.connect(self.do_generate_password)
        row3.addWidget(generate_btn)

        copy_btn = QPushButton("📋 复制密码")
        copy_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 6px 16px; border-radius: 3px;")
        copy_btn.clicked.connect(self.do_copy_password)
        row3.addWidget(copy_btn)
        row3.addStretch()
        input_layout.addLayout(row3, 2, 0, 1, 2)

        layout.addWidget(input_frame)

        # 结果区域
        result_frame = QFrame()
        result_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(12, 10, 12, 10)
        result_layout.setSpacing(8)

        result_title = QLabel("📋 生成结果")
        result_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        result_layout.addWidget(result_title)

        self.password_result_input = QLineEdit()
        self.password_result_input.setReadOnly(True)
        self.password_result_input.setStyleSheet("""
            QLineEdit { font-size: 14px; padding: 8px; border: 2px solid #e0e0e0; border-radius: 5px; font-family: Consolas; letter-spacing: 2px; }
        """)
        result_layout.addWidget(self.password_result_input)

        strength_row = QHBoxLayout()
        strength_row.addWidget(QLabel("密码强度:"))
        self.password_strength_label = QLabel("")
        self.password_strength_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        strength_row.addWidget(self.password_strength_label)
        strength_row.addStretch()
        result_layout.addLayout(strength_row)

        layout.addWidget(result_frame)
        layout.addStretch()

        return page

    # -----------------------------------------------------------------------
    # NSLookup Tab
    # -----------------------------------------------------------------------
    def _build_nslookup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🔍 NSLookup")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("域名:"))
        self.nslookup_domain_input = QLineEdit("baidu.com")
        row.addWidget(self.nslookup_domain_input)

        row.addWidget(QLabel("查询类型:"))
        self.nslookup_type_combo = QComboBox()
        self.nslookup_type_combo.addItems(["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"])
        row.addWidget(self.nslookup_type_combo)

        row.addWidget(QLabel("DNS服务器:"))
        self.nslookup_server_input = QLineEdit("")
        self.nslookup_server_input.setPlaceholderText("留空使用系统默认")
        row.addWidget(self.nslookup_server_input)

        query_btn = QPushButton("🚀 查询")
        query_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        query_btn.clicked.connect(self.do_nslookup)
        row.addWidget(query_btn)

        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._make_input_frame("📋 查询结果")
        self.nslookup_result = self._make_result_text(result_frame)
        result_layout.addWidget(self.nslookup_result)
        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # 连接统计 Tab
    # -----------------------------------------------------------------------
    def _build_connection_stats_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("📊 连接统计")

        row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 刷新统计")
        refresh_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        refresh_btn.clicked.connect(self.do_connection_stats)
        row.addWidget(refresh_btn)
        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 12, 15, 12)
        stats_layout.setSpacing(10)

        stats_title = QLabel("📈 连接统计信息")
        stats_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        stats_layout.addWidget(stats_title)

        self.connection_stats_result = self._make_result_text(stats_frame)
        stats_layout.addWidget(self.connection_stats_result)

        layout.addWidget(stats_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # 端口进程 Tab
    # -----------------------------------------------------------------------
    def _build_port_process_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._make_input_frame("🔌 端口进程")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("过滤端口:"))
        self.port_process_filter_input = QLineEdit()
        self.port_process_filter_input.setPlaceholderText("留空显示所有")
        row.addWidget(self.port_process_filter_input)

        refresh_btn = QPushButton("🔄 刷新列表")
        refresh_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        refresh_btn.clicked.connect(self.do_port_process)
        row.addWidget(refresh_btn)

        row.addStretch()
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame = QFrame()
        result_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(10, 10, 10, 10)
        result_layout.setSpacing(8)

        table_title = QLabel("📋 端口占用列表")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(table_title)

        self.port_process_table = QTableWidget()
        self.port_process_table.setColumnCount(7)
        self.port_process_table.setHorizontalHeaderLabels(
            ["协议", "本地地址", "远程地址", "状态", "PID", "进程名", "进程路径"]
        )
        self.port_process_table.setAlternatingRowColors(True)
        self.port_process_table.setStyleSheet("""
            QTableWidget { font-size: 12px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 6px; font-weight: bold; }
            QTableWidget::item { padding: 4px; }
        """)
        header = self.port_process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.port_process_table.verticalHeader().setVisible(False)
        result_layout.addWidget(self.port_process_table)

        layout.addWidget(result_frame, 1)

        return page

    # -----------------------------------------------------------------------
    # 后台线程启动与停止辅助
    # -----------------------------------------------------------------------
    def _start_thread(self, thread_class, result_callback, *args):
        """启动后台线程并登记，页面切换时统一清理。"""
        self._cleanup_finished_threads()
        thread = thread_class(*args)
        thread.result_signal.connect(result_callback)
        thread.finished.connect(self._cleanup_finished_threads)
        self.threads.append(thread)
        thread.start()
        return thread

    def _cleanup_finished_threads(self):
        """移除已结束的后台线程引用。"""
        alive = []
        for t in self.threads:
            if t.isRunning():
                alive.append(t)
            else:
                try:
                    t.result_signal.disconnect()
                except Exception:
                    pass
        self.threads = alive

    # -----------------------------------------------------------------------
    # DNS 查询
    # -----------------------------------------------------------------------
    def do_dns_query(self):
        domain = self.dns_domain_input.text().strip()
        if not domain:
            QMessageBox.warning(self, "提示", "请输入域名")
            return

        dns_server = self.dns_server_combo.currentData()
        record_type = self.dns_type_combo.currentText()
        self.dns_result.setPlainText(f"正在查询 {domain} ({record_type})...")

        self._start_thread(
            DNSQueryThread,
            self.on_dns_result,
            domain, dns_server, record_type
        )

    def on_dns_result(self, result):
        if result['success']:
            output = [
                "✅ DNS查询成功",
                f"DNS服务器: {result['server']}",
                f"记录数量: {len(result['records'])}",
                "",
                "解析结果:",
            ]
            for i, record in enumerate(result['records'], 1):
                output.append(f"  {i}. {record}")
            self.dns_result.setPlainText("\n".join(output))
        else:
            self.dns_result.setPlainText(f"❌ DNS查询失败: {result['error']}")

    # -----------------------------------------------------------------------
    # DNS 优选
    # -----------------------------------------------------------------------
    def do_dns_select(self):
        domain = self.dns_select_input.text().strip()
        if not domain:
            QMessageBox.warning(self, "提示", "请输入测试域名")
            return

        test_count = self.dns_test_count_combo.currentData()
        self.dns_stop_event.clear()

        self.dns_select_start_btn.setEnabled(False)
        self.dns_select_stop_btn.setEnabled(True)
        self.dns_recommend_label.setVisible(False)
        self.dns_select_table.setRowCount(0)
        self.dns_select_progress.setValue(0)

        self.dns_select_thread = DNSSelectThread(domain, test_count, self.dns_stop_event)
        self.dns_select_thread.progress_signal.connect(self.on_dns_select_progress)
        self.dns_select_thread.result_signal.connect(self.on_dns_select_result)
        self.dns_select_thread.finished_signal.connect(self.on_dns_select_finished)
        self.threads.append(self.dns_select_thread)
        self.dns_select_thread.start()

    def on_dns_select_progress(self, text, idx):
        self.dns_select_progress.setValue(idx + 1)
        self.dns_select_progress.setFormat(f"{text} ({idx + 1}/{len(DNS_SERVERS_FULL)})")

    def on_dns_select_result(self, results):
        self.dns_select_table.setRowCount(len(results))
        for i, r in enumerate(results):
            # 排名
            rank_item = QTableWidgetItem(str(i + 1))
            rank_item.setTextAlignment(Qt.AlignCenter)
            self.dns_select_table.setItem(i, 0, rank_item)

            self.dns_select_table.setItem(i, 1, QTableWidgetItem(r['name']))
            self.dns_select_table.setItem(i, 2, QTableWidgetItem(r['server']))

            avg_text = f"{r['avg_time']:.1f} ms" if r['success'] else "-"
            self.dns_select_table.setItem(i, 3, QTableWidgetItem(avg_text))

            rate_item = QTableWidgetItem(r['success_rate'])
            rate_item.setTextAlignment(Qt.AlignCenter)
            self.dns_select_table.setItem(i, 4, rate_item)

            self.dns_select_table.setItem(i, 5, QTableWidgetItem(r['ip']))

            if r['partial']:
                status_text = "⚠️ 部分"
            elif r['success']:
                status_text = "✅ 正常"
            else:
                status_text = "❌ 失败"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.dns_select_table.setItem(i, 6, status_item)

        # 最优推荐
        best = next((r for r in results if r['success']), None)
        if best:
            self.dns_recommend_label.setText(
                f"🏆 最优推荐: {best['name']} {best['server']} 平均延迟 {best['avg_time']:.1f} ms — 建议将首选 DNS 设为此地址"
            )
            self.dns_recommend_label.setVisible(True)
        else:
            self.dns_recommend_label.setText("❌ 所有 DNS 服务器均不可用")
            self.dns_recommend_label.setVisible(True)

    def on_dns_select_finished(self):
        self.dns_select_start_btn.setEnabled(True)
        self.dns_select_stop_btn.setEnabled(False)
        self.dns_select_progress.setFormat("测试完成")

    def stop_dns_select(self):
        self.dns_stop_event.set()
        self.dns_select_stop_btn.setEnabled(False)
        self.dns_select_progress.setFormat("正在停止...")

    # -----------------------------------------------------------------------
    # 站点测试
    # -----------------------------------------------------------------------
    def do_site_test(self):
        url = self.site_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入URL")
            return

        self.site_result.setPlainText("正在测试站点...")
        self._start_thread(
            SiteTestThread,
            self.on_site_test_result,
            url
        )

    def on_site_test_result(self, result):
        if result['success']:
            self.site_result.setPlainText(
                f"✅ 站点访问成功\n"
                f"状态码: {result['status']}\n"
                f"响应时间: {result['time']}\n"
                f"页面大小: {result['size']} bytes"
            )
        else:
            self.site_result.setPlainText(f"❌ 站点访问失败: {result['error']}")

    # -----------------------------------------------------------------------
    # Telnet 端口测试
    # -----------------------------------------------------------------------
    def do_telnet_test(self):
        host = self.telnet_host_input.text().strip()
        port = self.telnet_port_input.value()
        timeout = self.telnet_timeout_input.value()
        if not host:
            QMessageBox.warning(self, "提示", "请输入目标主机")
            return

        self.telnet_result.setPlainText(f"正在连接 {host}:{port} (超时 {timeout} 秒)...")
        self._start_thread(
            TelnetTestThread,
            self.on_telnet_test_result,
            host, port, timeout
        )

    def on_telnet_test_result(self, result):
        port = self.telnet_port_input.value()
        host = self.telnet_host_input.text().strip()
        if result['success']:
            self.telnet_result.setPlainText(
                f"✅ 端口 {port} 开放\n"
                f"目标主机: {host}\n"
                f"连接耗时: {result['time']}"
            )
        else:
            self.telnet_result.setPlainText(
                f"❌ 端口 {port} 连接失败\n"
                f"目标主机: {host}\n"
                f"{result['error']}"
            )

    # -----------------------------------------------------------------------
    # MTU 测试（按图片格式输出详细结果）
    # -----------------------------------------------------------------------
    def do_mtu_test(self):
        host = self.mtu_host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "提示", "请输入目标主机")
            return

        self.mtu_result.setPlainText(f"正在测试到 {host} 的MTU...")
        self._start_thread(
            MTUTestThread,
            self.on_mtu_test_result,
            host
        )

    def on_mtu_test_result(self, result):
        host = self.mtu_host_input.text().strip()
        if not result['success']:
            self.mtu_result.setPlainText(f"❌ MTU测试失败: {result['error']}")
            return

        lines = []
        lines.append(f"MTU (最大传输单元) 测试 - {host}")
        lines.append("=" * 50)
        lines.append(f"测试时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("🔍 测试不同MTU大小的可达性:")
        lines.append("")

        for item in result['results']:
            if item['success']:
                lines.append(f"☑ MTU {item['mtu']}: 可达")
            else:
                lines.append(f"☐ MTU {item['mtu']}: 不可达")

        lines.append("")
        max_mtu = result['max_mtu']
        lines.append("📊 测试结果:")
        if max_mtu:
            lines.append(f"最大可达MTU: {max_mtu}")
        else:
            lines.append("最大可达MTU: 无法确定（所有测试点均不可达）")

        lines.append("")
        lines.append("💡 建议:")
        if max_mtu == 1500:
            lines.append("• 网络支持标准MTU (1500字节)")
            lines.append("• 无需调整MTU设置")
        elif max_mtu:
            lines.append(f"• 当前网络最大MTU为 {max_mtu} 字节")
            lines.append("• 如需优化，可将网卡MTU调整为此值")
        else:
            lines.append("• 无法到达目标主机，请检查网络连接")

        lines.append("")
        lines.append("📝 MTU说明:")
        lines.append("• MTU是网络层数据包的最大长度")
        lines.append("• 标准以太网帧为1500字节")
        lines.append("• 过小的MTU会降低网络性能")
        lines.append("• 过大的MTU可能导致分片")

        self.mtu_result.setPlainText("\n".join(lines))

    # -----------------------------------------------------------------------
    # SSL 检查
    # -----------------------------------------------------------------------
    def do_ssl_check(self):
        host = self.ssl_host_input.text().strip()
        port = self.ssl_port_input.value()
        if not host:
            QMessageBox.warning(self, "提示", "请输入域名")
            return

        self.ssl_result.setPlainText(f"正在检查 {host}:{port} 的SSL证书...")
        self._start_thread(
            SSLCheckThread,
            self.on_ssl_check_result,
            host, port
        )

    def on_ssl_check_result(self, result):
        if result['success']:
            self.ssl_result.setPlainText(result['output'])
        else:
            self.ssl_result.setPlainText(f"❌ SSL检查失败: {result['error']}")

    # -----------------------------------------------------------------------
    # SSL检查增强版
    # -----------------------------------------------------------------------
    def do_ssl_enhanced_check(self):
        host = self.ssl_enhanced_host_input.text().strip()
        port = self.ssl_enhanced_port_input.value()
        if not host:
            QMessageBox.warning(self, "提示", "请输入域名")
            return

        self.ssl_enhanced_result.setPlainText(f"正在检查 {host}:{port} 的SSL证书...")
        self._start_thread(
            SSLEnhancedThread,
            self.on_ssl_enhanced_result,
            host, port
        )

    def on_ssl_enhanced_result(self, result):
        if not result['success']:
            self.ssl_enhanced_result.setPlainText(f"❌ SSL检查失败: {result['error']}")
            return

        lines = []
        lines.append("✅ SSL证书检查成功")
        lines.append("=" * 50)
        lines.append(f"TLS版本: {result['tls_version']}")
        lines.append(f"加密套件: {result['cipher']} ({result['cipher_bits']}位)")
        lines.append("")
        lines.append("📋 证书信息:")
        lines.append(f"  域名: {result['subject']}")
        lines.append(f"  颁发者: {result['issuer']}")
        lines.append(f"  颁发机构: {result['issuer_org']} ({result['issuer_country']})")
        lines.append("")
        lines.append("⏱️ 有效期:")
        lines.append(f"  从: {result.get('valid_from', 'N/A')}")
        lines.append(f"  至: {result.get('valid_to', 'N/A')}")
        
        days_left = result.get('days_left')
        if days_left != '未知':
            if days_left > 30:
                lines.append(f"  剩余: {days_left} 天")
            elif days_left > 0:
                lines.append(f"  ⚠️ 剩余: {days_left} 天（即将过期）")
            else:
                lines.append(f"  ❌ 已过期 {abs(days_left)} 天")
        else:
            lines.append(f"  剩余: {days_left}")

        alt_names = result.get('alt_names', [])
        if alt_names:
            lines.append("")
            lines.append("🔗 支持域名:")
            for name in alt_names[:10]:
                lines.append(f"  • {name}")
            if len(alt_names) > 10:
                lines.append(f"  ... 等共 {len(alt_names)} 个域名")

        self.ssl_enhanced_result.setPlainText("\n".join(lines))

    # -----------------------------------------------------------------------
    # 密码生成
    # -----------------------------------------------------------------------
    def do_generate_password(self):
        length = self.password_length_input.value()
        include_upper = self.password_upper_check.isChecked()
        include_lower = self.password_lower_check.isChecked()
        include_digits = self.password_digit_check.isChecked()
        include_special = self.password_special_check.isChecked()

        if not (include_upper or include_lower or include_digits or include_special):
            QMessageBox.warning(self, "提示", "至少选择一种字符类型")
            return

        self._start_thread(
            PasswordGenThread,
            self.on_password_gen_result,
            length, include_upper, include_lower, include_digits, include_special
        )

    def on_password_gen_result(self, result):
        if result['success']:
            self.password_result_input.setText(result['password'])
            strength_text, strength_color = result['strength']
            self.password_strength_label.setText(strength_text)
            self.password_strength_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {strength_color};")
        else:
            QMessageBox.warning(self, "提示", result['error'])

    def do_copy_password(self):
        password = self.password_result_input.text()
        if not password:
            QMessageBox.warning(self, "提示", "请先生成密码")
            return
        
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(password)
        QMessageBox.information(self, "提示", "密码已复制到剪贴板")

    # -----------------------------------------------------------------------
    # NSLookup
    # -----------------------------------------------------------------------
    def do_nslookup(self):
        domain = self.nslookup_domain_input.text().strip()
        dns_server = self.nslookup_server_input.text().strip() or None
        record_type = self.nslookup_type_combo.currentText()
        
        if not domain:
            QMessageBox.warning(self, "提示", "请输入域名")
            return

        self.nslookup_result.setPlainText(f"正在查询 {domain} ({record_type})...")
        self._start_thread(
            NSLookupThread,
            self.on_nslookup_result,
            domain, dns_server, record_type
        )

    def on_nslookup_result(self, result):
        if result['success']:
            output = []
            output.append(f"> nslookup {result.get('server', '')}")
            output.append("")
            output.append(f"服务器: {result['server']}")
            output.append("")
            output.append(f"名称: {self.nslookup_domain_input.text().strip()}")
            output.append("")
            output.append("Addresses:")
            for i, record in enumerate(result['records'], 1):
                output.append(f"  {record}")
            self.nslookup_result.setPlainText("\n".join(output))
        else:
            self.nslookup_result.setPlainText(f"> nslookup\n\n❌ 查询失败: {result['error']}")

    # -----------------------------------------------------------------------
    # 连接统计
    # -----------------------------------------------------------------------
    def do_connection_stats(self):
        self.connection_stats_result.setPlainText("正在获取连接统计...")
        self._start_thread(
            ConnectionStatsThread,
            self.on_connection_stats_result
        )

    def on_connection_stats_result(self, result):
        if not result['success']:
            self.connection_stats_result.setPlainText(f"❌ 获取连接统计失败: {result['error']}")
            return

        lines = []
        lines.append("📊 网络连接统计")
        lines.append("=" * 50)
        lines.append(f"总连接数: {result['total']}")
        lines.append(f"  TCP连接: {result['tcp_count']}")
        lines.append(f"  UDP连接: {result['udp_count']}")
        lines.append("")
        lines.append("TCP状态分布:")
        
        tcp_states = result.get('tcp_states', {})
        if tcp_states:
            for state, count in tcp_states.items():
                lines.append(f"  {state}: {count}")
        else:
            lines.append("  无TCP连接")

        lines.append("")
        lines.append("🔝 Top 10 远程IP:")
        top_ips = result.get('top_ips', [])
        if top_ips:
            for ip, count in top_ips:
                lines.append(f"  {ip}: {count} 次")
        else:
            lines.append("  无外部连接")

        self.connection_stats_result.setPlainText("\n".join(lines))

    # -----------------------------------------------------------------------
    # 端口进程
    # -----------------------------------------------------------------------
    def do_port_process(self):
        filter_port = self.port_process_filter_input.text().strip() or None
        self._start_thread(
            PortProcessThread,
            self.on_port_process_result,
            filter_port
        )

    def on_port_process_result(self, result):
        self.port_process_table.setRowCount(0)
        
        if not result['success']:
            QMessageBox.warning(self, "提示", f"获取端口列表失败: {result['error']}")
            return

        data = result.get('data', [])
        for i, item in enumerate(data):
            self.port_process_table.insertRow(i)
            self.port_process_table.setItem(i, 0, QTableWidgetItem(item['protocol']))
            self.port_process_table.setItem(i, 1, QTableWidgetItem(f"{item['local_ip']}:{item['local_port']}"))
            
            if item['remote_ip']:
                self.port_process_table.setItem(i, 2, QTableWidgetItem(f"{item['remote_ip']}:{item['remote_port']}"))
            else:
                self.port_process_table.setItem(i, 2, QTableWidgetItem("-"))
                
            self.port_process_table.setItem(i, 3, QTableWidgetItem(item['status']))
            self.port_process_table.setItem(i, 4, QTableWidgetItem(str(item['pid'])))
            self.port_process_table.setItem(i, 5, QTableWidgetItem(item['process_name']))
            self.port_process_table.setItem(i, 6, QTableWidgetItem(item['process_path']))

        QMessageBox.information(self, "提示", f"共找到 {len(data)} 条端口占用记录")

    # -----------------------------------------------------------------------
    # 页面清理
    # -----------------------------------------------------------------------
    def cleanup(self):
        """停止所有后台线程并断开信号连接，供页面切换时调用。"""
        self.dns_stop_event.set()
        for t in self.threads:
            try:
                t.result_signal.disconnect()
            except Exception:
                pass
            try:
                t.progress_signal.disconnect()
            except Exception:
                pass
            try:
                t.finished_signal.disconnect()
            except Exception:
                pass
            if t.isRunning():
                t.quit()
                t.wait(2000)
        self.threads.clear()

    def stop_all(self):
        self.cleanup()

    def stop_update_timer(self):
        self.cleanup()
