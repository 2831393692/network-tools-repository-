import psutil
import time
import socket
import platform
import subprocess
import re
from datetime import datetime
from collections import deque
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QTextEdit, QSizePolicy,
    QPushButton
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False


class MiniChart(QWidget):
    def __init__(self, color="#3498db", max_points=60, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.data = deque([0] * max_points, maxlen=max_points)
        self.max_value = 100
        self.setMinimumHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    
    def add_value(self, value):
        self.data.append(value)
        if value > self.max_value * 0.8:
            self.max_value = max(self.max_value, value * 1.2)
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        if len(self.data) < 2:
            return
        
        margin = 2
        chart_w = w - 2 * margin
        chart_h = h - 2 * margin
        
        if self.max_value <= 0:
            self.max_value = 1
        
        points = []
        step = chart_w / (len(self.data) - 1) if len(self.data) > 1 else 0
        for i, value in enumerate(self.data):
            x = margin + i * step
            y = margin + chart_h - (value / self.max_value) * chart_h
            points.append((x, y))
        
        pen = QPen(self.color, 2)
        painter.setPen(pen)
        for i in range(len(points) - 1):
            painter.drawLine(
                int(points[i][0]), int(points[i][1]),
                int(points[i+1][0]), int(points[i+1][1])
            )


class StatCard(QFrame):
    def __init__(self, title, value_color, parent=None):
        super().__init__(parent)
        self.value_color = value_color
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #f5f7fa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        
        title_layout = QHBoxLayout()
        title_layout.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #555; font-size: 12px; font-weight: bold; border: none;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(f"color: {value_color}; font-size: 28px; font-weight: bold; border: none;")
        self.value_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.value_label)
        
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #888; font-size: 11px; border: none;")
        self.detail_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.detail_label)
        
        self.chart = MiniChart(value_color)
        layout.addWidget(self.chart)
    
    def update_value(self, value, unit="%", detail=""):
        self.value_label.setText(f"{value}{unit}")
        if detail:
            self.detail_label.setText(detail)
        self.chart.add_value(value)
    
    def update_custom(self, html_value, detail=""):
        self.value_label.setText(html_value)
        if detail:
            self.detail_label.setText(detail)


class ConnectionCheckWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #f5f7fa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(15)
        
        title = QLabel("⚡ 连通性:")
        title.setStyleSheet("color: #555; font-size: 12px; font-weight: bold; border: none;")
        layout.addWidget(title)
        
        self.gateway_label = QLabel("网关: 检测中...")
        self.gateway_label.setStyleSheet("color: #555; font-size: 12px; border: none;")
        layout.addWidget(self.gateway_label)
        
        self.dns_label = QLabel("DNS: 检测中...")
        self.dns_label.setStyleSheet("color: #555; font-size: 12px; border: none;")
        layout.addWidget(self.dns_label)
        
        self.internet_label = QLabel("互联网: 检测中...")
        self.internet_label.setStyleSheet("color: #555; font-size: 12px; border: none;")
        layout.addWidget(self.internet_label)
        
        layout.addStretch()
    
    def update_status(self, gateway, dns, internet):
        self.gateway_label.setText(f"网关: {gateway}")
        self.dns_label.setText(f"DNS: {dns}")
        self.internet_label.setText(f"互联网: {internet}")


class QuickActionButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.setCursor(Qt.PointingHandCursor)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.boot_time = psutil.boot_time()
        self.last_network_stats = psutil.net_io_counters()
        self.last_update_time = time.time()
        self.tick_count = 0
        self.gateway = self.get_gateway()
        self.dns_server = "223.5.5.5"
        self.system_logs = deque(maxlen=100)
        self.init_ui()
        self.add_log("系统就绪，工具已启动")
        self.start_update_timer()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        self.create_header(layout)
        
        first_row = QHBoxLayout()
        first_row.setSpacing(8)
        self.cpu_card = StatCard("⚡ CPU 使用率", "#1976d2")
        self.memory_card = StatCard("🧠 内存占用", "#2ecc71")
        self.disk_card = StatCard("💾 磁盘占用", "#e74c3c")
        first_row.addWidget(self.cpu_card)
        first_row.addWidget(self.memory_card)
        first_row.addWidget(self.disk_card)
        layout.addLayout(first_row)
        
        second_row = QHBoxLayout()
        second_row.setSpacing(8)
        self.network_card = StatCard("📡 网络吞吐", "#9b59b6")
        self.uptime_card = StatCard("⏱ 系统运行时长", "#16a085")
        self.process_card = StatCard("📋 进程数量", "#34495e")
        second_row.addWidget(self.network_card)
        second_row.addWidget(self.uptime_card)
        second_row.addWidget(self.process_card)
        layout.addLayout(second_row)
        
        self.connection_widget = ConnectionCheckWidget()
        layout.addWidget(self.connection_widget)
        
        content_row = QHBoxLayout()
        content_row.setSpacing(8)
        
        log_frame = self.create_log_panel()
        content_row.addWidget(log_frame, 1)
        
        desc_frame = self.create_description_panel()
        content_row.addWidget(desc_frame, 1)
        
        layout.addLayout(content_row, 1)
        
        self.create_quick_actions(layout)
    
    def create_header(self, parent_layout):
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #ecf0f1;
                border: none;
                border-radius: 4px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 8, 15, 8)
        
        title = QLabel("🖥 网络状态总览")
        title.setStyleSheet("color: #2c3e50; font-size: 16px; font-weight: bold; background: transparent;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        info_layout = QHBoxLayout()
        info_layout.setSpacing(15)
        
        self.refresh_label = QLabel("最后刷新: --:--:--")
        self.refresh_label.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")
        info_layout.addWidget(self.refresh_label)
        
        hostname_label = QLabel(f"💻 {socket.gethostname()}")
        hostname_label.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")
        info_layout.addWidget(hostname_label)
        
        ip_address = self.get_ip_address()
        ip_label = QLabel(f"🌐 {ip_address}")
        ip_label.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")
        info_info = QHBoxLayout()
        info_info.addWidget(ip_label)
        info_layout.addLayout(info_info)
        
        header_layout.addLayout(info_layout)
        parent_layout.addWidget(header)
    
    def create_log_panel(self):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #fefefe;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        
        title = QLabel("📋 系统网络事件日志")
        title.setStyleSheet("color: #2c3e50; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(title)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #fefefe;
                border: 1px solid #e8e8e8;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 11px;
                color: #2c3e50;
            }
        """)
        layout.addWidget(self.log_text)
        
        return frame
    
    def create_description_panel(self):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #fffde7;
                border: 1px solid #fff9c4;
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        
        title = QLabel("🛠 工具使用说明")
        title.setStyleSheet("color: #2c3e50; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(title)
        
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setStyleSheet("""
            QTextEdit {
                background-color: #fffde7;
                border: 1px solid #fff9c4;
                border-radius: 3px;
                font-family: 'Microsoft YaHei';
                font-size: 11px;
                color: #555;
            }
        """)
        self.desc_text.setHtml("""
        <div style="padding: 5px;">
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">⚡ Ping 测试</span><br>
            <span style="color: #777; font-size: 10px;">向目标发送 ICMP 包，测量延迟与丢包率。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">🛣 路由追踪</span><br>
            <span style="color: #777; font-size: 10px;">逐跳显示数据包经过的路由节点及延迟。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">🔢 子网计算</span><br>
            <span style="color: #777; font-size: 10px;">输入 IP/掩码，自动计算网段、广播、可用 IP 范围。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">🔍 端口扫描</span><br>
            <span style="color: #777; font-size: 10px;">扫描目标主机开放的 TCP/UDP 端口。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">🌐 IP 信息</span><br>
            <span style="color: #777; font-size: 10px;">查询 IP 的地理位置、ASN 及运营商信息。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">⚡ 网速测试</span><br>
            <span style="color: #777; font-size: 10px;">通过 Speedtest 测量上下行带宽与延迟。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">⚙ 其他工具</span><br>
            <span style="color: #777; font-size: 10px;">DNS 查询、Whois、MAC 厂商查询等实用工具。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">📷 摄像头扫描</span><br>
            <span style="color: #777; font-size: 10px;">扫描局域网内的 RTSP/ONVIF 摄像头设备。</span></p>
            
            <p style="margin: 3px 0;"><span style="color: #1976d2; font-weight: bold;">📡 WiFi 分析</span><br>
            <span style="color: #777; font-size: 10px;">查看周边无线网络信号强度与信道分布。</span></p>
        </div>
        """)
        layout.addWidget(self.desc_text)
        
        return frame
    
    def create_quick_actions(self, parent_layout):
        action_frame = QFrame()
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 5, 0, 0)
        action_layout.setSpacing(10)
        
        title = QLabel("快速启动:")
        title.setStyleSheet("color: #555; font-size: 12px; font-weight: bold;")
        action_layout.addWidget(title)
        
        ping_btn = QuickActionButton("⚡ Ping")
        ping_btn.clicked.connect(lambda: self.quick_navigate("ping"))
        action_layout.addWidget(ping_btn)
        
        route_btn = QuickActionButton("🛣 路由追踪")
        route_btn.clicked.connect(lambda: self.quick_navigate("traceroute"))
        action_layout.addWidget(route_btn)
        
        port_btn = QuickActionButton("🔍 端口扫描")
        port_btn.clicked.connect(lambda: self.quick_navigate("port_scan"))
        action_layout.addWidget(port_btn)
        
        ip_btn = QuickActionButton("🌐 IP信息")
        ip_btn.clicked.connect(lambda: self.quick_navigate("tools"))
        action_layout.addWidget(ip_btn)
        
        speed_btn = QuickActionButton("⚡ 网速测试")
        speed_btn.clicked.connect(lambda: self.quick_navigate("speed_external"))
        action_layout.addWidget(speed_btn)
        
        action_layout.addStretch()
        parent_layout.addWidget(action_frame)
    
    def quick_navigate(self, page_key):
        if self.main_window and hasattr(self.main_window, 'switch_page'):
            from app.ui.ping_test import PingTestPage
            from app.ui.traceroute import TraceroutePage
            from app.ui.port_scan import PortScanPage
            from app.ui.tools import ToolsPage
            from app.ui.placeholder import PlaceholderPage
            
            page_map = {
                "ping": (PingTestPage, "Ping测试"),
                "traceroute": (TraceroutePage, "路由追踪"),
                "port_scan": (PortScanPage, "端口扫描"),
                "tools": (ToolsPage, "实用工具"),
                "speed_external": (PlaceholderPage, "外网测速"),
            }
            
            if page_key in page_map:
                page_class, page_name = page_map[page_key]
                self.main_window.switch_page(page_key, page_class, page_name)
    
    def get_gateway(self):
        try:
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True, text=True, encoding="gbk", timeout=5
            )
            for line in result.stdout.split('\n'):
                if '0.0.0.0' in line:
                    parts = re.split(r'\s+', line.strip())
                    if len(parts) >= 3 and parts[2] not in ['0.0.0.0', 'On-link']:
                        return parts[2]
        except Exception:
            pass
        return "192.168.1.1"
    
    def get_ip_address(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def add_log(self, message):
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        self.system_logs.append(f"{timestamp} {message}")
        self.refresh_log_display()
    
    def refresh_log_display(self):
        html = "<br>".join(self.system_logs)
        self.log_text.setHtml(f'<div style="padding: 5px;">{html}</div>')
    
    def start_update_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.smart_update)
        self.timer.start(2000)
        self.smart_update()
    
    def stop_update_timer(self):
        if hasattr(self, 'timer') and self.timer:
            try:
                self.timer.stop()
                self.timer.timeout.disconnect(self.smart_update)
            except:
                pass
    
    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)
    
    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)
    
    def smart_update(self):
        try:
            self.update_cpu()
            self.update_memory()
            self.update_network()
            self.update_uptime()
            self.update_process_count()
            self.update_refresh_time()
            
            if self.tick_count % 3 == 0:
                self.update_disk()
            
            if self.tick_count % 5 == 0:
                self.check_connection()
            
            self.tick_count = getattr(self, 'tick_count', 0) + 1
        except Exception as e:
            print(f"Update error: {e}")
    
    def update_cpu(self):
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            freq = psutil.cpu_freq()
            freq_text = f"{freq.current/1000:.1f} GHz" if freq else ""
            self.cpu_card.update_value(cpu_percent, "%", f"{psutil.cpu_count()} 核  {freq_text}")
        except Exception:
            pass
    
    def update_memory(self):
        try:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            self.memory_card.update_value(mem.percent, "%", f"共 {total_gb:.1f} GB  已用 {used_gb:.1f} GB")
        except Exception:
            pass
    
    def update_disk(self):
        try:
            disk = psutil.disk_usage("C:\\" if psutil.WINDOWS else "/")
            used_gb = disk.used / (1024 ** 3)
            total_gb = disk.total / (1024 ** 3)
            self.disk_card.update_value(disk.percent, "%", f"共 {total_gb:.1f} GB  剩余 {total_gb-used_gb:.1f} GB")
        except Exception:
            pass
    
    def update_network(self):
        try:
            current_stats = psutil.net_io_counters()
            current_time = time.time()
            elapsed = current_time - self.last_update_time
            
            if elapsed > 0:
                upload = (current_stats.bytes_sent - self.last_network_stats.bytes_sent) / elapsed
                download = (current_stats.bytes_recv - self.last_network_stats.bytes_recv) / elapsed
                
                up_text = f"{upload/1024:.1f} KB/s" if upload < 1024*1024 else f"{upload/1024/1024:.2f} MB/s"
                down_text = f"{download/1024:.1f} B/s" if download < 1024 else f"{download/1024:.1f} KB/s"
                
                html = f'<span style="color: #3498db;">↓ {up_text}</span>  <span style="color: #e74c3c;">↑ {down_text}</span>'
                self.network_card.update_custom(html)
                self.network_card.chart.add_value((upload + download) / 1024 / 1024)
            
            self.last_network_stats = current_stats
            self.last_update_time = current_time
        except Exception:
            pass
    
    def update_uptime(self):
        try:
            uptime_seconds = time.time() - self.boot_time
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            
            if days > 0:
                text = f"{days}天{hours}小时{minutes}分钟"
            elif hours > 0:
                text = f"{hours}小时{minutes}分钟"
            else:
                text = f"{minutes}分钟"
            
            self.uptime_card.update_custom(f'<span style="font-size: 24px;">{text}</span>')
        except Exception:
            pass
    
    def update_process_count(self):
        try:
            count = len(psutil.pids())
            self.process_card.update_value(count, " 个", "")
        except Exception:
            pass
    
    def update_refresh_time(self):
        self.refresh_label.setText(f"最后刷新: {datetime.now().strftime('%H:%M:%S')}")
    
    def check_connection(self):
        try:
            gateway_latency = self.ping_host(self.gateway)
            dns_latency = self.ping_host(self.dns_server)
            internet_latency = self.ping_host("223.5.5.5")
            
            self.connection_widget.update_status(
                f"✅ {gateway_latency}ms" if gateway_latency else "❌ 超时",
                f"✅ {dns_latency}ms" if dns_latency else "❌ 超时",
                f"✅ {internet_latency}ms" if internet_latency else "❌ 超时"
            )
            
            timestamp = datetime.now().strftime("[%H:%M:%S]")
            if gateway_latency:
                self.add_log(f"网关 {self.gateway} 可达，延迟 {gateway_latency}ms")
            if internet_latency:
                self.add_log(f"互联网 阿里DNS(223.5.5.5) 可达，延迟 {internet_latency}ms")
        except Exception:
            pass
    
    def ping_host(self, host):
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", host],
                capture_output=True, text=True, timeout=2
            )
            match = re.search(r"时间[=<](\d+)ms", result.stdout)
            if match:
                return int(match.group(1))
            match = re.search(r"time[<=](\d+)ms", result.stdout, re.IGNORECASE)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return None
