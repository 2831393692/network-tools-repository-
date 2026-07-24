"""串口调试页面 - 支持多会话串口通信

本页面使用 pyserial 进行串口通信，通过 QThread 后台读取串口数据，
避免阻塞 UI 主线程。页面切换时会调用 cleanup() 关闭所有串口和线程。
"""
import re
import time
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTabWidget,
    QPlainTextEdit, QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QEvent
from PySide6.QtGui import QFont, QTextCursor

from app.core.logger import Logger

logger = Logger("SerialDebug")


# ---------------------------------------------------------------------------
# 串口读取后台线程
# ---------------------------------------------------------------------------
class SerialReadThread(QThread):
    data_signal = Signal(bytes)
    error_signal = Signal(str)
    disconnected_signal = Signal()

    def __init__(self, ser):
        super().__init__()
        self.ser = ser
        self._running = True

    def run(self):
        while self._running and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    if data:
                        self.data_signal.emit(data)
                else:
                    time.sleep(0.02)
            except serial.SerialException as e:
                self.error_signal.emit(f"串口异常: {e}")
                break
            except Exception as e:
                self.error_signal.emit(f"读取错误: {e}")
                break
        self.disconnected_signal.emit()

    def stop(self):
        self._running = False


# ---------------------------------------------------------------------------
# 单个串口会话 Widget
# ---------------------------------------------------------------------------
class SerialSession(QWidget):
    def __init__(self, port_name, page=None, parent=None):
        super().__init__(parent)
        self.port_name = port_name
        self.page = page
        self.ser = None
        self.read_thread = None
        self.command_buffer = ""
        self.history = []
        self.history_index = -1
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #1e3a5f;
                border: none;
                border-bottom: 1px solid #0d2137;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        self.port_label = QLabel(f"📶 {self.port_name}")
        self.port_label.setStyleSheet("color: #87ceeb; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.port_label)

        header_layout.addStretch()

        self.clear_btn = QPushButton("🗑️ 清屏")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #b0bec5;
                border: none;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.1);
                color: white;
            }
        """)
        self.clear_btn.clicked.connect(self.clear_screen)
        header_layout.addWidget(self.clear_btn)

        self.close_btn = QPushButton("✖ 关闭")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #b0bec5;
                border: none;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.1);
                color: white;
            }
        """)
        self.close_btn.clicked.connect(self.on_close)
        header_layout.addWidget(self.close_btn)

        self.disconnect_btn = QPushButton("🔴 断开")
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #e53935;
                color: white;
                border: none;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
            QPushButton:disabled {
                background-color: #757575;
            }
        """)
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        header_layout.addWidget(self.disconnect_btn)

        self.status_label = QLabel("❌ 未连接")
        self.status_label.setStyleSheet("color: #e53935; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(self.status_label)

        layout.addWidget(header_frame)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(False)
        self.output.setUndoRedoEnabled(False)
        self.output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d2137;
                color: #00ff00;
                font-family: Consolas, Monaco, 'Courier New', monospace;
                font-size: 12px;
                border: none;
                padding: 6px;
            }
        """)
        font = QFont('Consolas', 12)
        font.setFixedPitch(True)
        self.output.setFont(font)
        self.output.installEventFilter(self)
        layout.addWidget(self.output, 1)

    def clear_screen(self):
        self.output.clear()
        self.command_buffer = ""

    def on_close(self):
        if self.page:
            for i in range(self.page.tabs.count()):
                if self.page.tabs.widget(i) == self:
                    self.page.close_tab(i)
                    break

    def on_disconnect(self):
        self.close_serial()
        self.status_label.setText("❌ 已断开")
        self.status_label.setStyleSheet("color: #e53935; font-size: 11px; font-weight: bold;")

    def _input_start_pos(self):
        """返回用户输入区域的起始位置。

        由于我们依赖设备回显，所有显示的内容都是设备返回的，
        所以输入起始位置就是文本末尾。"""
        text = self.output.toPlainText()
        return len(text)

    def _ensure_cursor_in_input(self):
        """确保光标在输入区域末尾。"""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
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
                    if not self.ser or not self.ser.is_open:
                        return True
                    if self.command_buffer.strip():
                        self.history.append(self.command_buffer)
                        self.history_index = len(self.history)
                    newline = ""
                    if self.page and hasattr(self.page, 'current_newline'):
                        newline = self.page.current_newline
                    if newline and self.ser and self.ser.is_open:
                        try:
                            self.ser.write(newline.encode('utf-8'))
                        except Exception:
                            pass
                    self.command_buffer = ""
                    return True

                elif event.key() == Qt.Key_Backspace:
                    if self.command_buffer:
                        self.command_buffer = self.command_buffer[:-1]
                        if self.ser and self.ser.is_open:
                            try:
                                self.ser.write(b'\x08')
                            except Exception:
                                pass
                    return True

                elif event.key() == Qt.Key_Delete:
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
                    return True

                elif event.key() == Qt.Key_Right:
                    return True

                elif event.key() == Qt.Key_Home:
                    return True

                elif event.key() == Qt.Key_End:
                    return True

                elif event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
                    if self.ser and self.ser.is_open:
                        self.ser.write(b'\x03')
                    self._insert_at_end("[SENT] Ctrl+C")
                    return True

                elif event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
                    if self.ser and self.ser.is_open:
                        self.ser.write(b'\x04')
                    self._insert_at_end("[SENT] Ctrl+D")
                    return True

                elif event.key() == Qt.Key_Z and event.modifiers() == Qt.ControlModifier:
                    if self.ser and self.ser.is_open:
                        self.ser.write(b'\x1a')
                    self._insert_at_end("[SENT] Ctrl+Z")
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
                        if self.ser and self.ser.is_open:
                            try:
                                self.ser.write(char.encode('utf-8'))
                            except Exception:
                                pass
                    return True

        return super().eventFilter(obj, event)

    def _replace_command(self, cmd):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(cmd)
        self.command_buffer = cmd
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _insert_at_end(self, text):
        """在末尾插入接收到的数据。

        处理以下控制字符：
        - \\r\\n : 回车+换行（转换为换行）
        - \\r : 忽略（由 \\n 处理换行）
        - \\n : 换行（连续多个换行只保留一个）
        - \\b : 退格（删除前一个字符）
        - \\x1b[...m : ANSI 颜色控制序列（过滤掉）"""
        text = text.replace('\r\n', '\n').replace('\r', '')
        text = re.sub(r'\n+', '\n', text)

        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '\n':
                cursor.insertText('\n')
                i += 1
            elif ch == '\b':
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

        self.output.setTextCursor(cursor)
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def append_data(self, data):
        """追加接收到的原始数据（bytes），尝试以 UTF-8 解码，失败则转十六进制。

        注意：串口设备通常会回显用户输入的内容，所以这里不加时间戳前缀，
        避免与设备回显的内容混在一起。
        同时处理 \\r\\n：\\r 用于光标回到行首（不回显换行），\\r\\n 才换行。"""
        try:
            text = data.decode('utf-8', errors='replace')
        except Exception:
            text = data.hex(' ')
        # 将单独的 \r 视为普通字符（不换行），保留 \n 和 \r\n 换行
        # 这样设备的回显会保持在一行
        self._insert_at_end(text)

    def append_info(self, text):
        self._insert_at_end(f"[INFO] {text}\n")

    def append_error(self, text):
        self._insert_at_end(f"[ERROR] {text}\n")

    def send_data(self, text=None):
        if text is None:
            text = self.command_buffer

        if not text and self.command_buffer is None:
            return

        if not self.ser or not self.ser.is_open:
            self._insert_at_end("[ERROR] 串口未打开")
            return

        newline = ""
        if self.page and hasattr(self.page, 'current_newline'):
            newline = self.page.current_newline

        try:
            data = text.encode('utf-8')
            if newline:
                data += newline.encode('utf-8')
            self.ser.write(data)
        except Exception as e:
            self._insert_at_end(f"[ERROR] 发送失败: {e}")

    def close_serial(self):
        if self.read_thread:
            self.read_thread.stop()
            self.read_thread.wait(1000)
            self.read_thread = None
        if self.ser:
            try:
                if self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None


# ---------------------------------------------------------------------------
# 主页面
# ---------------------------------------------------------------------------
class SerialDebugPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions = {}  # port_name -> SerialSession
        self.current_newline = "\r\n"
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 页面标题
        title_label = QLabel("🔌 串口调试终端   Serial Console — 支持多会话")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                font-family: "Microsoft YaHei";
                padding-bottom: 6px;
            }
        """)
        main_layout.addWidget(title_label)

        # 顶部参数设置栏
        self._build_toolbar(main_layout)

        # Tab 主体
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f5f5f5;
                color: #555;
                padding: 8px 20px;
                border: 1px solid #e0e0e0;
                border-bottom: none;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
                min-width: 80px;
            }
            QTabBar::tab:selected {
                background-color: #00bcd4;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #4dd0e1;
                color: white;
            }
            QTabBar::close-button {
                image: none;
                subcontrol-position: right;
            }
        """)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        main_layout.addWidget(self.tabs, 1)

        # 添加欢迎页
        self._build_welcome_tab()

        if not SERIAL_AVAILABLE:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._show_pyserial_warning)

    def _show_pyserial_warning(self):
        """显示 pyserial 缺少依赖的警告（延迟调用，避免阻塞启动）。"""
        QMessageBox.warning(
            self, "缺少依赖",
            "未检测到 pyserial 库，串口功能不可用。\n\n"
            "请执行以下命令安装：\n"
            "  pip install pyserial\n\n"
            "安装后重新打包即可正常使用串口功能。"
        )

    def _build_toolbar(self, parent_layout):
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
            }
        """)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # 串口
        layout.addWidget(QLabel("串口:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(90)
        self._refresh_ports()
        layout.addWidget(self.port_combo)

        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("刷新串口列表")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 1px solid #ccc;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f5f5f5; }
        """)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_ports)
        layout.addWidget(refresh_btn)

        layout.addSpacing(10)

        # 波特率
        layout.addWidget(QLabel("波特率:"))
        self.baud_combo = QComboBox()
        baud_rates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
        for b in baud_rates:
            self.baud_combo.addItem(str(b), b)
        self.baud_combo.setCurrentIndex(3)  # 9600
        self.baud_combo.setMinimumWidth(80)
        layout.addWidget(self.baud_combo)

        layout.addSpacing(10)

        # 数据位
        layout.addWidget(QLabel("数据位:"))
        self.data_bits_combo = QComboBox()
        for db in [5, 6, 7, 8]:
            self.data_bits_combo.addItem(str(db), db)
        self.data_bits_combo.setCurrentIndex(3)  # 8
        self.data_bits_combo.setMinimumWidth(60)
        layout.addWidget(self.data_bits_combo)

        layout.addSpacing(10)

        # 停止位
        layout.addWidget(QLabel("停止位:"))
        self.stop_bits_combo = QComboBox()
        stop_bits_map = [
            ("1", serial.STOPBITS_ONE if SERIAL_AVAILABLE else 1),
            ("1.5", serial.STOPBITS_ONE_POINT_FIVE if SERIAL_AVAILABLE else 1.5),
            ("2", serial.STOPBITS_TWO if SERIAL_AVAILABLE else 2),
        ]
        for label, val in stop_bits_map:
            self.stop_bits_combo.addItem(label, val)
        layout.addWidget(self.stop_bits_combo)

        layout.addSpacing(10)

        # 校验
        layout.addWidget(QLabel("校验:"))
        self.parity_combo = QComboBox()
        parity_map = [
            ("None", serial.PARITY_NONE if SERIAL_AVAILABLE else 'N'),
            ("Even", serial.PARITY_EVEN if SERIAL_AVAILABLE else 'E'),
            ("Odd", serial.PARITY_ODD if SERIAL_AVAILABLE else 'O'),
            ("Mark", serial.PARITY_MARK if SERIAL_AVAILABLE else 'M'),
            ("Space", serial.PARITY_SPACE if SERIAL_AVAILABLE else 'S'),
        ]
        for label, val in parity_map:
            self.parity_combo.addItem(label, val)
        layout.addWidget(self.parity_combo)

        layout.addSpacing(10)

        # 回车
        layout.addWidget(QLabel("回车:"))
        self.newline_combo = QComboBox()
        self.newline_map = {
            "CR+LF": "\r\n",
            "CR": "\r",
            "LF": "\n",
            "None": "",
        }
        for label, val in self.newline_map.items():
            self.newline_combo.addItem(label, val)
        self.newline_combo.currentIndexChanged.connect(self._on_newline_changed)
        layout.addWidget(self.newline_combo)

        layout.addSpacing(10)

        # 快速预设
        layout.addWidget(QLabel("快速预设:"))
        self.preset_combo = QComboBox()
        presets = [
            ("自定义", None),
            ("华为/Cisco Console", {"baud": 9600, "data": 8, "stop": 1, "parity": "None"}),
            ("H3C Console", {"baud": 9600, "data": 8, "stop": 1, "parity": "None"}),
            ("Linux ttyUSB", {"baud": 115200, "data": 8, "stop": 1, "parity": "None"}),
            ("工控/PLC", {"baud": 9600, "data": 7, "stop": 1, "parity": "Even"}),
            ("9600-8N1", {"baud": 9600, "data": 8, "stop": 1, "parity": "None"}),
            ("115200-8N1", {"baud": 115200, "data": 8, "stop": 1, "parity": "None"}),
            ("9600-7E1", {"baud": 9600, "data": 7, "stop": 1, "parity": "Even"}),
        ]
        for label, cfg in presets:
            self.preset_combo.addItem(label, cfg)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.preset_combo)

        layout.addSpacing(15)

        # 连接按钮
        self.connect_btn = QPushButton("🔌 连接")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self.on_connect)
        layout.addWidget(self.connect_btn)

        layout.addStretch()
        parent_layout.addWidget(toolbar)

    def _build_welcome_tab(self):
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        welcome.setStyleSheet("background-color: #0f172a;")

        icon_label = QLabel("🔧")
        icon_label.setFont(QFont("Microsoft YaHei", 72))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("color: #00bcd4;")
        layout.addWidget(icon_label)

        title = QLabel("串口调试终端")
        title.setFont(QFont("Microsoft YaHei", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #e2e8f0;")
        layout.addWidget(title)

        desc = QLabel(
            "1. 选择串口和参数（默认 9600-8N1）<br>"
            "2. 选择快速预设 或 手动设置参数<br>"
            "3. 点击「🔌 连接」按钮打开会话<br>"
            "4. 支持多个串口同时连接"
        )
        desc.setFont(QFont("Microsoft YaHei", 12))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #94a3b8; line-height: 1.8;")
        desc.setTextFormat(Qt.RichText)
        layout.addWidget(desc)

        layout.addStretch()
        self.tabs.addTab(welcome, "🏠 欢迎")

    def _refresh_ports(self):
        self.port_combo.clear()
        if SERIAL_AVAILABLE:
            ports = serial.tools.list_ports.comports()
            port_names = []
            for p in sorted(ports):
                name = p.device
                desc = p.description
                self.port_combo.addItem(f"{name} ({desc})", name)
                port_names.append(name)
            # 如果系统未检测到，至少保留 COM1-COM20 选项
            if not port_names:
                for i in range(1, 21):
                    self.port_combo.addItem(f"COM{i}", f"COM{i}")
            # 尝试选中 COM3
            idx = self.port_combo.findData("COM3")
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)
        else:
            for i in range(1, 21):
                self.port_combo.addItem(f"COM{i}", f"COM{i}")
            self.port_combo.setCurrentIndex(2)  # COM3

    def _on_newline_changed(self):
        self.current_newline = self.newline_combo.currentData() or ""

    def _on_preset_changed(self):
        cfg = self.preset_combo.currentData()
        if not cfg:
            return
        # 波特率
        idx = self.baud_combo.findData(cfg["baud"])
        if idx >= 0:
            self.baud_combo.setCurrentIndex(idx)
        # 数据位
        idx = self.data_bits_combo.findData(cfg["data"])
        if idx >= 0:
            self.data_bits_combo.setCurrentIndex(idx)
        # 停止位
        target_stop = str(cfg["stop"])
        for i in range(self.stop_bits_combo.count()):
            if self.stop_bits_combo.itemText(i) == target_stop:
                self.stop_bits_combo.setCurrentIndex(i)
                break
        # 校验
        idx = self.parity_combo.findText(cfg["parity"])
        if idx >= 0:
            self.parity_combo.setCurrentIndex(idx)

    def on_connect(self):
        if not SERIAL_AVAILABLE:
            QMessageBox.warning(self, "提示", "pyserial 未安装，无法打开串口。")
            return

        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "提示", "请选择串口")
            return

        # 如果已经连接该串口，切换到对应 Tab
        if port in self.sessions:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == port:
                    self.tabs.setCurrentIndex(i)
                    return

        baud = self.baud_combo.currentData()
        data_bits = self.data_bits_combo.currentData()
        stop_bits = self.stop_bits_combo.currentData()
        parity = self.parity_combo.currentData()

        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=data_bits,
                stopbits=stop_bits,
                parity=parity,
                timeout=0.5,
                write_timeout=1,
            )
        except serial.SerialException as e:
            err_msg = str(e)
            if "PermissionError" in err_msg or "拒绝访问" in err_msg:
                QMessageBox.critical(
                    self, "连接失败",
                    f"无法打开 {port}\n\n"
                    f"原因: 串口被其他程序占用或没有访问权限\n\n"
                    f"解决方法:\n"
                    f"1. 关闭其他使用该串口的程序（如 SecureCRT、Putty、WindTerm 等）\n"
                    f"2. 检查串口是否被正确识别\n"
                    f"3. 以管理员身份运行本程序"
                )
            else:
                QMessageBox.critical(self, "连接失败", f"无法打开 {port}:\n{e}")
            logger.error(f"打开串口 {port} 失败: {e}")
            return
        except Exception as e:
            QMessageBox.critical(self, "连接失败", f"打开 {port} 时发生错误:\n{e}")
            logger.error(f"打开串口 {port} 错误: {e}")
            return

        session = SerialSession(port, page=self)
        session.ser = ser
        self.sessions[port] = session

        # 启动读取线程
        thread = SerialReadThread(ser)
        thread.data_signal.connect(session.append_data)
        thread.error_signal.connect(session.append_error)
        thread.disconnected_signal.connect(lambda: self._on_session_closed(port))
        session.read_thread = thread
        thread.start()

        session.append_info(
            f"已连接到 {port} | 波特率: {baud} | 数据位: {data_bits} | "
            f"停止位: {self.stop_bits_combo.currentText()} | 校验: {self.parity_combo.currentText()}"
        )

        session.status_label.setText(f"✅ 已连接 {port}")
        session.status_label.setStyleSheet("color: #4caf50; font-size: 11px; font-weight: bold;")

        idx = self.tabs.addTab(session, port)
        self.tabs.setCurrentIndex(idx)

    def _on_session_closed(self, port):
        """串口断开时的回调（线程信号触发）。"""
        if port in self.sessions:
            session = self.sessions[port]
            session.append_info("串口连接已断开")
            session.read_thread = None

    def close_tab(self, index):
        """关闭指定 Tab，如果是欢迎页则不处理。"""
        tab_text = self.tabs.tabText(index)
        if tab_text.startswith("🏠"):
            return

        port = tab_text
        if port in self.sessions:
            session = self.sessions.pop(port)
            session.close_serial()

        self.tabs.removeTab(index)

    def cleanup(self):
        """关闭所有串口和线程，供页面切换时调用。"""
        for port, session in list(self.sessions.items()):
            try:
                if session.read_thread:
                    session.read_thread.stop()
                    session.read_thread.wait(1500)
                    try:
                        session.read_thread.data_signal.disconnect()
                    except Exception:
                        pass
                    try:
                        session.read_thread.error_signal.disconnect()
                    except Exception:
                        pass
                    try:
                        session.read_thread.disconnected_signal.disconnect()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                if session.ser and session.ser.is_open:
                    session.ser.close()
            except Exception:
                pass

        self.sessions.clear()

    def stop_all(self):
        self.cleanup()

    def stop_update_timer(self):
        self.cleanup()
