import threading
import time
from datetime import datetime
from collections import defaultdict
from scapy.all import sniff, get_if_list, conf, get_if_addr

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QMessageBox, QFrame, QScrollArea, QHeaderView, QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush

from app.core.logger import Logger


PROTOCOL_COLORS = {
    'TCP': QColor("#3498db"),
    'UDP': QColor("#9b59b6"),
    'DNS': QColor("#f39c12"),
    'DHCP': QColor("#1abc9c"),
    'HTTP': QColor("#e67e22"),
    'HTTPS': QColor("#16a085"),
    'QUIC': QColor("#1abc9c"),
    'Ping': QColor("#e74c3c"),
    'ARP': QColor("#2ecc71"),
    'IPv6': QColor("#7f8c8d"),
    'ICMPv6': QColor("#d35400"),
    'SSL/TLS': QColor("#27ae60"),
    'SSH': QColor("#8e44ad"),
    'FTP': QColor("#c0392b"),
    'SMTP': QColor("#d35400"),
    'Other': QColor("#95a5a6"),
    'Unknown': QColor("#95a5a6"),
    'Error': QColor("#c0392b"),
    'IP(1)': QColor("#34495e"),
    'IP(6)': QColor("#3498db"),
    'IP(17)': QColor("#9b59b6"),
}


def get_row_color(protocol):
    """根据协议返回整行背景的淡色版本。"""
    base = PROTOCOL_COLORS.get(protocol, QColor("#95a5a6"))
    light = QColor(base)
    light.setAlpha(40)
    return light


class ProtocolBarWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.bars = []

    def update_data(self, protocols, total_packets):
        for bar in self.bars:
            bar.deleteLater()
        self.bars.clear()

        if not protocols or total_packets == 0:
            label = QLabel("暂无数据")
            label.setStyleSheet("font-size: 12px; color: #999;")
            label.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(label)
            self.bars.append(label)
            return

        sorted_protocols = sorted(protocols.items(), key=lambda x: x[1], reverse=True)[:6]

        for proto, count in sorted_protocols:
            percent = (count / total_packets) * 100
            color = PROTOCOL_COLORS.get(proto, QColor("#95a5a6"))

            bar_frame = QFrame()
            bar_frame.setFixedHeight(24)
            bar_layout = QHBoxLayout(bar_frame)
            bar_layout.setSpacing(6)
            bar_layout.setContentsMargins(0, 0, 0, 0)

            color_dot = QFrame()
            color_dot.setFixedSize(12, 12)
            color_dot.setStyleSheet(f"background-color: {color.name()}; border-radius: 6px;")
            bar_layout.addWidget(color_dot)

            name_label = QLabel(proto)
            name_label.setFixedWidth(50)
            name_label.setStyleSheet("font-size: 12px; color: #333;")
            bar_layout.addWidget(name_label)

            bar_widget = QProgressBar()
            bar_widget.setRange(0, 100)
            bar_widget.setValue(int(percent))
            bar_widget.setTextVisible(False)
            bar_widget.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    border-radius: 4px;
                    background-color: #eee;
                    height: 16px;
                }}
                QProgressBar::chunk {{
                    background-color: {color.name()};
                    border-radius: 4px;
                }}
            """)
            bar_layout.addWidget(bar_widget, 1)

            count_label = QLabel(f"{count}")
            count_label.setFixedWidth(30)
            count_label.setStyleSheet("font-size: 12px; color: #666;")
            count_label.setAlignment(Qt.AlignRight)
            bar_layout.addWidget(count_label)

            percent_label = QLabel(f"{percent:.1f}%")
            percent_label.setFixedWidth(45)
            percent_label.setStyleSheet("font-size: 12px; color: #333; font-weight: bold;")
            percent_label.setAlignment(Qt.AlignRight)
            bar_layout.addWidget(percent_label)

            self.layout.addWidget(bar_frame)
            self.bars.append(bar_frame)


class ProtocolWorker(QObject):
    record_signal = Signal(dict)
    stat_signal = Signal(dict)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.interface = None
        self.records = []
        self.conn_stats = defaultdict(lambda: {'packets': 0, 'bytes': 0})
        self.protocol_counts = defaultdict(int)

    def start_analysis(self, interface):
        self.interface = interface
        self.is_running = True
        self.records = []
        self.conn_stats.clear()
        self.protocol_counts.clear()

        self.thread = threading.Thread(target=self._run_analysis)
        self.thread.start()

    def _run_analysis(self):
        try:
            while self.is_running:
                sniff(
                    iface=self.interface,
                    prn=self._process_packet,
                    store=False,
                    timeout=1
                )
        except Exception as e:
            Logger().error(f"协议分析抓包异常: {e}")
            self.record_signal.emit({
                'time': datetime.now().strftime('%H:%M:%S'),
                'source': 'ERROR',
                'dest': '-',
                'type': 'Error',
                'size': 0,
                'summary': str(e)
            })
        finally:
            self.is_running = False
            self.finished_signal.emit()

    def _process_packet(self, packet):
        if not self.is_running:
            return

        timestamp = datetime.now().strftime('%H:%M:%S')
        src_ip = dst_ip = "-"
        src_port = dst_port = "-"
        proto_type = "Unknown"
        size = len(packet)
        summary = ""

        if packet.haslayer('IP'):
            src_ip = packet['IP'].src
            dst_ip = packet['IP'].dst

            if packet.haslayer('TCP'):
                src_port = packet['TCP'].sport
                dst_port = packet['TCP'].dport
                flags = []
                if packet['TCP'].flags.S: flags.append('SYN')
                if packet['TCP'].flags.A: flags.append('ACK')
                if packet['TCP'].flags.F: flags.append('FIN')
                if packet['TCP'].flags.R: flags.append('RST')
                if packet['TCP'].flags.P: flags.append('PSH')
                flag_str = ','.join(flags) if flags else '-'

                proto_type, summary = self._classify_tcp(src_port, dst_port, flag_str)
            elif packet.haslayer('UDP'):
                src_port = packet['UDP'].sport
                dst_port = packet['UDP'].dport
                proto_type, summary = self._classify_udp(src_port, dst_port)
            elif packet.haslayer('ICMP'):
                proto_type = "Ping"
                summary = f"ICMP {packet['ICMP'].type}"
            else:
                proto_type = f"IP({packet['IP'].proto})"
                summary = "IP数据包"

        elif packet.haslayer('ARP'):
            proto_type = "ARP"
            src_ip = packet['ARP'].psrc
            dst_ip = packet['ARP'].pdst
            if packet['ARP'].op == 1:
                summary = f"查询: {packet['ARP'].pdst} 的 MAC 是谁? (来自 {packet['ARP'].psrc})"
            else:
                summary = f"响应: {packet['ARP'].psrc} 的 MAC 是 {packet['ARP'].hwsrc}"

        elif packet.haslayer('IPv6'):
            proto_type = "IPv6"
            src_ip = packet['IPv6'].src
            dst_ip = packet['IPv6'].dst
            if packet.haslayer('ICMPv6'):
                proto_type = "ICMPv6"
                summary = f"ICMPv6 {packet['ICMPv6'].type}"
            else:
                summary = "IPv6数据包"

        conn_key = f"{src_ip}:{src_port} -> {dst_ip}:{dst_port} [{proto_type}]"
        self.conn_stats[conn_key]['packets'] += 1
        self.conn_stats[conn_key]['bytes'] += size
        self.protocol_counts[proto_type] += 1

        if len(self.records) >= 600:
            self.records.pop(0)
        self.records.append({
            'time': timestamp,
            'source': f"{src_ip}:{src_port}",
            'dest': f"{dst_ip}:{dst_port}",
            'type': proto_type,
            'size': size,
            'summary': summary
        })

        self.record_signal.emit({
            'time': timestamp,
            'source': f"{src_ip}:{src_port}",
            'dest': f"{dst_ip}:{dst_port}",
            'type': proto_type,
            'size': size,
            'summary': summary
        })

        top_conns = sorted(self.conn_stats.items(), key=lambda x: x[1]['bytes'], reverse=True)[:10]
        self.stat_signal.emit({
            'protocols': dict(self.protocol_counts),
            'top_conns': top_conns,
            'total_packets': sum(self.protocol_counts.values())
        })

    def _classify_tcp(self, src_port, dst_port, flag_str):
        """根据端口号识别常见 TCP 应用层协议。"""
        if dst_port == 80 or src_port == 80:
            return "HTTP", f"HTTP网页 {flag_str}"
        if dst_port == 443 or src_port == 443:
            return "HTTPS", f"HTTPS网页 {flag_str}"
        if dst_port == 22 or src_port == 22:
            return "SSH", f"SSH远程登录 {flag_str}"
        if dst_port == 21 or src_port == 21:
            return "FTP", f"FTP控制 {flag_str}"
        if dst_port == 25 or src_port == 25:
            return "SMTP", f"SMTP邮件 {flag_str}"
        if dst_port == 23 or src_port == 23:
            return "Other", f"Telnet {flag_str}"
        if dst_port == 3389 or src_port == 3389:
            return "Other", f"RDP远程桌面 {flag_str}"
        if dst_port == 3306 or src_port == 3306:
            return "Other", f"MySQL {flag_str}"
        if dst_port == 445 or src_port == 445:
            return "Other", f"SMB {flag_str}"
        return "TCP", f"TCP {flag_str}"

    def _classify_udp(self, src_port, dst_port):
        """根据端口号识别常见 UDP 应用层协议。"""
        if dst_port == 53 or src_port == 53:
            return "DNS", "DNS查询/响应"
        if dst_port in [67, 68] or src_port in [67, 68]:
            return "DHCP", "DHCP请求/响应"
        if dst_port == 443 or src_port == 443:
            return "QUIC", "QUIC数据传输"
        if dst_port == 123 or src_port == 123:
            return "Other", "NTP时间同步"
        if dst_port == 161 or src_port == 161:
            return "Other", "SNMP网络管理"
        if dst_port == 5353 or src_port == 5353:
            return "Other", "mDNS组播"
        return "UDP", "UDP数据传输"

    def stop_analysis(self):
        self.is_running = False
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=2)


class ProtocolAnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._iface_map = {}
        self.worker = ProtocolWorker()
        self.worker.record_signal.connect(self.on_record)
        self.worker.stat_signal.connect(self.on_stat_update)
        self.worker.finished_signal.connect(self.on_finished)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self._build_toolbar(main_layout)
        self._build_record_table(main_layout)
        self._build_bottom_area(main_layout)

    def _build_toolbar(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; background: #fafafa; }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("网卡:"))
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(200)
        self._refresh_interfaces()
        layout.addWidget(self.iface_combo)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_interfaces)
        layout.addWidget(refresh_btn)

        self.start_btn = QPushButton("开始抓包")
        self.start_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 6px 16px; border-radius: 3px;")
        self.start_btn.clicked.connect(self.start_analysis)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; padding: 6px 16px; border-radius: 3px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_analysis)
        layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 6px 16px; border-radius: 3px;")
        self.clear_btn.clicked.connect(self.clear_results)
        layout.addWidget(self.clear_btn)

        status_label = QLabel("就绪 | 需要 scapy + npcap")
        status_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addStretch()
        layout.addWidget(status_label)

        parent_layout.addWidget(frame)

    def _build_record_table(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title_layout = QHBoxLayout()
        title = QLabel("实时通信记录")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        title_layout.addWidget(title)
        title_layout.addStretch()

        legend_html = (
            '<span style="color:#555;font-size:11px;">说明: 实时捕获本机进出流量, '
            '展示通信内容、协议类型和占比, </span>'
            '<span style="color:#888;font-size:11px;">'
            '<span style="color:#3498db;">■=TCP传输</span> '
            '<span style="color:#9b59b6;">■=UDP传输</span> '
            '<span style="color:#f39c12;">■=DNS</span> '
            '<span style="color:#1abc9c;">■=HTTP/HTTPS/QUIC</span> '
            '<span style="color:#e74c3c;">■=Ping</span> '
            '<span style="color:#2ecc71;">■=ARP</span>'
            '</span>'
        )
        legend = QLabel(legend_html)
        legend.setStyleSheet("font-size: 11px;")
        title_layout.addWidget(legend)
        layout.addLayout(title_layout)

        self.record_table = QTableWidget()
        self.record_table.setColumnCount(7)
        self.record_table.setHorizontalHeaderLabels(["#", "时间", "来源", "去往", "类型", "大小(B)", "内容摘要"])
        self.record_table.setAlternatingRowColors(False)
        self.record_table.setShowGrid(True)
        self.record_table.setStyleSheet("""
            QTableWidget {
                font-size: 11px;
                gridline-color: #e8e8e8;
                background-color: white;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                font-size: 11px;
                border: 1px solid #e0e0e0;
            }
        """)

        header = self.record_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)

        layout.addWidget(self.record_table, 1)
        parent_layout.addWidget(frame, 1)

    def _build_bottom_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_title = QLabel("流量类型占比")
        left_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        left_layout.addWidget(left_title)

        self.protocol_bar_widget = ProtocolBarWidget()
        left_layout.addWidget(self.protocol_bar_widget)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(6)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_title = QLabel("占用流量最多的连接")
        right_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        right_layout.addWidget(right_title)

        self.conn_table = QTableWidget()
        self.conn_table.setColumnCount(5)
        self.conn_table.setHorizontalHeaderLabels(["来源", "目标", "类型", "包数", "流量"])
        self.conn_table.setStyleSheet("""
            QTableWidget { font-size: 11px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 4px; font-size: 10px; }
        """)

        conn_header = self.conn_table.horizontalHeader()
        conn_header.setSectionResizeMode(0, QHeaderView.Stretch)
        conn_header.setSectionResizeMode(1, QHeaderView.Stretch)
        conn_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        conn_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        conn_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        right_layout.addWidget(self.conn_table)

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_panel, 1)

        parent_layout.addWidget(frame)

    def _refresh_interfaces(self):
        self.iface_combo.clear()
        self._iface_map = {}
        try:
            import psutil
            psutil_names = list(psutil.net_if_addrs().keys())

            if hasattr(conf, 'ifaces') and conf.ifaces:
                for dev in conf.ifaces.values():
                    scapy_name = dev.name
                    desc = getattr(dev, 'description', scapy_name)
                    matched = False
                    for psutil_name in psutil_names:
                        if psutil_name.lower() in desc.lower():
                            self._iface_map[psutil_name] = scapy_name
                            matched = True
                            break
                    if not matched:
                        if desc not in self._iface_map:
                            self._iface_map[desc] = scapy_name
            else:
                for iface in get_if_list():
                    self._iface_map[iface] = iface

            for friendly_name, scapy_name in self._iface_map.items():
                self.iface_combo.addItem(friendly_name, scapy_name)

            if self._iface_map:
                self.iface_combo.addItem("全部", None)
        except Exception as e:
            Logger().error(f"获取网卡列表失败: {e}")
            QMessageBox.warning(self, "警告", f"获取网卡列表失败: {str(e)}")

    def start_analysis(self):
        interface = self.iface_combo.currentData()
        if interface is None and self.iface_combo.currentText() != "全部":
            QMessageBox.warning(self, "提示", "请选择网卡")
            return

        self.worker.start_analysis(interface)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.record_table.setRowCount(0)
        self.conn_table.setRowCount(0)
        self.protocol_bar_widget.update_data({}, 0)

    def stop_analysis(self):
        self.worker.stop_analysis()
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(True)

    def on_record(self, record):
        row = self.record_table.rowCount()
        if row >= 600:
            self.record_table.removeRow(0)
            row -= 1

        self.record_table.insertRow(row)
        row_color = get_row_color(record['type'])

        num_item = QTableWidgetItem(str(row + 1))
        num_item.setBackground(row_color)
        self.record_table.setItem(row, 0, num_item)

        time_item = QTableWidgetItem(record['time'])
        time_item.setBackground(row_color)
        self.record_table.setItem(row, 1, time_item)

        src_item = QTableWidgetItem(record['source'])
        src_item.setBackground(row_color)
        self.record_table.setItem(row, 2, src_item)

        dst_item = QTableWidgetItem(record['dest'])
        dst_item.setBackground(row_color)
        self.record_table.setItem(row, 3, dst_item)

        type_item = QTableWidgetItem(record['type'])
        type_item.setBackground(row_color)
        type_item.setForeground(PROTOCOL_COLORS.get(record['type'], QColor("#333")))
        self.record_table.setItem(row, 4, type_item)

        size_item = QTableWidgetItem(str(record['size']))
        size_item.setBackground(row_color)
        size_item.setTextAlignment(Qt.AlignRight)
        self.record_table.setItem(row, 5, size_item)

        summary_item = QTableWidgetItem(record['summary'])
        summary_item.setBackground(row_color)
        self.record_table.setItem(row, 6, summary_item)

        self.record_table.scrollToBottom()

    def on_stat_update(self, stats):
        self.protocol_bar_widget.update_data(stats['protocols'], stats['total_packets'])

        self.conn_table.setRowCount(0)
        for conn_key, conn_stat in stats['top_conns']:
            parts = conn_key.split(' -> ')
            src = parts[0]
            dst_proto = parts[1].rsplit(' [', 1)
            dst = dst_proto[0]
            proto = dst_proto[1][:-1] if len(dst_proto) > 1 else ""

            row = self.conn_table.rowCount()
            self.conn_table.insertRow(row)
            self.conn_table.setItem(row, 0, QTableWidgetItem(src))
            self.conn_table.setItem(row, 1, QTableWidgetItem(dst))

            proto_item = QTableWidgetItem(proto)
            proto_item.setForeground(PROTOCOL_COLORS.get(proto, QColor("#333")))
            self.conn_table.setItem(row, 2, proto_item)

            packets_item = QTableWidgetItem(str(conn_stat['packets']))
            packets_item.setTextAlignment(Qt.AlignRight)
            self.conn_table.setItem(row, 3, packets_item)

            self.conn_table.setItem(row, 4, QTableWidgetItem(self._format_bytes(conn_stat['bytes'])))

    def _format_bytes(self, byte_count):
        if byte_count < 1024:
            return f"{byte_count} B"
        elif byte_count < 1024 * 1024:
            return f"{byte_count / 1024:.1f} KB"
        else:
            return f"{byte_count / (1024 * 1024):.1f} MB"

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def clear_results(self):
        self.record_table.setRowCount(0)
        self.conn_table.setRowCount(0)
        self.protocol_bar_widget.update_data({}, 0)
        self.worker.records = []
        self.worker.conn_stats.clear()
        self.worker.protocol_counts.clear()

    def stop_all(self):
        self.worker.stop_analysis()

    def cleanup(self):
        self.stop_all()
        try:
            self.worker.record_signal.disconnect(self.on_record)
            self.worker.stat_signal.disconnect(self.on_stat_update)
            self.worker.finished_signal.disconnect(self.on_finished)
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
