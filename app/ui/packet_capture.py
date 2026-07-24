import threading
import time
import ctypes
from datetime import datetime
from scapy.all import sniff, wrpcap, rdpcap, IFACES, conf

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QComboBox, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt, QObject, Signal

from app.core.logger import Logger

logger = Logger("PacketCapture")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


class CaptureWorker(QObject):
    packet_signal = Signal(str)
    stat_signal = Signal(dict)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.interface = None
        self.filter = ""
        self.max_packets = 100
        self.packets = []
        self.packet_count = 0
        self.protocol_stats = {}
        self.start_time = None
        self._reported_errors = set()

    def start_capture(self, interface, filter_str, max_packets):
        self.interface = interface
        self.filter = filter_str
        self.max_packets = max_packets
        self.packets = []
        self.packet_count = 0
        self.protocol_stats = {}
        self.start_time = datetime.now()
        self.is_running = True
        self._reported_errors.clear()

        conf.iface = interface

        self.capture_thread = threading.Thread(target=self._run_capture)
        self.capture_thread.start()

    def _run_capture(self):
        while self.is_running and self.packet_count < self.max_packets:
            try:
                remaining = self.max_packets - self.packet_count
                batch = min(remaining, 50)
                sniff(
                    iface=self.interface,
                    filter=self.filter or None,
                    prn=self._process_packet,
                    count=batch,
                    store=False,
                    timeout=1,
                )
            except Exception as e:
                err_msg = str(e)
                if err_msg not in self._reported_errors:
                    self._reported_errors.add(err_msg)
                    logger.error(f"抓包错误: {err_msg}")
                    self.packet_signal.emit(f"❌ 抓包错误: {err_msg}")
                break
        self.is_running = False
        self.finished_signal.emit()

    def _process_packet(self, packet):
        if not self.is_running:
            return

        self.packet_count += 1

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        src_ip = dst_ip = "-"
        src_port = dst_port = "-"
        protocol = "Unknown"
        size = len(packet)

        if packet.haslayer('IP'):
            src_ip = packet['IP'].src
            dst_ip = packet['IP'].dst

            if packet.haslayer('TCP'):
                protocol = "TCP"
                src_port = packet['TCP'].sport
                dst_port = packet['TCP'].dport
            elif packet.haslayer('UDP'):
                protocol = "UDP"
                src_port = packet['UDP'].sport
                dst_port = packet['UDP'].dport
            elif packet.haslayer('ICMP'):
                protocol = "ICMP"
            else:
                protocol = f"IP({packet['IP'].proto})"
        elif packet.haslayer('ARP'):
            protocol = "ARP"
            src_ip = packet['ARP'].psrc
            dst_ip = packet['ARP'].pdst
        elif packet.haslayer('Ether'):
            protocol = f"Ether({hex(packet['Ether'].type)[2:]})"

        self.protocol_stats[protocol] = self.protocol_stats.get(protocol, 0) + 1

        content = f"[{timestamp}] {protocol:8} {src_ip}:{src_port:>5} -> {dst_ip}:{dst_port:>5} 大小={size}B"
        self.packet_signal.emit(content)

        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > 0:
            pps = self.packet_count / elapsed
        else:
            pps = 0

        self.stat_signal.emit({
            'count': self.packet_count,
            'protocols': self.protocol_stats,
            'pps': round(pps, 1)
        })

    def stop_capture(self):
        self.is_running = False
        if hasattr(self, 'capture_thread') and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)

    def export_pcap(self, filepath):
        try:
            wrpcap(filepath, self.packets)
            return True
        except Exception as e:
            logger.error(f"导出PCAP失败: {e}")
            return False

    def import_pcap(self, filepath):
        try:
            packets = rdpcap(filepath)
            return packets
        except Exception as e:
            logger.error(f"导入PCAP失败: {e}")
            return str(e)


class PacketCapturePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = CaptureWorker()
        self.worker.packet_signal.connect(self.on_packet)
        self.worker.stat_signal.connect(self.on_stat_update)
        self.worker.finished_signal.connect(self.on_capture_finished)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        self._build_warning_area(main_layout)
        self._build_config_area(main_layout)
        self._build_result_area(main_layout)
        self._build_stats_area(main_layout)

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

    def _build_warning_area(self, parent_layout):
        if not is_admin():
            frame = QFrame()
            frame.setStyleSheet("""
                QFrame {
                    background-color: #fdf2f2;
                    border: 1px solid #fecaca;
                    border-radius: 5px;
                }
            """)
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(12, 8, 12, 8)

            icon = QLabel("⚠")
            icon.setStyleSheet("font-size: 16px; color: #dc2626;")
            layout.addWidget(icon)

            text = QLabel("抓包功能需要管理员权限！请右键选择\"以管理员身份运行\"")
            text.setStyleSheet("font-size: 12px; color: #dc2626;")
            layout.addWidget(text)

            parent_layout.addWidget(frame)

    def _build_config_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; background: #fafafa; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        title = QLabel("📡 抓包参数配置")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("选择网卡:"), 0, 0)
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(300)
        self._refresh_interfaces()
        grid.addWidget(self.iface_combo, 0, 1)

        grid.addWidget(QLabel("过滤器:"), 1, 0)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("例如: tcp | udp | icmp | host 192.168.1.1")
        grid.addWidget(self.filter_edit, 1, 1)

        hint_label = QLabel("💡 示例: tcp | udp | icmp | host 192.168.1.1 | port 80 | tcp port 443")
        hint_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(hint_label, 2, 0, 1, 2)

        grid.addWidget(QLabel("最大包数:"), 3, 0)
        self.max_packets_spin = QSpinBox()
        self.max_packets_spin.setRange(10, 2000)
        self.max_packets_spin.setValue(100)
        self.max_packets_spin.setSuffix(" 包")
        self.max_packets_spin.setStyleSheet(self._spinbox_style())
        grid.addWidget(self.max_packets_spin, 3, 1)

        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.start_btn = QPushButton("🚀 开始抓包")
        self.start_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 7px 16px; border-radius: 3px; font-size: 12px;")
        self.start_btn.clicked.connect(self.start_capture)

        self.stop_btn = QPushButton("⏹ 停止抓包")
        self.stop_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; padding: 7px 16px; border-radius: 3px; font-size: 12px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_capture)

        self.clear_btn = QPushButton("🗑 清空")
        self.clear_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 7px 16px; border-radius: 3px; font-size: 12px;")
        self.clear_btn.clicked.connect(self.clear_results)

        self.export_btn = QPushButton("📤 导出PCAP")
        self.export_btn.setStyleSheet("background-color: #3498db; color: white; border: none; padding: 7px 16px; border-radius: 3px; font-size: 12px;")
        self.export_btn.clicked.connect(self.export_pcap)

        self.import_btn = QPushButton("📥 导入PCAP")
        self.import_btn.setStyleSheet("background-color: #9b59b6; color: white; border: none; padding: 7px 16px; border-radius: 3px; font-size: 12px;")
        self.import_btn.clicked.connect(self.import_pcap)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.import_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)
        parent_layout.addWidget(frame)

    def _build_result_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title = QLabel("📊 抓包结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        layout.addWidget(title)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #00ff41;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                border: none;
            }
        """)
        self.result_text.append("等待抓包开始...")
        layout.addWidget(self.result_text)

        parent_layout.addWidget(frame)

    def _build_stats_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; background: #fafafa; }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(15)

        title = QLabel("📈 抓包统计")
        title.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        layout.addWidget(title)

        self.stats_label = QLabel("准备就绪")
        self.stats_label.setStyleSheet("font-size: 12px; color: #555;")
        layout.addWidget(self.stats_label)

        layout.addStretch()
        parent_layout.addWidget(frame)

    def _refresh_interfaces(self):
        self.iface_combo.clear()
        try:
            for iface_key, iface in IFACES.data.items():
                if iface_key.lower().startswith("lo") or "loopback" in iface_key.lower():
                    continue
                desc = iface.description or iface.name or iface_key
                ip_addr = ""
                try:
                    ip_addr = iface.ip
                except:
                    pass
                display = f"{desc} ({ip_addr})" if ip_addr else desc
                self.iface_combo.addItem(display, iface_key)
            logger.info(f"获取到 {self.iface_combo.count()} 个网卡")
        except Exception as e:
            logger.error(f"获取网卡列表失败: {e}")
            QMessageBox.warning(self, "警告", f"获取网卡列表失败: {str(e)}")

    def start_capture(self):
        if not is_admin():
            QMessageBox.warning(self, "权限不足", "抓包功能需要管理员权限！请右键选择\"以管理员身份运行\"")
            return

        interface = self.iface_combo.currentData()
        if not interface:
            QMessageBox.warning(self, "提示", "请选择网卡")
            return

        self.worker.start_capture(
            interface=interface,
            filter_str=self.filter_edit.text(),
            max_packets=self.max_packets_spin.value()
        )

        display_name = self.iface_combo.currentText()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.result_text.clear()
        self.result_text.append(f"开始抓包: {display_name} | 过滤器: {self.filter_edit.text() or '无'} | 最大包数: {self.max_packets_spin.value()}")
        self.result_text.append("-" * 100)

    def stop_capture(self):
        self.worker.stop_capture()
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(True)

    def on_packet(self, content):
        self.result_text.append(content)
        scroll_bar = self.result_text.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def on_stat_update(self, stats):
        proto_str = ", ".join([f"{k}: {v}" for k, v in stats['protocols'].items()])
        self.stats_label.setText(f"已捕获: {stats['count']} 包 | 协议: {proto_str} | 速率: {stats['pps']} pps")

    def on_capture_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.result_text.append("-" * 100)
        self.result_text.append("✅ 抓包完成")

    def clear_results(self):
        self.result_text.clear()
        self.result_text.append("等待抓包开始...")
        self.stats_label.setText("准备就绪")

    def export_pcap(self):
        import os
        filepath = os.path.join(os.path.expanduser("~"), f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pcap")
        if self.worker.export_pcap(filepath):
            QMessageBox.information(self, "成功", f"PCAP文件已导出到:\n{filepath}")
        else:
            QMessageBox.warning(self, "提示", "导出失败")

    def import_pcap(self):
        from PySide6.QtWidgets import QFileDialog
        filepath, _ = QFileDialog.getOpenFileName(self, "选择PCAP文件", "", "PCAP文件 (*.pcap *.pcapng)")
        if filepath:
            result = self.worker.import_pcap(filepath)
            if isinstance(result, str):
                QMessageBox.warning(self, "错误", f"导入失败: {result}")
            else:
                self.result_text.clear()
                self.result_text.append(f"已导入PCAP文件: {filepath}")
                self.result_text.append(f"数据包数量: {len(result)}")
                self.result_text.append("-" * 100)
                for i, packet in enumerate(result[:50]):
                    if packet.haslayer('IP'):
                        proto = "TCP" if packet.haslayer('TCP') else "UDP" if packet.haslayer('UDP') else "ICMP" if packet.haslayer('ICMP') else "IP"
                        self.result_text.append(f"[{i+1}] {proto} {packet['IP'].src} -> {packet['IP'].dst}")
                if len(result) > 50:
                    self.result_text.append(f"... 还有 {len(result) - 50} 个包未显示")

    def cleanup(self):
        self.worker.stop_capture()
        self.worker.packet_signal.disconnect()
        self.worker.stat_signal.disconnect()
        self.worker.finished_signal.disconnect()

    def stop_all(self):
        self.cleanup()

    def stop_update_timer(self):
        self.cleanup()