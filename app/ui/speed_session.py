import socket
import threading
import time
import datetime
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSpinBox, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QFont


class SessionTestWorker(QObject):
    log_signal = Signal(str)
    success_signal = Signal(int)
    fail_signal = Signal(int)
    time_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False

    def emit_log(self, text):
        self.log_signal.emit(text)

    def emit_success(self, count):
        self.success_signal.emit(count)

    def emit_fail(self, count):
        self.fail_signal.emit(count)

    def emit_time(self, text):
        self.time_signal.emit(text)

    def emit_finished(self):
        self.finished_signal.emit()


class SpeedSessionPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self.server_thread = None
        self.test_thread = None
        self.server_socket = None
        self.success_count = 0
        self.fail_count = 0
        self.start_time = None
        self.timer = None
        self.worker = SessionTestWorker()

        self.worker.log_signal.connect(self.append_log)
        self.worker.success_signal.connect(self.update_success)
        self.worker.fail_signal.connect(self.update_fail)
        self.worker.time_signal.connect(self.update_time)
        self.worker.finished_signal.connect(self.on_test_finished)

        self.init_ui()

    def stop_update_timer(self):
        self.is_running = False
        self.worker.is_running = False
        if self.timer:
            self.timer.stop()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2)
        if self.test_thread and self.test_thread.is_alive():
            self.test_thread.join(timeout=2)

    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)

    def append_log(self, text):
        if hasattr(self, 'log_text'):
            self.log_text.append(text)

    def update_success(self, count):
        self.success_count = count
        if hasattr(self, 'success_label'):
            self.success_label.setText(str(count))

    def update_fail(self, count):
        self.fail_count = count
        if hasattr(self, 'fail_label'):
            self.fail_label.setText(str(count))

    def update_time(self, text):
        if hasattr(self, 'time_label'):
            self.time_label.setText(text)

    def on_test_finished(self):
        self.is_running = False
        if self.timer:
            self.timer.stop()
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(True)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setEnabled(False)
        self.append_log("测试已结束")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title_label = QLabel("🔗 会话数测试")
        title_label.setStyleSheet("color: #3498db; font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        self._build_config_area(layout)
        self._build_button_area(layout)
        self._build_stats_area(layout)
        self._build_log_area(layout)

    def _build_config_area(self, parent_layout):
        title = QLabel("⚙ 测试配置")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        grid = QGridLayout(frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(15)

        grid.addWidget(self._styled_label("测试服务器:"), 0, 0)
        server_layout = QHBoxLayout()
        self.server_group = QButtonGroup(self)
        self.server_main = QRadioButton("主服务器")
        self.server_backup = QRadioButton("备用服务器")
        self.server_main.setChecked(True)
        for r in (self.server_main, self.server_backup):
            r.setStyleSheet("color: #555; font-size: 12px;")
            server_layout.addWidget(r)
            self.server_group.addButton(r)
        server_layout.addStretch()
        grid.addLayout(server_layout, 0, 1, 1, 3)

        grid.addWidget(self._styled_label("延迟(ms):"), 1, 0)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 1000)
        self.delay_spin.setValue(100)
        self.delay_spin
        grid.addWidget(self.delay_spin, 1, 1)

        grid.addWidget(self._styled_label("线程数:"), 1, 2)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 100)
        self.threads_spin.setValue(10)
        self.threads_spin
        grid.addWidget(self.threads_spin, 1, 3)

        grid.addWidget(self._styled_label("最大连接:"), 2, 0)
        self.max_conn_spin = QSpinBox()
        self.max_conn_spin.setRange(1, 100000)
        self.max_conn_spin.setValue(10000)
        self.max_conn_spin
        grid.addWidget(self.max_conn_spin, 2, 1)

        grid.addWidget(self._styled_label("失败上限:"), 2, 2)
        self.fail_limit_spin = QSpinBox()
        self.fail_limit_spin.setRange(1, 1000)
        self.fail_limit_spin.setValue(100)
        self.fail_limit_spin
        grid.addWidget(self.fail_limit_spin, 2, 3)

        parent_layout.addWidget(frame)

    def _build_button_area(self, parent_layout):
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.start_btn = QPushButton("开始测试")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet(self._primary_btn_style("#5b9bd5", "#4a8ac4"))
        self.start_btn.clicked.connect(self.start_test)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._secondary_btn_style())
        self.stop_btn.clicked.connect(self.stop_test)
        btn_layout.addWidget(self.stop_btn)

        parent_layout.addLayout(btn_layout)

    def _build_stats_area(self, parent_layout):
        title = QLabel("📊 实时统计")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        grid = QGridLayout(frame)
        grid.setContentsMargins(30, 15, 30, 15)
        grid.setSpacing(100)

        success_label = QLabel("成功连接")
        success_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(success_label, 0, 0)
        self.success_label = QLabel("0")
        self.success_label.setStyleSheet("color: #00b050; font-size: 24px; font-weight: bold; font-family: Consolas;")
        grid.addWidget(self.success_label, 1, 0)

        fail_label = QLabel("失败次数")
        fail_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(fail_label, 0, 1)
        self.fail_label = QLabel("0")
        self.fail_label.setStyleSheet("color: #c00; font-size: 24px; font-weight: bold; font-family: Consolas;")
        grid.addWidget(self.fail_label, 1, 1)

        time_label = QLabel("运行时间")
        time_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(time_label, 0, 2)
        self.time_label = QLabel("0s")
        self.time_label.setStyleSheet("color: #1976d2; font-size: 24px; font-weight: bold; font-family: Consolas;")
        grid.addWidget(self.time_label, 1, 2)

        parent_layout.addWidget(frame)

    def _build_log_area(self, parent_layout):
        title = QLabel("📋 运行日志")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
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
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now}] 就绪，等待开始测试...")
        parent_layout.addWidget(self.log_text, 1)

    def start_test(self):
        if self.is_running:
            return

        self.is_running = True
        self.worker.is_running = True
        self.success_count = 0
        self.fail_count = 0
        self.start_time = time.time()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_text.clear()

        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.worker.emit_log(f"[{now}] 开始会话数测试...")

        server_type = "主服务器" if self.server_main.isChecked() else "备用服务器"
        delay = self.delay_spin.value()
        threads = self.threads_spin.value()
        max_conn = self.max_conn_spin.value()
        fail_limit = self.fail_limit_spin.value()

        self.worker.emit_log(f"测试服务器: {server_type}")
        self.worker.emit_log(f"延迟: {delay}ms, 线程数: {threads}")
        self.worker.emit_log(f"最大连接: {max_conn}, 失败上限: {fail_limit}")

        self.server_thread = threading.Thread(target=self.run_local_server, daemon=True)
        self.server_thread.start()

        time.sleep(0.5)

        self.test_thread = threading.Thread(target=self.run_test, args=(delay, threads, max_conn, fail_limit))
        self.test_thread.start()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed_time)
        self.timer.start(1000)

    def stop_test(self):
        self.is_running = False
        self.worker.is_running = False
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.worker.emit_log(f"[{now}] 正在停止测试...")

    def run_local_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("127.0.0.1", 5201))
            self.server_socket.listen(1000)
            self.server_socket.settimeout(1)

            now = datetime.datetime.now().strftime("%H:%M:%S")
            self.worker.emit_log(f"[{now}] 本地服务器已启动，监听 127.0.0.1:5201")

            while self.is_running:
                try:
                    conn, addr = self.server_socket.accept()
                    conn.settimeout(1)
                    threading.Thread(target=self.handle_client_connection, args=(conn,), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        now = datetime.datetime.now().strftime("%H:%M:%S")
                        self.worker.emit_log(f"[{now}] 服务器错误: {e}")

        except Exception as e:
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self.worker.emit_log(f"[{now}] 服务器启动失败: {e}")

    def handle_client_connection(self, conn):
        try:
            data = conn.recv(1024)
            if data:
                conn.sendall(b"OK")
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def run_test(self, delay, threads, max_conn, fail_limit):
        connections = []
        with ThreadPoolExecutor(max_workers=threads) as executor:
            while self.is_running and len(connections) < max_conn and self.fail_count < fail_limit:
                futures = []
                for _ in range(min(threads, max_conn - len(connections))):
                    if not self.is_running or self.fail_count >= fail_limit:
                        break
                    futures.append(executor.submit(self.connect_to_server))

                for future in futures:
                    if not self.is_running or self.fail_count >= fail_limit:
                        break
                    try:
                        conn = future.result()
                        if conn:
                            connections.append(conn)
                            self.success_count += 1
                            self.worker.emit_success(self.success_count)
                        else:
                            self.fail_count += 1
                            self.worker.emit_fail(self.fail_count)
                    except Exception:
                        self.fail_count += 1
                        self.worker.emit_fail(self.fail_count)

                if delay > 0:
                    time.sleep(delay / 1000)

        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.worker.emit_log(f"[{now}] 测试结束 - 成功: {self.success_count}, 失败: {self.fail_count}")

        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

        self.worker.emit_finished()

    def connect_to_server(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("127.0.0.1", 5201))
            sock.sendall(b"HELLO")
            response = sock.recv(1024)
            if response == b"OK":
                return sock
            sock.close()
            return None
        except Exception:
            return None

    def update_elapsed_time(self):
        if self.start_time and self.is_running:
            elapsed = int(time.time() - self.start_time)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            if hours > 0:
                self.worker.emit_time(f"{hours}h{minutes}m{seconds}s")
            elif minutes > 0:
                self.worker.emit_time(f"{minutes}m{seconds}s")
            else:
                self.worker.emit_time(f"{seconds}s")

    def _styled_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #555; font-size: 12px;")
        return lbl

    def _spinbox_style(self):
        return """
            QSpinBox {
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
                min-width: 100px;
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