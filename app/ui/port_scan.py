import threading
import socket
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QSpinBox, QComboBox, QProgressBar, QTableWidget,
    QTableWidgetItem
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QFont

class PortScanWorker(QObject):
    status_signal = Signal(str)
    progress_signal = Signal(int)
    result_signal = Signal(tuple)
    finished_signal = Signal()
    
    def __init__(self):
        super().__init__()
    
    def emit_status(self, text):
        self.status_signal.emit(text)
    
    def emit_progress(self, value):
        self.progress_signal.emit(value)
    
    def emit_result(self, port, status, service):
        self.result_signal.emit((port, status, service))

class PortScanPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.is_running = False
        self.thread = None
        self.open_ports = []
        self.worker = PortScanWorker()
        self.worker.status_signal.connect(self.update_status)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.add_result)
        self.worker.finished_signal.connect(self.on_scan_finished)
        self.init_ui()
    
    def stop_update_timer(self):
        self.is_running = False
        self.worker.is_running = False
        try:
            self.worker.status_signal.disconnect(self.update_status)
            self.worker.progress_signal.disconnect(self.update_progress)
            self.worker.result_signal.disconnect(self.add_result)
            self.worker.finished_signal.disconnect(self.on_scan_finished)
        except:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
    
    def on_scan_finished(self):
        self.is_running = False
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(True)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setEnabled(False)
    
    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)
    
    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)

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

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title_label = QLabel("端口扫描")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)
        
        group = QGroupBox("端口扫描设置")
        grid_layout = QGridLayout(group)
        
        grid_layout.addWidget(QLabel("目标地址:"), 0, 0)
        self.target_input = QLineEdit("192.168.1.1")
        grid_layout.addWidget(self.target_input, 0, 1)
        
        grid_layout.addWidget(QLabel("端口范围:"), 1, 0)
        self.port_range_input = QLineEdit("1-1000")
        grid_layout.addWidget(self.port_range_input, 1, 1)
        
        grid_layout.addWidget(QLabel("常用端口:"), 2, 0)
        self.common_ports_combo = QComboBox()
        self.common_ports_combo.addItems(["自定义", "HTTP(80)", "HTTPS(443)", "SSH(22)", "FTP(21)", "MySQL(3306)", "SQL Server(1433)", "RDP(3389)", "全部常用端口"])
        self.common_ports_combo.currentIndexChanged.connect(self.select_common_ports)
        grid_layout.addWidget(self.common_ports_combo, 2, 1)
        
        grid_layout.addWidget(QLabel("超时(秒):"), 3, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(2)
        self.timeout_spin.setStyleSheet(self._spinbox_style())
        grid_layout.addWidget(self.timeout_spin, 3, 1)
        
        grid_layout.addWidget(QLabel("并发数:"), 4, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(10, 200)
        self.threads_spin.setValue(50)
        self.threads_spin.setStyleSheet(self._spinbox_style())
        grid_layout.addWidget(self.threads_spin, 4, 1)
        
        layout.addWidget(group)
        
        bottom_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始扫描")
        self.start_btn.clicked.connect(self.start_scan)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.setEnabled(False)
        bottom_layout.addWidget(self.start_btn)
        bottom_layout.addWidget(self.stop_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(self.status_label)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["端口", "状态", "服务"])
        self.result_table.setColumnWidth(0, 80)
        self.result_table.setColumnWidth(1, 80)
        self.result_table.setColumnWidth(2, 200)
        layout.addWidget(self.result_table)
    
    def select_common_ports(self, index):
        port_ranges = {
            0: "1-1000",
            1: "80",
            2: "443",
            3: "22",
            4: "21",
            5: "3306",
            6: "1433",
            7: "3389",
            8: "21,22,23,25,53,80,110,143,443,445,3306,3389,8080"
        }
        self.port_range_input.setText(port_ranges.get(index, "1-1000"))
    
    def parse_ports(self, port_str):
        ports = []
        for part in port_str.split(','):
            part = part.strip()
            if '-' in part:
                start, end = part.split('-')
                ports.extend(range(int(start), int(end) + 1))
            else:
                ports.append(int(part))
        return sorted(set(ports))
    
    def get_service_name(self, port):
        services = {
            21: "FTP",
            22: "SSH",
            23: "Telnet",
            25: "SMTP",
            53: "DNS",
            80: "HTTP",
            110: "POP3",
            143: "IMAP",
            443: "HTTPS",
            445: "SMB",
            3306: "MySQL",
            3389: "RDP",
            8080: "HTTP Proxy",
            8081: "HTTP Alternate",
            1433: "SQL Server",
            27017: "MongoDB",
            5432: "PostgreSQL"
        }
        return services.get(port, "未知")
    
    def start_scan(self):
        if self.is_running:
            return
        
        self.is_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_ports = []
        self.result_table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在扫描...")
        
        self.thread = threading.Thread(target=self.run_scan)
        self.thread.start()
    
    def stop_scan(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.is_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("扫描已停止")
    
    def update_status(self, text):
        if hasattr(self, 'status_label'):
            self.status_label.setText(text)
    
    def update_progress(self, value):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)
    
    def add_result(self, data):
        port, status, service = data
        if hasattr(self, 'result_table'):
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem(str(port)))
            self.result_table.setItem(row, 1, QTableWidgetItem(status))
            self.result_table.setItem(row, 2, QTableWidgetItem(service))
            
            if status == "开放":
                self.result_table.item(row, 1).setForeground(Qt.green)
                self.result_table.item(row, 0).setForeground(Qt.green)
    
    def run_scan(self):
        target = self.target_input.text().strip()
        port_str = self.port_range_input.text().strip()
        timeout = self.timeout_spin.value()
        threads = self.threads_spin.value()
        
        try:
            ports = self.parse_ports(port_str)
            total_ports = len(ports)
            
            if total_ports == 0:
                self.worker.emit_status("无效的端口范围")
                self.stop_scan()
                return
            
            self.worker.emit_status(f"正在扫描 {target} 的 {total_ports} 个端口...")
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {executor.submit(self.scan_port, target, port, timeout): port for port in ports}
                
                completed = 0
                for future in as_completed(futures):
                    if not self.is_running:
                        break
                    
                    completed += 1
                    progress = (completed / total_ports) * 100
                    self.worker.emit_progress(int(progress))
                    
                    port = futures[future]
                    try:
                        result = future.result()
                        if result:
                            self.open_ports.append(port)
                            service = self.get_service_name(port)
                            self.worker.emit_result(port, "开放", service)
                    except:
                        pass
            
            if self.is_running:
                self.worker.emit_status(f"扫描完成，发现 {len(self.open_ports)} 个开放端口")
                self.worker.emit_progress(100)
        
        except Exception as e:
            self.worker.emit_status(f"扫描错误: {str(e)}")
        finally:
            self.worker.is_running = False
            self.worker.finished_signal.emit()
    
    def scan_port(self, host, port, timeout):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False