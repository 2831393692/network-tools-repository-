"""
主机发现页面 - 完整重构

三大 Tab：
1. 扫描结果  - 扫描参数 + 实时文本结果 + 统计卡片 + 导出
2. 局域网拓扑 - pyqtgraph 可拖动节点视图
3. 远程唤醒  - 手动输入 MAC + WOL 魔术包发送
"""
import subprocess
import threading
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QRadioButton, QButtonGroup, QHeaderView, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsLineItem, QProgressBar
)
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont, QBrush, QColor, QPen


# ============================================================
#  内置 OUI 厂商库（覆盖国内主流厂商）
# ============================================================
OUI_VENDORS = {
    # 华为
    "00:1E:10": "Huawei",
    "00:25:9E": "Huawei",
    "28:6E:D4": "Huawei",
    "48:46:FB": "Huawei",
    "AC:E8:7B": "Huawei",
    "E4:68:A3": "Huawei",
    # 小米
    "28:6C:07": "Xiaomi",
    "64:09:80": "Xiaomi",
    "C0:EE:FB": "Xiaomi",
    "EC:D0:9F": "Xiaomi",
    "FC:64:BA": "Xiaomi",
    # 苹果
    "00:1F:F3": "Apple",
    "3C:07:54": "Apple",
    "A4:5E:60": "Apple",
    "B8:78:2E": "Apple",
    "DC:A9:04": "Apple",
    # 海康威视
    "00:40:48": "Hikvision",
    "28:57:BE": "Hikvision",
    "44:19:B6": "Hikvision",
    "BC:AD:28": "Hikvision",
    "C0:51:7E": "Hikvision",
    # 大华
    "00:12:12": "Dahua",
    "3C:EF:8C": "Dahua",
    "E0:3F:49": "Dahua",
    # TP-LINK
    "00:0A:EB": "TP-LINK",
    "14:CC:20": "TP-LINK",
    "1C:61:B4": "TP-LINK",
    "30:B5:C2": "TP-LINK",
    "AC:84:C6": "TP-LINK",
    # 思科
    "00:1B:0D": "Cisco",
    "00:1D:A1": "Cisco",
    "00:26:0B": "Cisco",
    "F8:4F:57": "Cisco",
    # 锐捷
    "00:1A:A9": "Ruijie",
    "30:0D:9E": "Ruijie",
    "58:69:6D": "Ruijie",
    # H3C
    "00:0F:E2": "H3C",
    "38:22:D6": "H3C",
    "80:F6:2E": "H3C",
    # 华三/惠普服务器
    "00:1A:4B": "HPE",
    "00:23:7D": "HPE",
    "28:92:4A": "HPE",
    # D-Link
    "00:1B:11": "D-Link",
    "1C:7E:E5": "D-Link",
    "28:10:7B": "D-Link",
    # 水星/迅捷
    "00:13:46": "MERCURY",
    "C8:3A:35": "MERCURY",
    # Netgear
    "00:14:6C": "Netgear",
    "20:E5:2A": "Netgear",
    "B0:7F:B9": "Netgear",
    # Intel
    "00:1B:21": "Intel",
    "00:1C:C0": "Intel",
    "7C:5C:F8": "Intel",
    "A0:88:B4": "Intel",
    # 联想
    "00:21:CC": "Lenovo",
    "1C:75:08": "Lenovo",
    "60:FB:42": "Lenovo",
    # 戴尔
    "00:14:22": "Dell",
    "00:18:8B": "Dell",
    "78:2B:CB": "Dell",
    "B0:83:FE": "Dell",
    # 微软
    "00:15:5D": "Microsoft",
    "28:18:78": "Microsoft",
    "50:1A:C5": "Microsoft",
    # 谷歌
    "F4:F5:E8": "Google",
    "F8:8F:CA": "Google",
    # 三星
    "00:1D:25": "Samsung",
    "34:23:BA": "Samsung",
    "B8:5E:7B": "Samsung",
    # Vivo/Oppo
    "70:1C:E7": "Vivo",
    "70:8A:09": "Oppo",
    "AC:C5:1B": "Oppo",
    # 360
    "C8:0E:14": "360",
    # 友讯
    "00:1E:58": "D-Link",
    # 普联
    "D4:6E:0E": "TP-LINK",
    # 中兴
    "00:1A:2A": "ZTE",
    "8C:79:67": "ZTE",
    # 烽火
    "F4:B7:2A": "FiberHome",
    # 视洞
    "E4:0D:36": "Hikvision",
    # 萤石
    "0C:4D:E9": "EZVIZ",
    # 普联/TP-LINK 补充
    "E8:94:F6": "TP-LINK",
    "B0:4E:26": "TP-LINK",
    # 海尔
    "C0:A1:A2": "Haier",
    # 美的
    "B4:E1:0F": "Midea",
    # 格力
    "AC:84:C9": "Gree",
    # 海信
    "AC:CF:5C": "Hisense",
    # 公共/广播
    "FF:FF:FF": "Broadcast",
}


def lookup_vendor(mac):
    """
    根据 MAC 地址查询厂商。
    仅取前 3 字节（OUI 字段）匹配。

    参数:
        mac: 形如 "AA:BB:CC:DD:EE:FF" 的 MAC 地址
    返回:
        厂商名称字符串，未知返回 "未知"
    """
    if not mac or mac == "未知":
        return "未知"
    # 标准化为 AA:BB:CC 大写
    parts = re.split(r"[:-]", mac)
    if len(parts) < 3:
        return "未知"
    oui = ":".join(p.upper().zfill(2) for p in parts[:3])
    return OUI_VENDORS.get(oui, "未知")


def parse_mac_address(ip):
    """
    通过 Windows arp 表查询 IP 对应的 MAC 地址。
    """
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


def resolve_hostname(ip):
    """
    反向解析 IP 的主机名。
    """
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


# ============================================================
#  扫描结果信号 Worker
# ============================================================
class HostDiscoveryWorker(QObject):
    """
    主机发现工作线程的信号中转器。

    所有后台线程产生的状态、进度、结果、完成事件都通过 Signal 发送到主线程。
    """
    status_signal = Signal(str)
    progress_signal = Signal(int)
    result_signal = Signal(dict)  # 每台主机的完整信息字典
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
        """data: {"ip", "mac", "hostname", "latency", "vendor", "role"}"""
        self.result_signal.emit(data)

    def emit_scan_progress(self, completed, total):
        self.scan_progress_signal.emit(completed, total)

    def emit_finished(self):
        self.finished_signal.emit()


# ============================================================
#  局域网拓扑 - pyqtgraph 节点视图
# ============================================================
class TopologyNode(QGraphicsEllipseItem):
    """
    拓扑图节点：圆圈 + 文字标签，支持鼠标拖动、点击弹出详情。
    """

    def __init__(self, ip, label, x, y, role="host", size=40, host_data=None):
        super().__init__(-size / 2, -size / 2, size, size)
        self.ip = ip
        self.label_text = label
        self.role = role
        self.host_data = host_data or {}  # 完整主机信息
        self.setPos(x, y)

        color_map = {
            "gateway": QColor(0, 188, 212),
            "host": QColor(76, 175, 80),
            "device": QColor(255, 152, 0),
            "other": QColor(158, 158, 158),
        }
        self.setBrush(QBrush(color_map.get(role, QColor(76, 175, 80))))
        self.setPen(QPen(Qt.black, 1.5))
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.setCursor(Qt.PointingHandCursor)

        # IP 标签
        self.text_item = QGraphicsTextItem(label, self)
        font = QFont("Microsoft YaHei", 8)
        self.text_item.setFont(font)
        br = self.text_item.boundingRect()
        self.text_item.setPos(-br.width() / 2, size / 2 + 2)

    def mousePressEvent(self, event):
        """点击节点弹出详情对话框"""
        if self.role == "gateway":
            self._show_gateway_detail()
        elif self.host_data:
            self._show_host_detail()
        super().mousePressEvent(event)

    def _show_gateway_detail(self):
        """网关节点详情"""
        msg = QMessageBox()
        msg.setWindowTitle(f"网关 {self.ip}")
        msg.setTextFormat(Qt.RichText)
        msg.setText(f"""
            <h3>网关 {self.ip}</h3>
            <table>
            <tr><td style='padding: 5px'>角色:</td><td>默认网关</td></tr>
            <tr><td style='padding: 5px'>地址:</td><td>{self.ip}</td></tr>
            </table>
        """)
        msg.exec()

    def _show_host_detail(self):
        """主机节点详情"""
        h = self.host_data
        msg = QMessageBox()
        msg.setWindowTitle(f"主机 {h.get('ip', '')}")
        msg.setTextFormat(Qt.RichText)
        msg.setText(f"""
            <h3>主机 {h.get('ip', '')}</h3>
            <table>
            <tr><td style='padding: 5px'>主机名:</td><td>{h.get('hostname', '未知')}</td></tr>
            <tr><td style='padding: 5px'>MAC:</td><td>{h.get('mac', '-')}</td></tr>
            <tr><td style='padding: 5px'>厂商:</td><td>{h.get('vendor', '未知')}</td></tr>
            <tr><td style='padding: 5px'>角色:</td><td>{h.get('role', '主机')}</td></tr>
            <tr><td style='padding: 5px'>响应:</td><td>{h.get('latency', '-')}ms</td></tr>
            </table>
        """)
        msg.exec()

    def itemChange(self, change, value):
        """节点位置变化时通知场景更新连线"""
        if change == QGraphicsEllipseItem.ItemPositionChange and self.scene():
            self.scene().emit_node_moved(self, value)
        return super().itemChange(change, value)


class TopologyScene(QGraphicsScene):
    """
    自定义场景：处理节点移动事件，更新连线端点。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gateway_node = None
        self.node_lines = {}  # node_ip -> [QGraphicsLineItem]

    def set_gateway(self, node):
        """设置网关节点（连线的中心点）"""
        self.gateway_node = node

    def add_line(self, node_ip, line):
        """添加一条连线"""
        if node_ip not in self.node_lines:
            self.node_lines[node_ip] = []
        self.node_lines[node_ip].append(line)

    def emit_node_moved(self, node, new_pos):
        """节点位置变化时更新相关连线"""
        if node.ip == "gateway":
            # 网关节点移动：更新所有连线
            if self.node_lines:
                gw_x, gw_y = new_pos.x(), new_pos.y()
                for ip, lines in self.node_lines.items():
                    if ip in self.items():
                        node_item = self.items()[0]
                        for line in lines:
                            end_x = line.line().x2()
                            end_y = line.line().y2()
                            line.setLine(gw_x, gw_y, end_x, end_y)
        else:
            # 普通节点移动：更新该节点到网关的连线
            if node.ip in self.node_lines and self.gateway_node:
                gw_x, gw_y = self.gateway_node.x(), self.gateway_node.y()
                for line in self.node_lines[node.ip]:
                    line.setLine(gw_x, gw_y, new_pos.x(), new_pos.y())


class TopologyView(QGraphicsView):
    """
    拓扑图视图：可缩放、可拖动节点、连线跟随。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = TopologyScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor(240, 245, 250)))
        self.setScene(self.scene)
        self.setRenderHint(self.renderHints())
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setMinimumHeight(400)
        self.nodes = {}     # ip -> TopologyNode
        self.lines = []     # 中心到节点的连线

    def clear(self):
        self.scene.clear()
        self.scene.gateway_node = None
        self.scene.node_lines = {}
        self.nodes = {}
        self.lines = []

    def add_gateway(self, ip, label):
        """中心网关节点"""
        node = TopologyNode(ip, label, 0, 0, role="gateway", size=60)
        node.text_item.setPlainText("GW")
        br = node.text_item.boundingRect()
        node.text_item.setPos(-br.width() / 2, -br.height() / 2)
        self.scene.addItem(node)
        self.scene.set_gateway(node)
        self.nodes[ip] = node
        return node

    def add_host_node(self, ip, label, host_data=None):
        """环形布局的普通节点（优化版：均匀分布）"""
        import math
        n = len(self.nodes) - 1  # 减去网关
        if n == 0:
            radius = 150
        elif n <= 8:
            radius = 180
        elif n <= 16:
            radius = 220
        elif n <= 24:
            radius = 260
        else:
            radius = 300 + ((n - 24) // 8) * 40

        angle = (n * (2 * math.pi / max(8, len(self.nodes) - 1)))
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)

        node = TopologyNode(ip, label, x, y, role="host", size=40, host_data=host_data)
        self.scene.addItem(node)

        # 中心到节点的连线
        if "gateway" in self.nodes:
            gw = self.nodes["gateway"]
            line = QGraphicsLineItem(gw.x(), gw.y(), x, y)
            line.setPen(QPen(QColor(180, 180, 180), 1.0))
            line.setZValue(0)
            self.scene.addItem(line)
            self.scene.add_line(ip, line)
            self.lines.append(line)

        self.nodes[ip] = node
        return node

    def wheelEvent(self, event):
        """滚轮缩放"""
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


# ============================================================
#  主页面
# ============================================================
class HostDiscoveryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.is_running = False
        self.thread = None
        self.found_hosts = []      # 扫描结果完整信息列表
        self.worker = HostDiscoveryWorker()

        self.worker.status_signal.connect(self.update_status)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.add_result)
        self.worker.scan_progress_signal.connect(self.on_scan_progress)
        self.worker.finished_signal.connect(self.on_scan_finished)

        self.init_ui()

    # -------------------- 资源清理 --------------------
    def stop_update_timer(self):
        """页面隐藏/关闭时统一释放线程和信号"""
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
    def on_scan_finished(self):
        """主线程槽函数：扫描完成后恢复 UI 状态"""
        self.is_running = False
        self.worker.is_running = False
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(True)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setEnabled(False)
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(100)
        # 刷新 WOL 列表（主线程安全）
        self._refresh_wol_list()
        # 同步到拓扑 Tab
        self._refresh_topology()

    def _get_gateway_ip(self):
        """根据当前网段输入框动态计算网关 IP（取网段的第一个可用地址）"""
        subnet = self.subnet_input.text().strip()
        try:
            import ipaddress
            network = ipaddress.IPv4Network(subnet, strict=False)
            return str(network.network_address + 1)
        except Exception:
            parts = subnet.split(".")
            if len(parts) >= 3:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.1"
            return "192.168.1.1"

    def _refresh_topology(self):
        """把扫描结果同步到拓扑视图"""
        if not hasattr(self, 'topology_view'):
            return
        self.topology_view.clear()
        gateway_ip = self._get_gateway_ip()
        self.topology_view.add_gateway(gateway_ip, "默认网关")
        for host in self.found_hosts:
            ip = host.get("ip", "")
            hostname = host.get("hostname", "") or "未知"
            label = hostname[:8] if hostname != "未知" else ip
            self.topology_view.add_host_node(ip, label, host_data=host)

    # -------------------- UI 初始化 --------------------
    def init_ui(self):
        # 整个页面 = 顶部 Tab 容器
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e0e0e0; background: white; }
            QTabBar::tab {
                padding: 8px 24px;
                font-size: 13px;
                background: #f5f5f5;
                border: 1px solid #e0e0e0;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #00bcd4;
                border-bottom: 2px solid #00bcd4;
                font-weight: bold;
            }
        """)
        self.tabs.addTab(self._build_scan_tab(), "📊 扫描结果")
        self.tabs.addTab(self._build_topology_tab(), "🕸️ 局域网拓扑")
        self.tabs.addTab(self._build_wol_tab(), "⚡ 远程唤醒")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.tabs)

    # ========== Tab 1: 扫描结果 ==========
    def _build_scan_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # ----- 扫描参数区 -----
        title = QLabel("⚙ 扫描参数")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        param_frame = QFrame()
        param_frame.setStyleSheet("""
            QFrame { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        grid = QGridLayout(param_frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(12)

        # 第 0 行：网络范围
        grid.addWidget(self._styled_label("🌐 网络范围:"), 0, 0)
        self.subnet_input = QLineEdit("192.168.1.0/24")
        self.subnet_input.setStyleSheet(self._lineedit_style())
        self.subnet_input.setMinimumWidth(280)
        grid.addWidget(self.subnet_input, 0, 1)

        # 第 1 行：扫描方式
        grid.addWidget(self._styled_label("🔍 扫描方式:"), 1, 0)
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(widget)
        self.mode_ping = QRadioButton("Ping扫描 (快速)")
        self.mode_tcp = QRadioButton("TCP连接 (推荐)")
        self.mode_mix = QRadioButton("混合模式 (全面)")
        self.mode_tcp.setChecked(True)
        for r in (self.mode_ping, self.mode_tcp, self.mode_mix):
            r.setStyleSheet("color: #555; font-size: 12px;")
            mode_layout.addWidget(r)
            self.mode_group.addButton(r)
        mode_layout.addStretch()
        grid.addLayout(mode_layout, 1, 1, 1, 3)

        # 第 2 行：线程数 / 超时（各占一半）
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(20)
        
        # 左半部分：线程数
        threads_layout = QHBoxLayout()
        threads_layout.setSpacing(8)
        threads_layout.addWidget(self._styled_label("⚡ 线程数:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 200)
        self.threads_spin.setValue(50)
        self.threads_spin.setFixedWidth(80)
        threads_layout.addWidget(self.threads_spin)
        threads_layout.addStretch()
        
        # 右半部分：超时
        timeout_layout = QHBoxLayout()
        timeout_layout.setSpacing(8)
        timeout_layout.addWidget(self._styled_label("⏱ 超时(秒):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(2)
        self.timeout_spin.setFixedWidth(80)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addStretch()
        
        row2_layout.addLayout(threads_layout, 1)
        row2_layout.addLayout(timeout_layout, 1)
        grid.addLayout(row2_layout, 2, 0, 1, 4)

        # 第 3 行：按钮组
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.start_btn = QPushButton("🚀 开始扫描")
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

        self.export_btn = QPushButton("💾 导出结果")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(self._secondary_btn_style())
        self.export_btn.clicked.connect(self.export_results)
        btn_layout.addWidget(self.export_btn)
        grid.addLayout(btn_layout, 3, 0, 1, 4)

        layout.addWidget(param_frame)

        # 蓝色分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #00bcd4; min-height: 2px; border: none;")
        layout.addWidget(line)

        # ----- 统计卡片 -----
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        self.stat_total = self._make_stat_card("总IP", "0", "#3498db")
        self.stat_scanned = self._make_stat_card("已扫", "0", "#f39c12")
        self.stat_active = self._make_stat_card("存活", "0", "#27ae60")
        self.stat_progress = self._make_stat_card("进度", "0%", "#9b59b6")
        for c in (self.stat_total, self.stat_scanned, self.stat_active, self.stat_progress):
            stats_layout.addWidget(c)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # ----- 进度条 -----
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #00bcd4;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # ----- 扫描结果黑底文本框 -----
        result_title = QLabel("📋 扫描结果")
        result_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        layout.addWidget(result_title)

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
        layout.addWidget(self.result_text)

        return widget

    def _make_stat_card(self, label, value, color):
        """生成统计卡片：标签 + 大字号数值"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #e0e0e0;
                border-left: 3px solid {color};
                border-radius: 3px;
            }}
        """)
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #888; font-size: 11px;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
        val.setObjectName(f"stat_{label}")
        v.addWidget(lbl)
        v.addWidget(val)
        frame.setMaximumWidth(110)
        return frame

    def _update_stat(self, card, value):
        """更新统计卡片数值"""
        for child in card.findChildren(QLabel):
            if child.objectName():
                child.setText(value)
                return

    # ========== Tab 2: 局域网拓扑 ==========
    def _build_topology_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 工具栏
        toolbar = QHBoxLayout()
        self.refresh_topo_btn = QPushButton("🔄 刷新拓扑")
        self.refresh_topo_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_topo_btn.setStyleSheet(self._secondary_btn_style())
        self.refresh_topo_btn.clicked.connect(self._refresh_topology)
        toolbar.addWidget(self.refresh_topo_btn)

        self.reset_layout_btn = QPushButton("📐 重置布局")
        self.reset_layout_btn.setCursor(Qt.PointingHandCursor)
        self.reset_layout_btn.setStyleSheet(self._secondary_btn_style())
        self.reset_layout_btn.clicked.connect(self._reset_topology_layout)
        toolbar.addWidget(self.reset_layout_btn)

        self.topo_info_label = QLabel("设备数: 0 | 网关: -- | 点击节点查看详情，可拖动")
        self.topo_info_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self.topo_info_label)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 标题
        title = QLabel("🕸️ 局域网拓扑图")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        # 拓扑视图
        self.topology_view = TopologyView()
        layout.addWidget(self.topology_view)

        return widget

    def _reset_topology_layout(self):
        """重新布局节点（环形均分）"""
        if not self.found_hosts:
            return
        import math
        self.topology_view.clear()
        gateway_ip = self._get_gateway_ip()
        self.topology_view.add_gateway(gateway_ip, "默认网关")
        for i, host in enumerate(self.found_hosts):
            ip = host.get("ip", "")
            hostname = host.get("hostname", "") or "未知"
            label = hostname[:8] if hostname != "未知" else ip
            n = i + 1
            radius = 200
            angle = (n * (2 * math.pi / max(len(self.found_hosts), 1)))
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            node = TopologyNode(ip, label, x, y, role="host", size=40, host_data=host)
            self.topology_view.scene.addItem(node)
            # 连线
            gw = self.topology_view.nodes[gateway_ip]
            line = QGraphicsLineItem(gw.x(), gw.y(), x, y)
            line.setPen(QPen(QColor(180, 180, 180), 1.0))
            line.setZValue(0)
            self.topology_view.scene.addItem(line)
            self.topology_view.scene.add_line(ip, line)
            self.topology_view.lines.append(line)
            self.topology_view.nodes[ip] = node

    # ========== Tab 3: 远程唤醒 ==========
    def _build_wol_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 顶部说明
        tip = QLabel("💡 先完成「扫描结果」主机发现获取 MAC，或手动输入 MAC 地址发送魔术包唤醒设备")
        tip.setStyleSheet("color: #888; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 主体：左右两栏
        body = QHBoxLayout()
        body.setSpacing(15)

        # 左栏：可唤醒主机列表
        left = QVBoxLayout()
        left_title = QLabel("📋 可唤醒主机 (来自最近扫描)")
        left_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        left.addWidget(left_title)

        self.wol_table = QTableWidget()
        self.wol_table.setColumnCount(4)
        self.wol_table.setHorizontalHeaderLabels(["IP", "MAC", "主机名", "厂商"])
        self.wol_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wol_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.wol_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.wol_table.itemSelectionChanged.connect(self._on_wol_row_selected)
        self.wol_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e0e0e0;
                gridline-color: #f0f0f0;
                font-size: 12px;
            }
            QHeaderView::section {
                background: #f5f5f5;
                padding: 6px;
                border: 1px solid #e0e0e0;
                font-weight: bold;
            }
        """)
        left.addWidget(self.wol_table)

        left_btn_row = QHBoxLayout()
        self.refresh_list_btn = QPushButton("🔄 刷新列表")
        self.refresh_list_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_list_btn.setStyleSheet(self._secondary_btn_style())
        self.refresh_list_btn.clicked.connect(self._refresh_wol_list)
        left_btn_row.addWidget(self.refresh_list_btn)

        self.wake_selected_btn = QPushButton("⚡ 唤醒选中")
        self.wake_selected_btn.setCursor(Qt.PointingHandCursor)
        self.wake_selected_btn.setStyleSheet(self._primary_btn_style("#ff9800", "#f57c00"))
        self.wake_selected_btn.clicked.connect(self._wake_selected)
        left_btn_row.addWidget(self.wake_selected_btn)
        left_btn_row.addStretch()
        left.addLayout(left_btn_row)

        # 右栏：手动输入
        right = QVBoxLayout()
        right_title = QLabel("⚡ 手动唤醒")
        right_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        right.addWidget(right_title)

        mac_label = QLabel("MAC 地址:")
        mac_label.setStyleSheet("color: #555; font-size: 12px;")
        right.addWidget(mac_label)
        self.mac_input = QLineEdit()
        self.mac_input.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.mac_input.setStyleSheet(self._lineedit_style())
        right.addWidget(self.mac_input)

        bcast_label = QLabel("广播地址:")
        bcast_label.setStyleSheet("color: #555; font-size: 12px; margin-top: 8px;")
        right.addWidget(bcast_label)
        self.broadcast_input = QLineEdit("255.255.255.255")
        self.broadcast_input.setStyleSheet(self._lineedit_style())
        right.addWidget(self.broadcast_input)

        right.addSpacing(8)
        self.send_wol_btn = QPushButton("⚡ 发送唤醒包")
        self.send_wol_btn.setCursor(Qt.PointingHandCursor)
        self.send_wol_btn.setStyleSheet(self._primary_btn_style("#ff9800", "#f57c00"))
        self.send_wol_btn.clicked.connect(self._send_wol_manual)
        right.addWidget(self.send_wol_btn)

        fmt_label = QLabel("格式: AA:BB:CC:DD:EE:FF\n广播默认 255.255.255.255")
        fmt_label.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 10px;")
        right.addWidget(fmt_label)
        right.addStretch()

        body.addLayout(left, 2)
        body.addLayout(right, 1)
        layout.addLayout(body)

        # 底部：操作日志
        log_title = QLabel("📝 操作日志")
        log_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        layout.addWidget(log_title)
        self.wol_log = QTextEdit()
        self.wol_log.setReadOnly(True)
        self.wol_log.setMaximumHeight(120)
        self.wol_log.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, "Microsoft YaHei";
                font-size: 11px;
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.wol_log)

        return widget

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
        """
        开始扫描（主线程）。
        先解析网段、初始化 UI，再启动后台线程。
        """
        if self.is_running:
            return

        # 解析网段并计算总IP数（主线程完成，避免后台线程操作UI）
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
        self.found_hosts = []
        self.result_text.clear()
        self.progress_bar.setValue(0)
        self._update_stat(self.stat_total, str(total))
        self._update_stat(self.stat_scanned, "0")
        self._update_stat(self.stat_active, "0")
        self._update_stat(self.stat_progress, "0%")

        self.thread = threading.Thread(target=self.run_scan, args=(hosts, total))
        self.thread.start()

    def stop_scan(self):
        self.is_running = False
        self.worker.is_running = False
        self.worker.emit_status("正在停止扫描...")

    def update_status(self, text):
        """主线程槽函数：追加状态文本"""
        if hasattr(self, 'result_text'):
            self.result_text.append(f"<span style='color:#888'>{text}</span>")

    def update_progress(self, value):
        """主线程槽函数：更新进度条"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)
        self._update_stat(self.stat_progress, f"{value}%")

    def on_scan_progress(self, completed, total):
        """主线程槽函数：更新已扫描计数"""
        self._update_stat(self.stat_scanned, str(completed))

    def add_result(self, data):
        """主线程槽函数：插入扫描结果"""
        if not hasattr(self, 'result_text'):
            return
        ip = data.get("ip", "")
        mac = data.get("mac") or "-"
        hostname = data.get("hostname") or "未知"
        latency = data.get("latency")
        vendor = data.get("vendor") or "未知"
        role = data.get("role", "主机")

        latency_str = f"{latency}ms" if latency else "-"
        line = (
            f"<span style='color:#4ec9b0'>[✓ 存活]</span> "
            f"<span style='color:#d4d4d4'>IP: {ip}</span> "
            f"<span style='color:#888'>| 响应: {latency_str}</span> "
            f"<span style='color:#d4d4d4'>| 主机名: {hostname}</span> "
            f"<span style='color:#888'>| MAC: {mac}</span> "
            f"<span style='color:#888'>| 厂商: {vendor}</span> "
            f"<span style='color:#888'>| 角色: {role}</span>"
        )
        self.result_text.append(line)
        self._update_stat(self.stat_active, str(len(self.found_hosts)))

    def export_results(self):
        """导出扫描结果到文本文件"""
        if not self.found_hosts:
            QMessageBox.information(self, "提示", "暂无扫描结果可导出")
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "保存扫描结果",
            f"host_discovery_{self.subnet_input.text().strip().replace('/', '_')}.txt",
            "文本文件 (*.txt);;CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                if path.endswith(".csv"):
                    f.write("IP,MAC,主机名,厂商,响应时间(ms)\n")
                    for h in self.found_hosts:
                        f.write(f"{h.get('ip','')},{h.get('mac','')},{h.get('hostname','')},{h.get('vendor','')},{h.get('latency','')}\n")
                else:
                    f.write(f"主机发现扫描结果 - {self.subnet_input.text().strip()}\n")
                    f.write("=" * 80 + "\n")
                    f.write(f"{'IP':<16} {'MAC':<20} {'主机名':<25} {'厂商':<20} {'响应':<8}\n")
                    f.write("-" * 80 + "\n")
                    for h in self.found_hosts:
                        f.write(f"{h.get('ip',''):<16} {(h.get('mac') or '-'):<20} {h.get('hostname','未知'):<25} {h.get('vendor','未知'):<20} {h.get('latency','-')}ms\n".replace("-    ms", "-     "))
            QMessageBox.information(self, "成功", f"已导出到: {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def run_scan(self, hosts, total):
        """
        后台线程：执行主机扫描。

        注意：
        - 所有 UI 更新必须通过 Worker 的 Signal 发送到主线程
        - 禁止在此方法中直接访问任何 QWidget（如 _update_stat、progress_bar 等）
        """
        timeout = self.timeout_spin.value()
        threads = self.threads_spin.value()

        self.worker.emit_status("=" * 80)
        self.worker.emit_status("主机发现扫描开始")
        self.worker.emit_status(f"扫描网络: {self.subnet_input.text().strip()}  (共 {total} 个 IP)")
        self.worker.emit_status("=" * 80)

        mode = "ping" if self.mode_ping.isChecked() else ("tcp" if self.mode_tcp.isChecked() else "mix")
        completed = 0
        active = 0

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(self._scan_one, host, timeout, mode): host
                for host in hosts
            }
            for future in as_completed(futures):
                if not self.is_running:
                    break
                completed += 1
                progress = int((completed / total) * 100)
                self.worker.emit_progress(progress)
                self.worker.emit_scan_progress(completed, total)
                try:
                    data = future.result()
                    if data:
                        self.found_hosts.append(data)
                        active += 1
                        self.worker.emit_result(data)
                except Exception:
                    pass

        if self.is_running:
            self.worker.emit_status("=" * 80)
            self.worker.emit_status(f"✅ 扫描完成, 发现 {active} 台在线主机, 共扫描 {completed} 个 IP")
            self.worker.emit_progress(100)
        else:
            self.worker.emit_status(f"⏹ 扫描已停止, 已扫 {completed} / 在线 {active}")

        self.worker.emit_finished()

    def _scan_one(self, host, timeout, mode):
        """
        单个主机探测，返回 dict 或 None。
        mode: ping / tcp / mix
        """
        latency = None
        ok = False
        try:
            if mode == "ping":
                ok, latency = self._probe_ping(host, timeout)
            elif mode == "tcp":
                ok, latency = self._probe_tcp(host, timeout)
            else:  # mix
                ok, latency = self._probe_ping(host, timeout)
                if not ok:
                    ok2, lat2 = self._probe_tcp(host, timeout)
                    if ok2:
                        ok, latency = True, lat2
        except Exception:
            return None
        if not ok:
            return None
        # 在线主机：补全 MAC、主机名、厂商
        mac = parse_mac_address(host)
        hostname = resolve_hostname(host)
        vendor = lookup_vendor(mac) if mac else "未知"
        role = self._infer_role(host, mac, vendor)
        return {
            "ip": host,
            "mac": mac,
            "hostname": hostname,
            "vendor": vendor,
            "latency": int(latency) if latency else None,
            "role": role
        }

    def _probe_ping(self, host, timeout):
        """Ping 探测"""
        try:
            result = subprocess.run(
                f"ping -n 1 -w {timeout * 1000} {host}",
                capture_output=True, text=True, timeout=timeout + 2, creationflags=subprocess.CREATE_NO_WINDOW
            )
            m = re.search(r'(?:时间|time)\s*[<=]?\s*(\d+)\s*ms', result.stdout, re.IGNORECASE)
            if m:
                return True, int(m.group(1))
        except Exception:
            pass
        return False, None

    def _probe_tcp(self, host, timeout):
        """TCP 探测：尝试连接常见端口（80/443/22/3389/8080）"""
        common_ports = [80, 443, 22, 3389, 8080]
        for port in common_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                start = time.time()
                sock.connect((host, port))
                latency = (time.time() - start) * 1000
                sock.close()
                return True, latency
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
        return False, None

    def _infer_role(self, ip, mac, vendor):
        """推断主机角色：网关 / 网络设备 / 主机"""
        # 网关通常为 .1
        if ip.endswith(".1"):
            return "网关"
        # 常见网络设备厂商
        net_vendors = {"TP-LINK", "Huawei", "H3C", "Ruijie", "Cisco", "HPE", "D-Link", "MERCURY", "Netgear"}
        if vendor in net_vendors:
            return "网络设备"
        return "主机"

    # ============================================================
    #  远程唤醒 (WOL) 功能
    # ============================================================
    def _refresh_wol_list(self):
        """把扫描结果填充到 WOL 表格"""
        if not hasattr(self, 'wol_table'):
            return
        self.wol_table.setRowCount(0)
        for host in self.found_hosts:
            row = self.wol_table.rowCount()
            self.wol_table.insertRow(row)
            self.wol_table.setItem(row, 0, QTableWidgetItem(host.get("ip", "")))
            self.wol_table.setItem(row, 1, QTableWidgetItem(host.get("mac") or "-"))
            self.wol_table.setItem(row, 2, QTableWidgetItem(host.get("hostname") or "未知"))
            self.wol_table.setItem(row, 3, QTableWidgetItem(host.get("vendor") or "未知"))

    def _on_wol_row_selected(self):
        """表格选中行时把 MAC 自动填入手动输入框"""
        row = self.wol_table.currentRow()
        if row < 0:
            return
        mac_item = self.wol_table.item(row, 1)
        if mac_item and mac_item.text() != "-":
            self.mac_input.setText(mac_item.text())

    def _wake_selected(self):
        """唤醒表格中选中的主机"""
        row = self.wol_table.currentRow()
        if row < 0:
            self._wol_log("⚠ 请先在表格中选择一台主机")
            return
        mac = self.wol_table.item(row, 1).text()
        ip = self.wol_table.item(row, 0).text()
        if mac == "-":
            self._wol_log(f"⚠ 主机 {ip} 缺少 MAC 地址, 无法唤醒")
            return
        self._do_wake(mac, broadcast="255.255.255.255", note=f"选中主机 {ip}")

    def _send_wol_manual(self):
        """手动输入 MAC 发送"""
        mac = self.mac_input.text().strip()
        bcast = self.broadcast_input.text().strip() or "255.255.255.255"
        if not mac:
            self._wol_log("⚠ 请输入 MAC 地址")
            return
        self._do_wake(mac, bcast, note="手动输入")

    def _do_wake(self, mac, broadcast, note=""):
        """实际发送 WOL 魔术包"""
        if not self._validate_mac(mac):
            self._wol_log(f"❌ MAC 格式错误: {mac} (应为 AA:BB:CC:DD:EE:FF)")
            return
        self._wol_log(f"⚡ 发送唤醒包: {mac} → {broadcast} ({note})")
        try:
            mac_clean = mac.replace(":", "").replace("-", "").upper()
            # 构造魔术包：6 字节 0xFF + MAC 重复 16 次
            magic = b"\xff" * 6 + bytes.fromhex(mac_clean) * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast, 9))
            sock.close()
            self._wol_log(f"✅ 唤醒包已发送至 {mac} (广播 {broadcast})")
        except PermissionError:
            self._wol_log(f"❌ 权限不足: WOL 需要管理员权限，请以管理员身份运行")
        except Exception as e:
            self._wol_log(f"❌ 发送失败: {e}")

    def _validate_mac(self, mac):
        return bool(re.match(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$", mac))

    def _wol_log(self, text):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.wol_log.append(f"<span style='color:#888'>[{ts}]</span> {text}")

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
        return """
            QSpinBox {
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
                min-height: 20px;
                min-width: 80px;
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
