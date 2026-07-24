"""
摄像头扫描页面

技术实现（裸 socket，不依赖第三方库）：
1. ONVIF Discovery: WS-Discovery 协议，UDP 239.255.255.250 端口 3702
   - 发送 Probe XML 探测包
   - 监听响应中的 XAddrs，提取设备 URL
2. RTSP DESCRIBE 探测: TCP 554 端口发送 DESCRIBE 请求
   - 解析 SDP 响应中的设备信息
3. HTTP 登录页探测: TCP 80/8080 端口发送 GET /
   - 检查 Server 头和 HTML 关键字

设计稿参考：
- 左侧：扫描参数 + 统计 + 扫描结果
- 右侧：扫描说明
"""
import socket
import struct
import threading
import re
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSpinBox, QCheckBox, QButtonGroup, QRadioButton,
    QMessageBox, QFileDialog, QProgressBar
)
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont


# ============================================================
#  ONVIF WS-Discovery 协议实现（裸 socket）
# ============================================================
WS_DISCOVERY_MULTICAST_IP = "239.255.255.250"
WS_DISCOVERY_PORT = 3702

ONVIF_PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:dn="http://www.onvif.org/ver10/network/wsdl" xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">uuid:{message_id}</wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>dn:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>"""


def send_onvif_probe(timeout=3):
    """
    发送 ONVIF WS-Discovery 探测包，接收设备响应。

    返回:
        list of dict, 每个 dict 包含 ip, xaddrs, types
    """
    message_id = str(uuid.uuid4())
    probe_msg = ONVIF_PROBE_TEMPLATE.format(message_id=message_id).encode("utf-8")

    devices = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)

    try:
        sock.sendto(probe_msg, (WS_DISCOVERY_MULTICAST_IP, WS_DISCOVERY_PORT))
        end_time = time.time() + timeout
        seen_ips = set()

        while time.time() < end_time:
            try:
                data, addr = sock.recvfrom(8192)
                response = data.decode("utf-8", errors="ignore")
                ip = addr[0]

                if ip in seen_ips:
                    continue
                seen_ips.add(ip)

                # 提取 XAddrs
                xaddrs_match = re.search(r"<XAddrs>(.*?)</XAddrs>", response, re.DOTALL)
                types_match = re.search(r"<Types>(.*?)</Types>", response, re.DOTALL)
                scopes_match = re.search(r"<Scopes>(.*?)</Scopes>", response, re.DOTALL)

                if xaddrs_match:
                    xaddrs = xaddrs_match.group(1).strip()
                    types = types_match.group(1).strip() if types_match else ""
                    scopes = scopes_match.group(1).strip() if scopes_match else ""

                    devices.append({
                        "ip": ip,
                        "xaddrs": xaddrs,
                        "types": types,
                        "scopes": scopes
                    })
            except socket.timeout:
                break
            except Exception:
                continue
    except Exception:
        pass
    finally:
        sock.close()

    return devices


# ============================================================
#  RTSP DESCRIBE 探测
# ============================================================
def probe_rtsp_describe(host, port=554, timeout=2):
    """
    发送 RTSP DESCRIBE 请求，解析 SDP 响应。

    返回:
        dict: {"available": bool, "url": str, "server": str, "sdp_info": str}
        失败返回 None
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        request = (
            f"DESCRIBE rtsp://{host}:{port}/ RTSP/1.0\r\n"
            f"CSeq: 1\r\n"
            f"User-Agent: NetworkToolkit/1.0\r\n"
            f"Accept: application/sdp\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode("utf-8"))

        # 接收响应（最多 4KB）
        response = b""
        sock.settimeout(timeout)
        while b"\r\n\r\n" not in response and len(response) < 4096:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break

        response_text = response.decode("utf-8", errors="ignore")
        # 检查 RTSP/1.0 200 OK
        if "RTSP/1.0 200" in response_text or "RTSP/2.0 200" in response_text:
            # 提取 Server 头
            server_match = re.search(r"Server:\s*(.+)", response_text, re.IGNORECASE)
            server = server_match.group(1).strip() if server_match else ""
            return {
                "available": True,
                "url": f"rtsp://{host}:{port}/",
                "server": server,
                "sdp_info": "RTSP流媒体设备"
            }
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return None


def probe_rtsp_port(host, port=554, timeout=1):
    """仅探测 554 端口是否开放（快速模式）"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


# ============================================================
#  HTTP 登录页探测（辅助识别）
# ============================================================
def probe_http(host, port=80, timeout=2):
    """
    发送 HTTP GET / 请求，检查是否为摄像头登录页。

    返回:
        dict: {"available": bool, "server": str, "title": str}
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: NetworkToolkit/1.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode("utf-8"))

        response = b""
        sock.settimeout(timeout)
        while len(response) < 8192:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break

        response_text = response.decode("utf-8", errors="ignore")
        if "HTTP/1." not in response_text and "HTTP/2" not in response_text:
            return None

        # 提取 Server 头
        server_match = re.search(r"Server:\s*(.+)", response_text, re.IGNORECASE)
        server = server_match.group(1).strip() if server_match else ""

        # 提取 <title>
        title_match = re.search(r"<title[^>]*>(.*?)</title>", response_text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        return {
            "available": True,
            "server": server,
            "title": title
        }
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


# ============================================================
#  MAC 地址查询
# ============================================================
def parse_mac_address(ip):
    """通过 arp 命令查询 IP 的 MAC 地址"""
    import subprocess
    try:
        result = subprocess.run(
            ["arp", "-a", ip],
            capture_output=True, text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW
        )
        match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', result.stdout)
        if match:
            return match.group(0).upper().replace("-", ":")
    except Exception:
        pass
    return None


# ============================================================
#  扫描信号 Worker
# ============================================================
class CameraScanWorker(QObject):
    status_signal = Signal(str)
    progress_signal = Signal(int)
    result_signal = Signal(dict)
    scan_progress_signal = Signal(int, int)  # (completed, total)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False

    def emit_status(self, text):
        self.status_signal.emit(text)

    def emit_progress(self, value):
        self.progress_signal.emit(value)

    def emit_result(self, data):
        self.result_signal.emit(data)

    def emit_scan_progress(self, completed, total):
        self.scan_progress_signal.emit(completed, total)

    def emit_finished(self):
        self.finished_signal.emit()


# ============================================================
#  主页面
# ============================================================
class CameraScanPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self.thread = None
        self.found_cameras = []     # 扫描到的摄像头列表
        self.worker = CameraScanWorker()

        # 信号连接（所有 UI 更新都通过主线程槽函数）
        self.worker.status_signal.connect(self.update_status)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.add_result)
        self.worker.scan_progress_signal.connect(self.on_scan_progress)
        self.worker.finished_signal.connect(self.on_scan_finished)

        self.init_ui()

    # -------------------- 资源清理 --------------------
    def stop_update_timer(self):
        """页面隐藏/关闭时统一停止扫描"""
        self.is_running = False
        self.worker.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)

    # -------------------- 槽函数 --------------------
    def update_status(self, text):
        if hasattr(self, 'result_text'):
            self.result_text.append(f"<span style='color:#888'>{text}</span>")

    def update_progress(self, value):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)

    def on_scan_progress(self, completed, total):
        """主线程槽函数：更新已扫描统计"""
        if hasattr(self, 'stat_scanned'):
            self.stat_scanned.setText(str(completed))
        if hasattr(self, 'stat_progress'):
            self.stat_progress.setText(f"{int(completed / max(total, 1) * 100)}%")

    def add_result(self, data):
        """主线程槽函数：插入摄像头发现结果"""
        if not hasattr(self, 'result_text'):
            return
        ip = data.get("ip", "")
        port = data.get("port", "-")
        brand = data.get("brand", "通用")
        model = data.get("model", "未知")
        rtsp = data.get("rtsp", "不可用")
        status = data.get("status", "在线")
        web_url = data.get("web", "-")
        mac = data.get("mac", "-")

        # 格式化（按设计稿：定宽对齐）
        line = (
            f"<span style='color:#4ec9b0'>[📹 发现]</span> "
            f"<span style='color:#d4d4d4'>IP: {ip:<15s}</span> "
            f"<span style='color:#888'>| 端口: {str(port):<6s}</span> "
            f"<span style='color:#d4d4d4'>| 品牌: {brand:<14s}</span> "
            f"<span style='color:#888'>| 型号: {model:<22s}</span> "
            f"<span style='color:#d4d4d4'>| RTSP: {rtsp:<6s}</span> "
            f"<span style='color:#888'>| 状态: {status:<6s}</span> "
            f"<span style='color:#d4d4d4'>| Web: {web_url}</span> "
            f"<span style='color:#888'>| MAC: {mac}</span>"
        )
        self.result_text.append(line)
        # 更新发现数
        if hasattr(self, 'stat_found'):
            self.stat_found.setText(str(len(self.found_cameras)))

    def on_scan_finished(self):
        """主线程槽函数：扫描完成"""
        self.is_running = False
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(True)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setEnabled(False)
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(100)

    # -------------------- UI 初始化 --------------------
    def init_ui(self):
        """
        整体布局：
        - 左侧 (3/4 宽度): 扫描参数 + 统计 + 结果
        - 右侧 (1/4 宽度): 扫描说明
        """
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ----- 左侧主区 -----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)
        root.addWidget(left, 3)

        # 扫描参数
        self._build_param_area(left_layout)

        # 统计
        self._build_stats_area(left_layout)

        # 扫描结果
        self._build_result_area(left_layout)

        # ----- 右侧说明栏 -----
        right = self._build_help_panel()
        root.addWidget(right, 1)

    def _build_param_area(self, parent_layout):
        """扫描参数区"""
        title = QLabel("⚙ 扫描参数")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        grid = QGridLayout(frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(12)

        # 网络范围
        grid.addWidget(self._styled_label("🌐 网络范围:"), 0, 0)
        self.subnet_input = QLineEdit("192.168.1.0/24")
        self.subnet_input.setStyleSheet(self._lineedit_style())
        self.subnet_input.setMinimumWidth(280)
        tip = QLabel("💡 扫描IP段内的监控摄像头设备")
        tip.setStyleSheet("color: #888; font-size: 11px;")
        tip_layout = QHBoxLayout()
        tip_layout.addWidget(self.subnet_input)
        tip_layout.addWidget(tip)
        tip_layout.addStretch()
        grid.addLayout(tip_layout, 0, 1, 1, 3)

        # 扫描品牌（多选）
        grid.addWidget(self._styled_label("📹 扫描品牌:"), 1, 0)
        brand_layout = QHBoxLayout()
        self.brand_checks = {}
        brands = [("海康威视", "hikvision"), ("大华", "dahua"), ("宇视", "uniview"),
                  ("天地伟业", "tianshi"), ("通用", "generic")]
        for name, key in brands:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet("color: #555; font-size: 12px;")
            brand_layout.addWidget(cb)
            self.brand_checks[key] = cb
        brand_layout.addStretch()
        grid.addLayout(brand_layout, 1, 1, 1, 3)

        # 扫描模式
        grid.addWidget(self._styled_label("🔧 扫描模式:"), 2, 0)
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_fast = QRadioButton("⚡ 快速扫描")
        self.mode_deep = QRadioButton("🔍 深度扫描")
        self.mode_onvif = QRadioButton("🌐 ONVIF发现")
        self.mode_fast.setChecked(True)
        for r in (self.mode_fast, self.mode_deep, self.mode_onvif):
            r.setStyleSheet("color: #555; font-size: 12px;")
            mode_layout.addWidget(r)
            self.mode_group.addButton(r)
        mode_layout.addStretch()
        grid.addLayout(mode_layout, 2, 1, 1, 3)

        # 线程数 / 超时
        grid.addWidget(self._styled_label("⚡ 线程数:"), 3, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 200)
        self.threads_spin.setValue(50)
        self.threads_spin.setStyleSheet(self._spinbox_style())
        grid.addWidget(self.threads_spin, 3, 1)

        grid.addWidget(self._styled_label("⏱ 超时(秒):"), 3, 2)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(2)
        self.timeout_spin.setStyleSheet(self._spinbox_style())
        grid.addWidget(self.timeout_spin, 3, 3)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.start_btn = QPushButton("🔍 开始扫描")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet(self._primary_btn_style("#00bcd4", "#00acc1"))
        self.start_btn.clicked.connect(self.start_scan)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止扫描")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._secondary_btn_style())
        self.stop_btn.clicked.connect(self.stop_scan)
        btn_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🗑 清空结果")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(self._secondary_btn_style())
        self.clear_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(self.clear_btn)

        self.export_btn = QPushButton("💾 导出清单")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(self._secondary_btn_style())
        self.export_btn.clicked.connect(self.export_results)
        btn_layout.addWidget(self.export_btn)
        grid.addLayout(btn_layout, 4, 0, 1, 4)

        parent_layout.addWidget(frame)

        # 蓝色分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #00bcd4; min-height: 2px; border: none;")
        parent_layout.addWidget(line)

    def _build_stats_area(self, parent_layout):
        """统计区"""
        title = QLabel("📊 统计")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)

        # 总IP / 已检测 / 发现 / 进度（保存 value 标签引用以便更新）
        self.stat_total_frame, self.stat_total = self._make_stat_label("扫描IP:", "0", "#3498db")
        self.stat_scanned_frame, self.stat_scanned = self._make_stat_label("已检测:", "0", "#f39c12")
        self.stat_found_frame, self.stat_found = self._make_stat_label("发现:", "0", "#27ae60")
        self.stat_progress_frame, self.stat_progress = self._make_stat_label("进度:", "0%", "#9b59b6")

        for c in (self.stat_total_frame, self.stat_scanned_frame, self.stat_found_frame, self.stat_progress_frame):
            stats_layout.addWidget(c)
        stats_layout.addStretch()
        parent_layout.addLayout(stats_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: #e0e0e0;
            }
            QProgressBar::chunk {
                background: #00bcd4;
                border-radius: 4px;
            }
        """)
        parent_layout.addWidget(self.progress_bar)

    def _build_result_area(self, parent_layout):
        """扫描结果区"""
        title = QLabel("📋 扫描结果")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, "Microsoft YaHei";
                font-size: 11px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #1e1e1e;
                color: #d4d4d4;
                padding: 8px;
            }
        """)
        parent_layout.addWidget(self.result_text, 1)

    def _build_help_panel(self):
        """右侧扫描说明栏"""
        panel = QWidget()
        panel.setStyleSheet("background: #fafafa; border-left: 1px solid #e0e0e0;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 标题
        title = QLabel("💡 扫描说明")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # 支持的协议
        layout.addWidget(self._help_section("支持的协议:", [
            "• HTTP/HTTPS 通用协议",
            "• ONVIF 标准协议",
            "• RTSP 流媒体协议",
            "• 常见品牌通用端口"
        ]))

        # 扫描限制
        layout.addWidget(self._help_section("⚠ 扫描限制:", [
            "• 仅支持标准通用协议",
            "• 私有协议无法识别",
            "• 部分厂商定制协议不支持",
            "• 需要认证的设备可能无法检测"
        ]))

        # 扫描建议
        layout.addWidget(self._help_section("💡 扫描建议:", [
            "• 优先使用「通用」模式",
            "• ONVIF模式兼容性好",
            "• 深度扫描耗时较长",
            "• 建议在局域网内扫描"
        ]))

        # 当前状态
        self.status_info = QLabel("状态: 待扫描")
        self.status_info.setStyleSheet("""
            color: #555; font-size: 12px; padding: 10px;
            background: white; border: 1px solid #e0e0e0; border-radius: 3px;
        """)
        self.status_info.setWordWrap(True)
        layout.addWidget(self.status_info)

        layout.addStretch()
        return panel

    def _help_section(self, title, items):
        """帮助栏的子区块"""
        section = QWidget()
        v = QVBoxLayout(section)
        v.setContentsMargins(0, 5, 0, 5)
        v.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 12px;")
        v.addWidget(lbl_title)

        for item in items:
            lbl = QLabel(item)
            lbl.setStyleSheet("color: #555; font-size: 11px;")
            v.addWidget(lbl)

        return section

    def _make_stat_label(self, label, value, color):
        """生成统计卡片（label + 数值 横排）"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #e0e0e0;
                border-left: 3px solid {color};
                border-radius: 3px;
            }}
        """)
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #888; font-size: 11px;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        h.addWidget(lbl)
        h.addWidget(val)
        h.addStretch()
        frame.setMaximumWidth(150)
        return frame, val

    # ============================================================
    #  扫描核心逻辑
    # ============================================================
    def parse_subnet(self, subnet):
        try:
            import ipaddress
            network = ipaddress.IPv4Network(subnet, strict=False)
            return [str(ip) for ip in network.hosts()]
        except Exception:
            base = ".".join(subnet.split(".")[:3])
            return [f"{base}.{i}" for i in range(1, 255)]

    def start_scan(self):
        if self.is_running:
            return

        subnet = self.subnet_input.text().strip()
        hosts = self.parse_subnet(subnet)
        total = len(hosts)
        if total == 0:
            self.update_status("[错误] 无效的网段")
            return

        self.is_running = True
        self.worker.is_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.found_cameras = []
        self.result_text.clear()
        self.progress_bar.setValue(0)
        # 重置统计数值
        self.stat_total.setText(str(total))
        self.stat_scanned.setText("0")
        self.stat_found.setText("0")
        self.stat_progress.setText("0%")
        if hasattr(self, 'status_info'):
            self.status_info.setText("状态: 正在扫描...")

        self.thread = threading.Thread(target=self.run_scan, args=(hosts, total))
        self.thread.start()

    def stop_scan(self):
        self.is_running = False
        self.worker.is_running = False
        self.worker.emit_status("正在停止扫描...")

    def clear_results(self):
        self.result_text.clear()
        self.found_cameras = []

    def export_results(self):
        if not self.found_cameras:
            QMessageBox.information(self, "提示", "暂无扫描结果可导出")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存扫描结果",
            f"camera_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "文本文件 (*.txt);;CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                if path.endswith(".csv"):
                    f.write("IP,端口,品牌,型号,RTSP,状态,Web,MAC\n")
                    for c in self.found_cameras:
                        f.write(f"{c.get('ip','')},{c.get('port','')},{c.get('brand','')},{c.get('model','')},{c.get('rtsp','')},{c.get('status','')},{c.get('web','')},{c.get('mac','')}\n")
                else:
                    f.write(f"摄像头扫描结果 - {self.subnet_input.text().strip()}\n")
                    f.write("=" * 100 + "\n")
                    f.write(f"{'IP':<16} {'端口':<6} {'品牌':<10} {'型号':<20} {'RTSP':<8} {'状态':<6} {'Web':<35} {'MAC':<18}\n")
                    f.write("-" * 100 + "\n")
                    for c in self.found_cameras:
                        f.write(f"{c.get('ip',''):<16} {str(c.get('port','-')):<6} {c.get('brand','通用'):<10} {c.get('model','未知'):<20} {c.get('rtsp','不可用'):<8} {c.get('status','在线'):<6} {c.get('web','-'):<35} {c.get('mac','-'):<18}\n")
            QMessageBox.information(self, "成功", f"已导出到: {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def run_scan(self, hosts, total):
        """
        后台线程：执行摄像头扫描。

        模式说明：
        - fast: 仅探测 554 端口
        - deep: RTSP DESCRIBE + HTTP 探测
        - onvif: WS-Discovery 协议 + 单 IP 探测
        """
        timeout = self.timeout_spin.value()
        threads = self.threads_spin.value()

        # 模式选择
        if self.mode_fast.isChecked():
            mode = "fast"
        elif self.mode_deep.isChecked():
            mode = "deep"
        else:
            mode = "onvif"

        self.worker.emit_status("=" * 88)
        self.worker.emit_status("摄像头扫描开始")
        self.worker.emit_status(f"扫描网络: {self.subnet_input.text().strip()}  (共 {total} 个 IP)")
        self.worker.emit_status(f"扫描模式: {mode}")
        self.worker.emit_status("=" * 88)

        # ONVIF 模式：先发送 WS-Discovery（找到的所有设备 ip 单独探测）
        onvif_ips = set()
        if mode == "onvif" and self.is_running:
            self.worker.emit_status("[阶段 1/2] ONVIF WS-Discovery 探测...")
            try:
                onvif_devices = send_onvif_probe(timeout=timeout + 1)
                for dev in onvif_devices:
                    ip = dev.get("ip", "")
                    if ip:
                        onvif_ips.add(ip)
                self.worker.emit_status(f"  → ONVIF 发现 {len(onvif_ips)} 个设备: {', '.join(sorted(onvif_ips)) if onvif_ips else '无'}")
            except Exception as e:
                self.worker.emit_status(f"  → ONVIF 探测失败: {e}")
            self.worker.emit_status("")

        # 端口/RTSP 探测
        completed = 0
        with ThreadPoolExecutor(max_workers=threads) as executor:
            if mode == "onvif":
                # ONVIF 模式：只扫描发现的 IP
                target_hosts = list(onvif_ips)
                if not target_hosts:
                    target_hosts = hosts  # fallback
            else:
                target_hosts = hosts

            futures = {
                executor.submit(self._scan_one, host, timeout, mode): host
                for host in target_hosts
            }
            for future in as_completed(futures):
                if not self.is_running:
                    break
                completed += 1
                progress = int((completed / max(len(target_hosts), 1)) * 100)
                self.worker.emit_progress(progress)
                # 通过信号通知主线程更新统计（线程安全）
                self.worker.emit_scan_progress(completed, len(target_hosts))
                try:
                    data = future.result()
                    if data:
                        self.found_cameras.append(data)
                        self.worker.emit_result(data)
                except Exception:
                    pass

        if self.is_running:
            self.worker.emit_status("=" * 88)
            self.worker.emit_status(f"✅ 扫描完成, 发现 {len(self.found_cameras)} 个摄像头, 扫描 {completed} 个 IP")
            self.worker.emit_progress(100)
        else:
            self.worker.emit_status(f"⏹ 扫描已停止, 已扫 {completed} / 发现 {len(self.found_cameras)}")

        self.worker.emit_finished()

    def _scan_one(self, host, timeout, mode):
        """
        单个主机摄像头探测。

        返回 dict（含发现结果）或 None。
        """
        try:
            if mode == "fast":
                # 快速模式：仅检查 554 端口
                if probe_rtsp_port(host, 554, timeout=timeout):
                    return self._build_camera_dict(host, 554, "通用", "RTSP流媒体设备", "可用", "在线", f"rtsp://{host}:554", is_rtsp=True)
            elif mode == "deep":
                # 深度模式：RTSP DESCRIBE + HTTP
                rtsp_result = probe_rtsp_describe(host, 554, timeout=timeout)
                if rtsp_result:
                    model = rtsp_result.get("sdp_info", "RTSP流媒体设备")
                    if rtsp_result.get("server"):
                        model = f"{rtsp_result.get('server')[:20]}"
                    return self._build_camera_dict(host, 554, "通用", model, "可用", "在线", f"rtsp://{host}:554", is_rtsp=True)
                # 尝试 HTTP 80/8080
                for port in (80, 8080):
                    http_result = probe_http(host, port, timeout=timeout)
                    if http_result:
                        title = http_result.get("title", "")[:20]
                        if "camera" in title.lower() or "ipc" in title.lower() or "视频" in title or "监控" in title:
                            return self._build_camera_dict(host, port, "通用", title or "HTTP摄像头", "不可用", "在线", f"http://{host}:{port}", is_rtsp=False)
            elif mode == "onvif":
                # ONVIF 模式：完整探测 554 + HTTP
                rtsp_result = probe_rtsp_describe(host, 554, timeout=timeout)
                if rtsp_result:
                    model = rtsp_result.get("sdp_info", "ONVIF摄像头")
                    if rtsp_result.get("server"):
                        model = f"{rtsp_result.get('server')[:20]}"
                    return self._build_camera_dict(host, 554, "通用", model, "可用", "在线", f"rtsp://{host}:554", is_rtsp=True)
        except Exception:
            return None
        return None

    def _build_camera_dict(self, ip, port, brand, model, rtsp, status, web, is_rtsp=False):
        """构造摄像头结果字典"""
        mac = parse_mac_address(ip)
        return {
            "ip": ip,
            "port": port,
            "brand": brand,
            "model": model,
            "rtsp": rtsp,
            "status": status,
            "web": web,
            "mac": mac or "-"
        }

    # ============================================================
    #  样式辅助方法
    # ============================================================
    def _styled_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #555; font-size: 12px;")
        return lbl

    def _lineedit_style(self):
        return """
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
            }
        """

    def _spinbox_style(self):
        """返回 QSpinBox 统一样式，使用 SVG 箭头避免黑色方块。"""
        return """
            QSpinBox {
                padding: 2px 24px 2px 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                font-size: 13px;
                min-height: 30px;
                min-width: 90px;
            }
            QSpinBox:hover {
                border-color: #999;
            }
        """

    def _primary_btn_style(self, color, hover):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: #e0e0e0; color: #888; }}
        """

    def _secondary_btn_style(self):
        return """
            QPushButton {
                background-color: white;
                color: #555;
                border: 1px solid #ccc;
                padding: 8px 20px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f5f5f5; }
            QPushButton:disabled { color: #aaa; }
        """
