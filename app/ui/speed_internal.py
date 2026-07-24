import socket
import threading
import time
import subprocess
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSpinBox, QRadioButton, QButtonGroup, QComboBox,
    QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont


class InternalSpeedWorker(QObject):
    server_status_signal = Signal(str)
    client_result_signal = Signal(str)
    progress_signal = Signal(int)
    server_finished_signal = Signal()
    client_finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False

    def emit_server_status(self, text):
        self.server_status_signal.emit(text)

    def emit_client_result(self, text):
        self.client_result_signal.emit(text)

    def emit_progress(self, value):
        self.progress_signal.emit(value)

    def emit_server_finished(self):
        self.server_finished_signal.emit()

    def emit_client_finished(self):
        self.client_finished_signal.emit()


class SpeedInternalPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.server_running = False
        self.client_running = False
        self.server_thread = None
        self.client_thread = None
        self.server_socket = None
        self.client_socket = None
        self.worker = InternalSpeedWorker()

        self.worker.server_status_signal.connect(self.append_server_log)
        self.worker.client_result_signal.connect(self.append_client_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.server_finished_signal.connect(self.on_server_finished)
        self.worker.client_finished_signal.connect(self.on_client_finished)

        self.iperf3_installed = self.check_iperf3()
        self.local_ips = self.get_local_ips()

        self.init_ui()

    def stop_update_timer(self):
        self.server_running = False
        self.client_running = False
        self.worker.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2)
        if self.client_thread and self.client_thread.is_alive():
            self.client_thread.join(timeout=2)

    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)

    def append_server_log(self, text):
        if hasattr(self, 'server_log'):
            self.server_log.append(text)

    def append_client_log(self, text):
        if hasattr(self, 'client_log'):
            self.client_log.append(text)

    def update_progress(self, value):
        if hasattr(self, 'client_progress'):
            self.client_progress.setValue(value)

    def on_server_finished(self):
        self.server_running = False
        if hasattr(self, 'start_server_btn'):
            self.start_server_btn.setEnabled(True)
        if hasattr(self, 'stop_server_btn'):
            self.stop_server_btn.setEnabled(False)

    def on_client_finished(self):
        self.client_running = False
        if hasattr(self, 'start_client_btn'):
            self.start_client_btn.setEnabled(True)
        if hasattr(self, 'stop_client_btn'):
            self.stop_client_btn.setEnabled(False)
        if hasattr(self, 'client_progress'):
            self.client_progress.setValue(100)

    def get_iperf3_path(self):
        if hasattr(self, '_iperf3_path') and self._iperf3_path:
            return self._iperf3_path

        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        candidates = [
            os.path.join(exe_dir, 'iperf3.exe'),
            os.path.join(exe_dir, 'tools', 'iperf3.exe'),
            os.path.join(exe_dir, 'bin', 'iperf3.exe'),
        ]

        for c in candidates:
            if os.path.isfile(c):
                self._iperf3_path = c
                return c

        self._iperf3_path = 'iperf3'
        return 'iperf3'

    def check_iperf3(self):
        try:
            iperf3_path = self.get_iperf3_path()
            result = subprocess.run([iperf3_path, "--version"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode == 0
        except Exception:
            return False

    def get_local_ips(self):
        ips = []
        try:
            result = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in result.stdout.split('\n'):
                if "IPv4" in line:
                    match = re.search(r":\s*(\d+\.\d+\.\d+\.\d+)", line)
                    if match:
                        ips.append(match.group(1))
        except Exception:
            pass
        if not ips:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ips.append(s.getsockname()[0])
                s.close()
            except Exception:
                ips.append("127.0.0.1")
        return ips

    def init_ui(self):
        title_label = QLabel("📶 内网测速工具 - 测试局域网内两台电脑之间的网络速度 | 左侧: 服务端模式 | 右侧: 客户端模式 | 支持上传/下载/双向测试")
        title_label.setStyleSheet("color: #333; font-size: 11px; margin-bottom: 10px;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        main_layout.addWidget(title_label)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        left_panel = self._build_server_panel()
        right_panel = self._build_client_panel()

        content_layout.addWidget(left_panel, 1)
        content_layout.addWidget(right_panel, 1)

        main_layout.addLayout(content_layout)

    def _build_server_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("🔧 服务端模式")
        title.setStyleSheet("color: #5b9bd5; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)

        grid.addWidget(self._styled_label("监听端口:"), 0, 0)
        self.server_port = QSpinBox()
        self.server_port.setRange(1024, 65535)
        self.server_port.setValue(5201)
        self.server_port
        grid.addWidget(self.server_port, 0, 1)

        grid.addWidget(self._styled_label("本机网卡:"), 1, 0)
        self.local_ip_combo = QComboBox()
        if self.local_ips:
            for ip in self.local_ips:
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                    self.local_ip_combo.addItem(f"{ip} - {hostname}", ip)
                except Exception:
                    self.local_ip_combo.addItem(ip, ip)
        else:
            self.local_ip_combo.addItem("127.0.0.1", "127.0.0.1")
        self.local_ip_combo.setStyleSheet(self._combo_style())
        grid.addWidget(self.local_ip_combo, 1, 1)

        grid.addWidget(self._styled_label("测试引擎:"), 2, 0)
        self.server_engine_group = QButtonGroup(self)
        self.server_engine_builtin = QRadioButton("内置引擎")
        self.server_engine_iperf3 = QRadioButton("iperf3")
        self.server_engine_builtin.setChecked(True)
        server_engine_layout = QHBoxLayout()
        for r in (self.server_engine_builtin, self.server_engine_iperf3):
            r.setStyleSheet("color: #555; font-size: 12px;")
            server_engine_layout.addWidget(r)
            self.server_engine_group.addButton(r)
        server_engine_layout.addStretch()
        grid.addLayout(server_engine_layout, 2, 1)

        if not self.iperf3_installed:
            self.server_engine_iperf3.setEnabled(False)
            iperf3_tip = QLabel("❌ iperf3未安装(点击查看安装方法)")
            iperf3_tip.setStyleSheet("color: #c00; font-size: 11px;")
            grid.addWidget(iperf3_tip, 3, 0, 1, 2)

        tip_label = QLabel("⚠ 提示: 服务端监听所有网卡(0.0.0.0), 上方显示本机可用IP供客户端连接。请确保两端使用相同引擎！")
        tip_label.setStyleSheet("color: #ed7d31; font-size: 10px;")
        grid.addWidget(tip_label, 4, 0, 1, 2)

        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        self.start_server_btn = QPushButton("启动服务端")
        self.start_server_btn.setCursor(Qt.PointingHandCursor)
        self.start_server_btn.setStyleSheet(self._primary_btn_style("#5b9bd5", "#4a8ac4"))
        self.start_server_btn.clicked.connect(self.start_server)
        btn_layout.addWidget(self.start_server_btn)

        self.stop_server_btn = QPushButton("停止服务端")
        self.stop_server_btn.setCursor(Qt.PointingHandCursor)
        self.stop_server_btn.setEnabled(False)
        self.stop_server_btn.setStyleSheet(self._secondary_btn_style())
        self.stop_server_btn.clicked.connect(self.stop_server)
        btn_layout.addWidget(self.stop_server_btn)

        layout.addLayout(btn_layout)

        status_label = QLabel("📊 服务端状态")
        status_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        layout.addWidget(status_label)

        self.server_log = QTextEdit()
        self.server_log.setReadOnly(True)
        self.server_log.setStyleSheet("""
            QTextEdit {
                font-family: Consolas;
                font-size: 11px;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                background-color: white;
                color: #333;
                padding: 8px;
            }
        """)
        self.server_log.append("等待启动服务端...")
        layout.addWidget(self.server_log, 1)

        return panel

    def _build_client_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("⚡ 客户端模式")
        title.setStyleSheet("color: #5b9bd5; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)

        grid.addWidget(self._styled_label("服务器IP:"), 0, 0)
        self.server_ip = QLineEdit("192.168.1.100")
        self.server_ip.setStyleSheet(self._lineedit_style())
        grid.addWidget(self.server_ip, 0, 1)

        grid.addWidget(self._styled_label("服务器端口:"), 1, 0)
        self.client_port = QSpinBox()
        self.client_port.setRange(1024, 65535)
        self.client_port.setValue(5201)
        self.client_port
        grid.addWidget(self.client_port, 1, 1)

        grid.addWidget(self._styled_label("测试时长(秒):"), 2, 0)
        self.test_duration = QSpinBox()
        self.test_duration.setRange(1, 60)
        self.test_duration.setValue(10)
        self.test_duration
        grid.addWidget(self.test_duration, 2, 1)

        layout.addLayout(grid)

        mode_label = QLabel("测试模式:")
        mode_label.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(mode_label)

        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_upload = QRadioButton("上传")
        self.mode_download = QRadioButton("下载")
        self.mode_both = QRadioButton("双向")
        self.mode_download.setChecked(True)
        for r in (self.mode_upload, self.mode_download, self.mode_both):
            r.setStyleSheet("color: #555; font-size: 12px;")
            mode_layout.addWidget(r)
            self.mode_group.addButton(r)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        engine_label = QLabel("测试引擎:")
        engine_label.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(engine_label)

        engine_layout = QHBoxLayout()
        self.engine_group = QButtonGroup(self)
        self.engine_builtin = QRadioButton("内置引擎")
        self.engine_iperf3 = QRadioButton("iperf3")
        self.engine_builtin.setChecked(True)
        for r in (self.engine_builtin, self.engine_iperf3):
            r.setStyleSheet("color: #555; font-size: 12px;")
            engine_layout.addWidget(r)
            self.engine_group.addButton(r)
        engine_layout.addStretch()
        layout.addLayout(engine_layout)

        if not self.iperf3_installed:
            iperf3_tip = QLabel("❌ 未安装(点击查看安装方法)")
            iperf3_tip.setStyleSheet("color: #c00; font-size: 11px;")
            layout.addWidget(iperf3_tip)

        btn_layout = QHBoxLayout()
        self.start_client_btn = QPushButton("开始测速")
        self.start_client_btn.setCursor(Qt.PointingHandCursor)
        self.start_client_btn.setStyleSheet(self._primary_btn_style("#5b9bd5", "#4a8ac4"))
        self.start_client_btn.clicked.connect(self.start_client)
        btn_layout.addWidget(self.start_client_btn)

        self.stop_client_btn = QPushButton("停止测试")
        self.stop_client_btn.setCursor(Qt.PointingHandCursor)
        self.stop_client_btn.setEnabled(False)
        self.stop_client_btn.setStyleSheet(self._secondary_btn_style())
        self.stop_client_btn.clicked.connect(self.stop_client)
        btn_layout.addWidget(self.stop_client_btn)

        layout.addLayout(btn_layout)

        self.client_progress = QProgressBar()
        self.client_progress.setRange(0, 100)
        self.client_progress.setValue(0)
        self.client_progress.setTextVisible(False)
        self.client_progress.setFixedHeight(8)
        self.client_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: #e0e0e0;
            }
            QProgressBar::chunk {
                background: #5b9bd5;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.client_progress)

        result_label = QLabel("📋 测试结果")
        result_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        layout.addWidget(result_label)

        self.client_log = QTextEdit()
        self.client_log.setReadOnly(True)
        self.client_log.setStyleSheet("""
            QTextEdit {
                font-family: Consolas;
                font-size: 11px;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                background-color: white;
                color: #333;
                padding: 8px;
            }
        """)
        self.client_log.append("等待开始测速...")
        layout.addWidget(self.client_log, 1)

        return panel

    def start_server(self):
        if self.server_running:
            return

        port = self.server_port.value()
        self.server_running = True
        self.worker.is_running = True
        self.start_server_btn.setEnabled(False)
        self.stop_server_btn.setEnabled(True)
        self.server_log.clear()
        self.server_log.append("服务端启动中...")

        if self.server_engine_iperf3.isChecked():
            if not self.iperf3_installed:
                QMessageBox.warning(self, "警告", "iperf3 未安装，无法使用 iperf3 引擎")
                self.server_running = False
                self.start_server_btn.setEnabled(True)
                self.stop_server_btn.setEnabled(False)
                return
            self.server_thread = threading.Thread(target=self.run_iperf3_server, args=(port,))
        else:
            self.server_thread = threading.Thread(target=self.run_builtin_server, args=(port,))
        self.server_thread.start()

    def stop_server(self):
        self.server_running = False
        self.worker.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if hasattr(self, 'iperf3_proc') and self.iperf3_proc:
            try:
                self.iperf3_proc.terminate()
                self.iperf3_proc.wait(timeout=2)
            except Exception:
                try:
                    self.iperf3_proc.kill()
                except Exception:
                    pass
            self.iperf3_proc = None
        self.start_server_btn.setEnabled(True)
        self.stop_server_btn.setEnabled(False)
        self.server_log.append("服务端已停止")

    def run_builtin_server(self, port):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", port))
            self.server_socket.listen(10)
            self.server_socket.settimeout(1)

            self.worker.emit_server_status(f"内置服务端已启动, 监听端口: {port}")
            self.worker.emit_server_status(f"本机IP: {', '.join(self.local_ips)}")
            self.worker.emit_server_status("等待客户端连接...")

            while self.server_running:
                try:
                    conn, addr = self.server_socket.accept()
                    self.worker.emit_server_status(f"客户端连接: {addr[0]}:{addr[1]}")
                    threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.server_running:
                        self.worker.emit_server_status(f"错误: {e}")

        except Exception as e:
            self.worker.emit_server_status(f"启动失败: {e}")
            self.start_server_btn.setEnabled(True)
            self.stop_server_btn.setEnabled(False)

    def run_iperf3_server(self, port):
        try:
            self.worker.emit_server_status(f"iperf3 服务端启动中, 端口: {port}...")
            iperf3_path = self.get_iperf3_path()
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            self.iperf3_proc = subprocess.Popen(
                [iperf3_path, "-s", "-p", str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.worker.emit_server_status(f"iperf3 服务端已启动, 监听端口: {port}")
            self.worker.emit_server_status(f"本机IP: {', '.join(self.local_ips)}")
            self.worker.emit_server_status("等待客户端连接...")

            while self.server_running and self.iperf3_proc.poll() is None:
                try:
                    line = self.iperf3_proc.stdout.readline()
                    if line:
                        self.worker.emit_server_status(line.strip())
                except Exception:
                    break
                time.sleep(0.1)

            if self.iperf3_proc.poll() is not None:
                self.worker.emit_server_status("iperf3 服务端已退出")

        except Exception as e:
            self.worker.emit_server_status(f"iperf3 启动失败: {e}")
        finally:
            self.server_running = False
            self.worker.emit_server_finished()

    def handle_client(self, conn, addr):
        try:
            conn.settimeout(30)
            data = conn.recv(1024).decode("utf-8")
            if not data:
                return

            parts = data.split("|")
            if len(parts) < 2:
                return

            mode = parts[0]
            duration = int(parts[1]) if len(parts) > 1 else 10

            if mode == "download":
                self.worker.emit_server_status(f"开始上传数据给 {addr[0]}...")
                start_time = time.time()
                total_sent = 0
                chunk = b"x" * 65536
                while time.time() - start_time < duration and self.server_running:
                    try:
                        conn.sendall(chunk)
                        total_sent += len(chunk)
                    except Exception:
                        break

                elapsed = time.time() - start_time
                speed_mbps = (total_sent * 8) / (1024 * 1024 * elapsed) if elapsed > 0 else 0
                self.worker.emit_server_status(f"上传完成: {speed_mbps:.1f} Mbps")

            elif mode == "upload":
                self.worker.emit_server_status(f"开始接收 {addr[0]} 的数据...")
                start_time = time.time()
                total_received = 0
                while time.time() - start_time < duration and self.server_running:
                    try:
                        data = conn.recv(65536)
                        if not data:
                            break
                        total_received += len(data)
                    except Exception:
                        break

                elapsed = time.time() - start_time
                speed_mbps = (total_received * 8) / (1024 * 1024 * elapsed) if elapsed > 0 else 0
                self.worker.emit_server_status(f"接收完成: {speed_mbps:.1f} Mbps")

        except Exception as e:
            self.worker.emit_server_status(f"处理客户端 {addr[0]} 出错: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def start_client(self):
        if self.client_running:
            return

        server_ip = self.server_ip.text().strip()
        port = self.client_port.value()
        duration = self.test_duration.value()

        if not server_ip:
            QMessageBox.warning(self, "警告", "请输入服务器IP")
            return

        if self.engine_iperf3.isChecked() and not self.iperf3_installed:
            QMessageBox.warning(self, "警告", "iperf3 未安装，请使用内置引擎或先安装 iperf3")
            return

        self.client_running = True
        self.worker.is_running = True
        self.start_client_btn.setEnabled(False)
        self.stop_client_btn.setEnabled(True)
        self.client_log.clear()
        self.client_progress.setValue(0)
        self.client_socket = None

        if self.engine_iperf3.isChecked():
            self.client_thread = threading.Thread(target=self.run_iperf3_test, args=(server_ip, port, duration))
        else:
            self.client_thread = threading.Thread(target=self.run_builtin_test, args=(server_ip, port, duration))
        self.client_thread.start()

    def stop_client(self):
        self.client_running = False
        self.worker.is_running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        self.worker.emit_client_result("正在停止测试...")

    def run_builtin_test(self, server_ip, port, duration):
        mode = "download"
        if self.mode_upload.isChecked():
            mode = "upload"
        elif self.mode_both.isChecked():
            mode = "both"

        if mode == "both":
            self.run_builtin_single("download", server_ip, port, duration)
            if self.client_running:
                time.sleep(1)
                self.run_builtin_single("upload", server_ip, port, duration)
        else:
            self.run_builtin_single(mode, server_ip, port, duration)

        self.worker.emit_client_finished()

    def run_builtin_single(self, mode, server_ip, port, duration):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(5)
            self.client_socket.connect((server_ip, port))
            self.client_socket.settimeout(30)

            self.client_socket.sendall(f"{mode}|{duration}".encode("utf-8"))

            if mode == "download":
                self.worker.emit_client_result(f"正在从 {server_ip} 下载数据...")
                start_time = time.time()
                total_received = 0
                while time.time() - start_time < duration and self.client_running:
                    try:
                        data = self.client_socket.recv(65536)
                        if not data:
                            break
                        total_received += len(data)
                        elapsed = time.time() - start_time
                        progress = int(min(elapsed / duration * 100, 100))
                        self.worker.emit_progress(progress)
                    except Exception:
                        break

                elapsed = time.time() - start_time
                speed_mbps = (total_received * 8) / (1024 * 1024 * elapsed) if elapsed > 0 else 0
                self.worker.emit_client_result(f"下载速度: {speed_mbps:.1f} Mbps")

            elif mode == "upload":
                self.worker.emit_client_result(f"正在向 {server_ip} 上传数据...")
                start_time = time.time()
                total_sent = 0
                chunk = b"x" * 65536
                while time.time() - start_time < duration and self.client_running:
                    try:
                        self.client_socket.sendall(chunk)
                        total_sent += len(chunk)
                        elapsed = time.time() - start_time
                        progress = int(min(elapsed / duration * 100, 100))
                        self.worker.emit_progress(progress)
                    except Exception:
                        break

                elapsed = time.time() - start_time
                speed_mbps = (total_sent * 8) / (1024 * 1024 * elapsed) if elapsed > 0 else 0
                self.worker.emit_client_result(f"上传速度: {speed_mbps:.1f} Mbps")

            self.client_socket.close()
            self.client_socket = None

        except Exception as e:
            self.worker.emit_client_result(f"测试失败: {e}")

    def run_iperf3_test(self, server_ip, port, duration):
        iperf3_path = self.get_iperf3_path()
        try:
            mode = "-R" if self.mode_upload.isChecked() else ""
            if self.mode_both.isChecked():
                mode = ""

            cmd = [iperf3_path, "-c", server_ip, "-p", str(port), "-t", str(duration), "-i", "1"]
            if mode:
                cmd.append(mode)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 10, creationflags=subprocess.CREATE_NO_WINDOW)
            self.worker.emit_client_result(result.stdout)
            if result.returncode != 0:
                self.worker.emit_client_result(f"错误: {result.stderr}")

        except Exception as e:
            self.worker.emit_client_result(f"iperf3 测试失败: {e}")

        self.worker.emit_client_finished()

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
                min-width: 80px;
            }
        """

    def _combo_style(self):
        return """
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
                min-width: 200px;
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