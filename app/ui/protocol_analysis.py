import threading
import time
from datetime import datetime
from collections import defaultdict
from scapy.all import sniff, get_if_list, conf, get_if_addr

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QMessageBox, QFrame, QScrollArea, QHeaderView, QTextEdit
)
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor

from app.core.logger import Logger


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
                proto_type = "TCP"
                src_port = packet['TCP'].sport
                dst_port = packet['TCP'].dport
                flags = []
                if packet['TCP'].flags.S: flags.append('SYN')
                if packet['TCP'].flags.A: flags.append('ACK')
                if packet['TCP'].flags.F: flags.append('FIN')
                if packet['TCP'].flags.R: flags.append('RST')
                if packet['TCP'].flags.P: flags.append('PSH')
                summary = f"TCP {','.join(flags)}"
            elif packet.haslayer('UDP'):
                proto_type = "UDP"
                src_port = packet['UDP'].sport
                dst_port = packet['UDP'].dport
                if dst_port == 53 or src_port == 53:
                    proto_type = "DNS"
                    summary = "DNS查询/响应"
                elif dst_port in [67, 68] or src_port in [67, 68]:
                    proto_type = "DHCP"
                    summary = "DHCP请求/响应"
                else:
                    summary = "UDP数据"
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
                summary = "ARP请求"
            else:
                summary = "ARP响应"

        elif packet.haslayer('IPv6'):
            proto_type = "IPv6"
            src_ip = packet['IPv6'].src
            dst_ip = packet['IPv6'].dst
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

        title = QLabel("实时通信记录")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        layout.addWidget(title)

        self.record_table = QTableWidget()
        self.record_table.setColumnCount(7)
        self.record_table.setHorizontalHeaderLabels(["#", "时间", "来源", "去往", "类型", "大小(B)", "内容摘要"])
        self.record_table.setAlternatingRowColors(True)
        self.record_table.setStyleSheet("""
            QTableWidget { font-size: 11px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 4px; font-size: 11px; }
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

        self.pie_frame = QFrame()
        self.pie_frame.setStyleSheet("background-color: #fafafa; border-radius: 4px;")
        self.pie_frame.setMinimumHeight(120)
        self.pie_label = QLabel("开始抓包后\n这里显示流量分布")
        self.pie_label.setAlignment(Qt.AlignCenter)
        self.pie_label.setStyleSheet("font-size: 11px; color: #888;")
        pie_layout = QVBoxLayout(self.pie_frame)
        pie_layout.addWidget(self.pie_label)
        left_layout.addWidget(self.pie_frame)

        self.proto_stats = QTextEdit()
        self.proto_stats.setReadOnly(True)
        self.proto_stats.setMaximumHeight(80)
        self.proto_stats.setStyleSheet("font-size: 11px; font-family: Consolas;")
        left_layout.addWidget(self.proto_stats)

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
        self.proto_stats.clear()

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
        self.record_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.record_table.setItem(row, 1, QTableWidgetItem(record['time']))
        self.record_table.setItem(row, 2, QTableWidgetItem(record['source']))
        self.record_table.setItem(row, 3, QTableWidgetItem(record['dest']))

        type_item = QTableWidgetItem(record['type'])
        colors = {
            'TCP': QColor("#3498db"),
            'UDP': QColor("#9b59b6"),
            'DNS': QColor("#f39c12"),
            'DHCP': QColor("#1abc9c"),
            'Ping': QColor("#e74c3c"),
            'ARP': QColor("#2ecc71"),
            'IPv6': QColor("#7f8c8d")
        }
        type_item.setForeground(colors.get(record['type'], QColor("#333")))
        self.record_table.setItem(row, 4, type_item)

        self.record_table.setItem(row, 5, QTableWidgetItem(str(record['size'])))
        self.record_table.setItem(row, 6, QTableWidgetItem(record['summary']))

        self.record_table.scrollToBottom()

    def on_stat_update(self, stats):
        proto_text = ""
        for proto, count in sorted(stats['protocols'].items(), key=lambda x: x[1], reverse=True):
            proto_text += f"{proto}: {count}个\n"
        self.proto_stats.setPlainText(proto_text)

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
            self.conn_table.setItem(row, 2, QTableWidgetItem(proto))
            self.conn_table.setItem(row, 3, QTableWidgetItem(str(conn_stat['packets'])))
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
        self.proto_stats.clear()
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
