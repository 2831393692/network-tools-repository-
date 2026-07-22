"""远程终端页面 - SSH / Telnet 多会话终端

使用 QThread + Signal 处理 SSH/Telnet 连接和输出，
支持同时打开多个会话，页面切换时调用 cleanup() 关闭所有连接。
"""
import socket
import time
import threading
import json
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QPlainTextEdit,
    QTabWidget, QDialog, QSpinBox, QMessageBox,
    QFrame, QSizePolicy, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QEvent
from PySide6.QtGui import QFont, QTextCursor

# paramiko 可选依赖
try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


# ---------------------------------------------------------------------------
# 后台线程类
# ---------------------------------------------------------------------------
class SshWorker(QThread):
    """SSH 连接后台线程，实时接收服务器输出。"""
    output_signal = Signal(str)
    connected_signal = Signal()
    disconnected_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, host, port, username, password):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.channel = None
        self._running = False
        self._lock = threading.Lock()

    def run(self):
        if not HAS_PARAMIKO:
            self.error_signal.emit("错误: 未安装 paramiko 库，无法使用 SSH 功能。\n请执行: pip install paramiko")
            return

        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=15,
                look_for_keys=False,
                allow_agent=False
            )
            self.channel = self.client.invoke_shell(term='xterm', width=120, height=40)
            self.channel.settimeout(0.5)
            self._running = True
            self.connected_signal.emit()

            # 接收循环
            while self._running:
                try:
                    if self.channel.recv_ready():
                        data = self.channel.recv(4096)
                        if data:
                            try:
                                text = data.decode('utf-8', errors='replace')
                            except Exception:
                                text = data.decode('gbk', errors='replace')
                            self.output_signal.emit(text)
                        else:
                            break
                    else:
                        time.sleep(0.05)

                    if self.channel.closed:
                        break
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        self.error_signal.emit(f"接收异常: {e}")
                    break

            self.disconnected_signal.emit("连接已关闭")
        except paramiko.AuthenticationException:
            self.error_signal.emit("认证失败: 用户名或密码错误")
        except paramiko.SSHException as e:
            self.error_signal.emit(f"SSH 错误: {e}")
        except socket.error as e:
            self.error_signal.emit(f"网络错误: {e}")
        except Exception as e:
            self.error_signal.emit(f"连接错误: {e}")
        finally:
            self._running = False
            self._close()

    def send_command(self, cmd):
        """发送命令到服务器。"""
        with self._lock:
            if self.channel and not self.channel.closed:
                try:
                    self.channel.send(cmd + '\n')
                    return True
                except Exception as e:
                    self.error_signal.emit(f"发送失败: {e}")
        return False

    def _close(self):
        if self.channel:
            try:
                self.channel.close()
            except Exception:
                pass
            self.channel = None
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def stop(self):
        """安全停止线程。"""
        self._running = False
        self._close()
        self.wait(2000)


class TelnetWorker(QThread):
    """Telnet 连接后台线程，实时接收服务器输出。"""
    output_signal = Signal(str)
    connected_signal = Signal()
    disconnected_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.tn = None
        self._running = False
        self._lock = threading.Lock()

    def run(self):
        try:
            import telnetlib
            self.tn = telnetlib.Telnet()
            self.tn.open(self.host, self.port, timeout=10)
            self._running = True
            self.connected_signal.emit()

            while self._running:
                try:
                    data = self.tn.read_very_eager()
                    if data:
                        try:
                            text = data.decode('utf-8', errors='replace')
                        except Exception:
                            text = data.decode('gbk', errors='replace')
                        self.output_signal.emit(text)
                    else:
                        time.sleep(0.1)
                except EOFError:
                    break
                except Exception as e:
                    if self._running:
                        self.error_signal.emit(f"接收异常: {e}")
                    break

            self.disconnected_signal.emit("连接已关闭")
        except ConnectionRefusedError:
            self.error_signal.emit("连接被拒绝: 目标主机拒绝了 Telnet 连接")
        except socket.timeout:
            self.error_signal.emit("连接超时: 无法连接到目标主机")
        except socket.error as e:
            self.error_signal.emit(f"网络错误: {e}")
        except Exception as e:
            self.error_signal.emit(f"连接错误: {e}")
        finally:
            self._running = False
            self._close()

    def send_command(self, cmd):
        """发送命令到服务器。"""
        with self._lock:
            if self.tn:
                try:
                    self.tn.write((cmd + '\n').encode('utf-8', errors='replace'))
                    return True
                except Exception as e:
                    self.error_signal.emit(f"发送失败: {e}")
        return False

    def _close(self):
        if self.tn:
            try:
                self.tn.close()
            except Exception:
                pass
            self.tn = None

    def stop(self):
        """安全停止线程。"""
        self._running = False
        self._close()
        self.wait(2000)


# ---------------------------------------------------------------------------
# 连接对话框
# ---------------------------------------------------------------------------
class SshConnectDialog(QDialog):
    """SSH 新建会话对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 SSH 连接")
        self.setMinimumWidth(400)
        self.history_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'ssh_history.json')
        self.history = self._load_history()
        self.init_ui()

    def _load_history(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_history(self, data):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QFrame()
        title_bar.setStyleSheet("""
            QFrame {
                background-color: #1e3a5f;
                padding: 12px 20px;
            }
        """)
        title_layout = QHBoxLayout(title_bar)
        title_label = QLabel("🔐 新建 SSH 连接")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        title_layout.addWidget(title_label)
        layout.addWidget(title_bar)

        content_frame = QFrame()
        content_frame.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(20, 15, 20, 15)
        content_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("📜 历史记录 (选择自动填充):"), 0, 0, 1, 2)
        self.history_combo = QComboBox()
        self.history_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 3px;
                font-size: 12px;
            }
        """)
        self.history_combo.addItem("请选择历史记录", None)
        for item in self.history:
            display = f"{item.get('username', '')}@{item.get('host', '')}:{item.get('port', 22)}"
            self.history_combo.addItem(display, item)
        self.history_combo.currentIndexChanged.connect(self._on_history_selected)
        grid.addWidget(self.history_combo, 1, 0, 1, 2)

        grid.addWidget(QLabel("主机 / Host:"), 2, 0)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("例如: 192.168.1.1")
        self.host_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 3px;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.host_input, 2, 1)

        grid.addWidget(QLabel("端口 / Port:"), 3, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(22)
        self.port_input.setFixedWidth(80)
        grid.addWidget(self.port_input, 3, 1, alignment=Qt.AlignLeft)

        grid.addWidget(QLabel("用户名 / Username:"), 4, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("例如: root")
        self.username_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 3px;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.username_input, 4, 1)

        grid.addWidget(QLabel("密码 / Password:"), 5, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("输入密码")
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 3px;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.password_input, 5, 1)

        grid.addWidget(QLabel("设备类型 / Device Type:"), 6, 0)
        self.device_type_combo = QComboBox()
        device_types = [
            ("华为/Cisco/通用", "huawei_cisco"),
            ("Linux 服务器", "linux"),
            ("Windows 服务器", "windows"),
            ("网络设备", "network"),
        ]
        for label, value in device_types:
            self.device_type_combo.addItem(label, value)
        self.device_type_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 3px;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.device_type_combo, 6, 1)

        content_layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.connect_btn = QPushButton("🔗 连接")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f;
                color: white;
                border: none;
                padding: 8px 24px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #0d2137; }
        """)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self.on_connect)
        btn_layout.addWidget(self.connect_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 24px;
                font-size: 12px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        content_layout.addLayout(btn_layout)
        layout.addWidget(content_frame)

    def _on_history_selected(self, index):
        item = self.history_combo.itemData(index)
        if item:
            self.host_input.setText(item.get('host', ''))
            self.port_input.setValue(item.get('port', 22))
            self.username_input.setText(item.get('username', ''))
            self.password_input.setText(item.get('password', ''))

    def on_connect(self):
        if not self.host_input.text().strip():
            QMessageBox.warning(self, "提示", "请输入主机/IP")
            return
        if not self.username_input.text().strip():
            QMessageBox.warning(self, "提示", "请输入用户名")
            return
        
        data = self.get_data()
        existing = False
        for i, item in enumerate(self.history):
            if item['host'] == data['host'] and item['username'] == data['username']:
                self.history[i] = data
                existing = True
                break
        if not existing:
            self.history.append(data)
            if len(self.history) > 20:
                self.history = self.history[-20:]
        self._save_history(data)
        
        self.accept()

    def get_data(self):
        return {
            'host': self.host_input.text().strip(),
            'port': self.port_input.value(),
            'username': self.username_input.text().strip(),
            'password': self.password_input.text(),
            'device_type': self.device_type_combo.currentData(),
        }


class TelnetConnectDialog(QDialog):
    """Telnet 新建会话对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 Telnet 会话")
        self.setMinimumWidth(360)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("🔌 新建 Telnet 连接")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("主机/IP:"), 0, 0)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("例如: 192.168.1.1")
        grid.addWidget(self.host_input, 0, 1)

        grid.addWidget(QLabel("端口:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(23)
        self.port_input.setFixedWidth(80)
        grid.addWidget(self.port_input, 1, 1, alignment=Qt.AlignLeft)

        grid.addWidget(QLabel("连接名称:"), 2, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("可选，留空使用主机名")
        grid.addWidget(self.name_input, 2, 1)

        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.connect_btn = QPushButton("🚀 连接")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 8px 24px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self.on_connect)
        btn_layout.addWidget(self.connect_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 24px;
                font-size: 12px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def on_connect(self):
        if not self.host_input.text().strip():
            QMessageBox.warning(self, "提示", "请输入主机/IP")
            return
        self.accept()

    def get_data(self):
        return {
            'host': self.host_input.text().strip(),
            'port': self.port_input.value(),
            'name': self.name_input.text().strip(),
        }


# ---------------------------------------------------------------------------
# 单个会话 Tab
# ---------------------------------------------------------------------------
class TerminalSession(QWidget):
    """单个终端会话，包含输出显示和输入框。"""

    def __init__(self, session_type, host, port, parent=None, **kwargs):
        super().__init__(parent)
        self.session_type = session_type  # 'ssh' 或 'telnet'
        self.host = host
        self.port = port
        self.username = kwargs.get('username', '')
        self.password = kwargs.get('password', '')
        self.worker = None
        self.connected = False
        self.prompt = ""
        self.command_buffer = ""
        self.history = []
        self.history_index = -1
        self.init_ui()
        self.start_connection()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(False)
        self.output.setUndoRedoEnabled(False)
        self.output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #000000;
                color: #00ff00;
                border: none;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 6px;
            }
        """)
        font = QFont('Consolas', 12)
        font.setFixedPitch(True)
        self.output.setFont(font)
        self.output.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.output.installEventFilter(self)
        layout.addWidget(self.output, 1)
        self._lock_input_position = True
        self._echo_mode = True

    def start_connection(self):
        self.append_output(f"正在连接 {self.session_type.upper()} {self.host}:{self.port} ...\n")

        if self.session_type == 'ssh':
            if not HAS_PARAMIKO:
                self.append_output("\n⚠️ 未安装 paramiko 库，无法使用 SSH 功能。\n")
                self.append_output("请执行: pip install paramiko\n")
                self.prompt_label.setText("❌ 缺少依赖")
                self.prompt_label.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")
                self.send_btn.setEnabled(False)
                self.input_line.setEnabled(False)
                return
            self.worker = SshWorker(self.host, self.port, self.username, self.password)
        else:
            self.worker = TelnetWorker(self.host, self.port)

        self.worker.output_signal.connect(self.append_output)
        self.worker.connected_signal.connect(self.on_connected)
        self.worker.disconnected_signal.connect(self.on_disconnected)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def _input_start_pos(self):
        """返回用户输入区域的起始位置（text length 减去当前命令长度）。"""
        text = self.output.toPlainText()
        return len(text) - len(self.command_buffer)

    def _ensure_cursor_in_input(self):
        """确保光标在输入区域末尾。"""
        cursor = self.output.textCursor()
        end = self._input_start_pos() + len(self.command_buffer)
        if cursor.position() != end:
            cursor.setPosition(end)
            self.output.setTextCursor(cursor)

    def eventFilter(self, obj, event):
        if obj == self.output:
            if event.type() == QEvent.Type.MouseButtonPress or event.type() == QEvent.Type.MouseButtonDblClick:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._ensure_cursor_in_input)
                return False

            if event.type() == QEvent.Type.KeyPress:
                self._ensure_cursor_in_input()

                if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    if not self.connected:
                        return True
                    if self.command_buffer.strip():
                        self.history.append(self.command_buffer)
                        self.history_index = len(self.history)
                        if self.worker:
                            self.worker.send_command(self.command_buffer)
                    else:
                        if self.worker:
                            self.worker.send_command("")
                    self.output.insertPlainText("\n")
                    self.command_buffer = ""
                    self.output.moveCursor(QTextCursor.MoveOperation.End)
                    return True

                elif event.key() == Qt.Key_Backspace:
                    if self.command_buffer:
                        cursor = self.output.textCursor()
                        cursor.deletePreviousChar()
                        self.command_buffer = self.command_buffer[:-1]
                    return True

                elif event.key() == Qt.Key_Delete:
                    if self.command_buffer:
                        cursor = self.output.textCursor()
                        cursor.deleteChar()
                        pos = cursor.position() - self._input_start_pos()
                        if 0 <= pos < len(self.command_buffer):
                            self.command_buffer = self.command_buffer[:pos] + self.command_buffer[pos+1:]
                    return True

                elif event.key() == Qt.Key_Up:
                    if self.history:
                        self.history_index = max(0, self.history_index - 1)
                        self._replace_command(self.history[self.history_index])
                    return True

                elif event.key() == Qt.Key_Down:
                    if self.history:
                        self.history_index = min(len(self.history), self.history_index + 1)
                        if self.history_index == len(self.history):
                            self._replace_command("")
                        else:
                            self._replace_command(self.history[self.history_index])
                    return True

                elif event.key() == Qt.Key_Left:
                    if self.command_buffer:
                        cursor = self.output.textCursor()
                        cursor.movePosition(QTextCursor.MoveOperation.Left)
                    return True

                elif event.key() == Qt.Key_Right:
                    cursor = self.output.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.Right)
                    return True

                elif event.key() == Qt.Key_Home:
                    cursor = self.output.textCursor()
                    cursor.setPosition(self._input_start_pos())
                    return True

                elif event.key() == Qt.Key_End:
                    cursor = self.output.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    return True

                elif event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                    if self.worker:
                        self.worker.send_command('\x03')
                    self.append_output("[SENT] Ctrl+C")
                    return True

                elif event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
                    if self.worker:
                        self.worker.send_command('\x04')
                    self.append_output("[SENT] Ctrl+D")
                    return True

                elif event.key() == Qt.Key_Z and event.modifiers() == Qt.ControlModifier:
                    if self.worker:
                        self.worker.send_command('\x1a')
                    self.append_output("[SENT] Ctrl+Z")
                    return True

                elif event.key() == Qt.Key_U and event.modifiers() == Qt.ControlModifier:
                    self.command_buffer = ""
                    cursor = self.output.textCursor()
                    cursor.setPosition(self._input_start_pos())
                    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                    return True

                elif event.key() == Qt.Key_W and event.modifiers() == Qt.ControlModifier:
                    words = self.command_buffer.split()
                    if words:
                        self.command_buffer = ' '.join(words[:-1])
                        cursor = self.output.textCursor()
                        cursor.setPosition(self._input_start_pos())
                        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                        cursor.removeSelectedText()
                        cursor.insertText(self.command_buffer)
                    return True

                elif event.key() == Qt.Key_A and event.modifiers() == Qt.ControlModifier:
                    cursor = self.output.textCursor()
                    cursor.setPosition(self._input_start_pos())
                    return True

                elif event.key() == Qt.Key_E and event.modifiers() == Qt.ControlModifier:
                    cursor = self.output.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    return True

                elif event.key() in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock]:
                    pass
                else:
                    char = event.text()
                    if char and char.isprintable():
                        self.command_buffer += char
                        cursor = self.output.textCursor()
                        cursor.insertText(char)
                    return True

        return super().eventFilter(obj, event)

    def _replace_command(self, cmd):
        cursor = self.output.textCursor()
        input_start = self._input_start_pos()

        cursor.setPosition(input_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        self.output.insertPlainText(cmd)
        self.command_buffer = cmd
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def append_output(self, text):
        """插入设备返回数据，正确处理 \\r、\\n、\\r\\n、\\b、ANSI 转义序列。"""
        cursor = self.output.textCursor()
        input_start = self._input_start_pos()

        cursor.setPosition(input_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '\r' and i + 1 < len(text) and text[i + 1] == '\n':
                cursor.insertText('\n')
                i += 2
            elif ch == '\r':
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                i += 1
            elif ch == '\n':
                cursor.insertText('\n')
                i += 1
            elif ch == '\b' or ch == '\x7f':
                cursor.deletePreviousChar()
                i += 1
            elif ch == '\x1b':
                j = i + 1
                while j < len(text) and text[j] not in 'ABCDEFGHJKSTfmnsulh':
                    j += 1
                if j < len(text):
                    i = j + 1
                else:
                    cursor.insertText(ch)
                    i += 1
            else:
                cursor.insertText(ch)
                i += 1

        cursor.insertText(self.command_buffer)
        self.output.setTextCursor(cursor)
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def on_connected(self):
        self.connected = True
        self.append_output(f"\n✅ 连接成功!\n")

    def on_disconnected(self, reason):
        self.connected = False
        self.append_output(f"\n⚠️ {reason}\n")

    def on_error(self, error_msg):
        self.append_output(f"\n❌ {error_msg}\n")

    def stop(self):
        """停止会话线程。"""
        if self.worker:
            try:
                self.worker.output_signal.disconnect(self.append_output)
                self.worker.connected_signal.disconnect(self.on_connected)
                self.worker.disconnected_signal.disconnect(self.on_disconnected)
                self.worker.error_signal.disconnect(self.on_error)
            except Exception:
                pass
            self.worker.stop()
            self.worker = None


# ---------------------------------------------------------------------------
# 主页面
# ---------------------------------------------------------------------------
class RemoteTerminalPage(QWidget):
    """远程终端页面，管理多个 SSH/Telnet 会话。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.sessions = {}  # tab_index -> TerminalSession
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题栏
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #1e3a5f;
                border: none;
                border-bottom: 1px solid #0d2137;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 8, 15, 8)
        header_layout.setSpacing(10)

        title = QLabel("🖥️ 远程终端  SSH / Telnet 多会话终端")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        ssh_btn = QPushButton("+ SSH 新建")
        ssh_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e90ff;
                color: white;
                border: none;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #1c86ee; }
        """)
        ssh_btn.setCursor(Qt.PointingHandCursor)
        ssh_btn.clicked.connect(self.new_ssh_session)
        header_layout.addWidget(ssh_btn)

        telnet_btn = QPushButton("+ Telnet 新建")
        telnet_btn.setStyleSheet("""
            QPushButton {
                background-color: #90ee90;
                color: #333;
                border: none;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7ccd7c; }
        """)
        telnet_btn.setCursor(Qt.PointingHandCursor)
        telnet_btn.clicked.connect(self.new_telnet_session)
        header_layout.addWidget(telnet_btn)

        layout.addWidget(header)

        # TabWidget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #1e2937;
            }
            QTabBar::tab {
                background-color: #34495e;
                color: #bdc3c7;
                padding: 8px 20px;
                border: 1px solid #2c3e50;
                border-bottom: none;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background-color: #1e2937;
                color: #ecf0f1;
            }
            QTabBar::tab:hover {
                background-color: #2c3e50;
                color: #ecf0f1;
            }
        """)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        layout.addWidget(self.tabs, 1)

        # 添加欢迎 Tab
        self.add_welcome_tab()

    def add_welcome_tab(self):
        welcome = QWidget()
        welcome.setStyleSheet("background-color: #1e2937;")
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setAlignment(Qt.AlignCenter)
        welcome_layout.setSpacing(20)

        icon_label = QLabel("🔌")
        icon_label.setStyleSheet("font-size: 72px; color: #3498db;")
        icon_label.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(icon_label)

        title = QLabel("远程工具箱")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #ecf0f1;")
        title.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(title)

        desc = QLabel(
            "支持 SSH / Telnet 多会话并行连接\n"
            "点击右上角「+ SSH 新建」或「+ Telnet 新建」开始"
        )
        desc.setStyleSheet("font-size: 13px; color: #95a5a6; line-height: 1.6;")
        desc.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(desc)

        self.tabs.addTab(welcome, "🏠 欢迎")

    def new_ssh_session(self):
        if not HAS_PARAMIKO:
            QMessageBox.warning(
                self, "缺少依赖",
                "未安装 paramiko 库，无法使用 SSH 功能。\n\n请执行:\npip install paramiko"
            )
            return

        dialog = SshConnectDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        name = f"{data['username']}@{data['host']}:{data['port']}"

        session = TerminalSession(
            'ssh', data['host'], data['port'],
            self, username=data['username'], password=data['password']
        )

        index = self.tabs.addTab(session, name)
        self.tabs.setCurrentIndex(index)
        self.sessions[index] = session

    def new_telnet_session(self):
        dialog = TelnetConnectDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        name = data['name'] or f"Telnet {data['host']}:{data['port']}"

        session = TerminalSession(
            'telnet', data['host'], data['port'], self
        )

        index = self.tabs.addTab(session, name)
        self.tabs.setCurrentIndex(index)
        self.sessions[index] = session

    def close_tab(self, index):
        """关闭指定 Tab。"""
        if index == 0:
            # 欢迎页不允许关闭
            return

        if index in self.sessions:
            session = self.sessions.pop(index)
            session.stop()

        self.tabs.removeTab(index)

        # 重建索引映射
        new_sessions = {}
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            for old_idx, sess in list(self.sessions.items()):
                if sess is widget:
                    new_sessions[i] = sess
                    break
        self.sessions = new_sessions

        # 如果没有会话只剩欢迎页，保持欢迎页
        if self.tabs.count() == 0:
            self.add_welcome_tab()

    def cleanup(self):
        """关闭所有连接和线程，供页面切换时调用。"""
        for session in list(self.sessions.values()):
            session.stop()
        self.sessions.clear()

    def hideEvent(self, event):
        self.cleanup()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
