import os
import json
import subprocess
import tempfile
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QFrame,
    QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.core.logger import Logger

logger = Logger("RemoteDesktop")


class RemoteDesktopPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.history_data = []
        self.history_file = self._get_history_path()
        self.init_ui()
        self.load_history()

    def _get_history_path(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "rdp_history.json")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 标题栏
        title_label = QLabel("🖥️ RDP 远程桌面  Windows 远程桌面一键启动")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)

        # 主体区域：左右分割
        main_layout = QHBoxLayout()
        main_layout.setSpacing(15)

        # ====== 左侧：连接参数 ======
        left_frame = QFrame()
        left_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
            }
        """)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(12)

        left_title = QLabel("🔗 连接参数")
        left_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        left_title.setStyleSheet("color: #00bcd4;")
        left_layout.addWidget(left_title)

        form_grid = QGridLayout()
        form_grid.setSpacing(10)
        form_grid.setColumnStretch(1, 1)

        # 主机/IP
        form_grid.addWidget(QLabel("主机 / IP:"), 0, 0)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("例如: 192.168.1.100")
        self.host_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #fafafa;
                font-size: 12px;
            }
        """)
        form_grid.addWidget(self.host_input, 0, 1)

        # 端口
        form_grid.addWidget(QLabel("端口:"), 1, 0)
        self.port_input = QLineEdit("3389")
        self.port_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #fafafa;
                font-size: 12px;
            }
        """)
        form_grid.addWidget(self.port_input, 1, 1)

        # 用户名
        form_grid.addWidget(QLabel("用户名:"), 2, 0)
        self.username_input = QLineEdit("Administrator")
        self.username_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #fafafa;
                font-size: 12px;
            }
        """)
        form_grid.addWidget(self.username_input, 2, 1)

        # 密码
        form_grid.addWidget(QLabel("密码:"), 3, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("可选")
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #fafafa;
                font-size: 12px;
            }
        """)
        form_grid.addWidget(self.password_input, 3, 1)

        left_layout.addLayout(form_grid)

        # 提示文字
        hint_label = QLabel("💡 提示：密码可留空，mstsc 会弹出输入框")
        hint_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px 0;")
        left_layout.addWidget(hint_label)

        # 分辨率
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["全屏", "1024x768", "1280x720", "1366x768", "1920x1080"])
        self.resolution_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        res_layout.addWidget(self.resolution_combo, 1)
        left_layout.addLayout(res_layout)

        left_layout.addStretch()

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.connect_btn = QPushButton("🖥️ 连接")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self.on_connect)
        btn_layout.addWidget(self.connect_btn)

        self.clear_btn = QPushButton("🧹 清空")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.on_clear_form)
        btn_layout.addWidget(self.clear_btn)

        left_layout.addLayout(btn_layout)

        main_layout.addWidget(left_frame, 1)

        # ====== 右侧：连接历史 ======
        right_frame = QFrame()
        right_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
            }
        """)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(12)

        right_title = QLabel("📋 连接历史")
        right_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        right_title.setStyleSheet("color: #00bcd4;")
        right_layout.addWidget(right_title)

        # 操作按钮行
        history_btn_layout = QHBoxLayout()
        history_btn_layout.setSpacing(10)

        self.hist_connect_btn = QPushButton("🔗 连接选中")
        self.hist_connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.hist_connect_btn.setCursor(Qt.PointingHandCursor)
        self.hist_connect_btn.clicked.connect(self.on_connect_selected)
        history_btn_layout.addWidget(self.hist_connect_btn)

        self.hist_fill_btn = QPushButton("📋 填入表单")
        self.hist_fill_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #e67e22; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.hist_fill_btn.setCursor(Qt.PointingHandCursor)
        self.hist_fill_btn.clicked.connect(self.on_fill_form)
        history_btn_layout.addWidget(self.hist_fill_btn)

        self.hist_delete_btn = QPushButton("🗑️ 删除选中")
        self.hist_delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        self.hist_delete_btn.setCursor(Qt.PointingHandCursor)
        self.hist_delete_btn.clicked.connect(self.on_delete_selected)
        history_btn_layout.addWidget(self.hist_delete_btn)

        history_btn_layout.addStretch()
        right_layout.addLayout(history_btn_layout)

        # 历史表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["主机/IP", "端口", "用户名", "最近连接"])
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SingleSelection)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setStyleSheet("""
            QTableWidget {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                gridline-color: #e0e0e0;
                font-family: "Microsoft YaHei";
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.history_table.doubleClicked.connect(self.on_table_double_click)
        right_layout.addWidget(self.history_table, 1)

        # 底部提示
        bottom_hint = QLabel("双击历史记录直接连接")
        bottom_hint.setStyleSheet("color: #888; font-size: 11px; padding: 4px 0;")
        bottom_hint.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(bottom_hint)

        main_layout.addWidget(right_frame, 2)
        layout.addLayout(main_layout, 1)

    def on_connect(self):
        host = self.host_input.text().strip()
        port = self.port_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        resolution = self.resolution_combo.currentText()

        if not host:
            QMessageBox.warning(self, "提示", "请输入主机/IP地址")
            return

        if not port:
            port = "3389"

        try:
            self._launch_rdp(host, port, username, password, resolution)
            self._add_or_update_history(host, port, username)
        except Exception as e:
            logger.error(f"RDP连接失败: {e}")
            QMessageBox.critical(self, "错误", f"启动远程桌面失败: {e}")

    def _launch_rdp(self, host, port, username, password, resolution):
        # 如果只填写了主机/IP（没有用户名和密码），直接执行 mstsc /v:host:port
        if not username and not password:
            cmd = f"mstsc /v:{host}:{port}"
            subprocess.Popen(cmd, shell=True)
            return

        # 生成临时 .rdp 文件
        rdp_content = f"""full address:s:{host}:{port}
        username:s:{username}
        """

        # 分辨率设置
        if resolution == "全屏":
            rdp_content += "screen mode id:i:2\n"
        else:
            rdp_content += "screen mode id:i:1\n"
            width, height = resolution.split("x")
            rdp_content += f"desktopwidth:i:{width}\n"
            rdp_content += f"desktopheight:i:{height}\n"

        # 如果填写了密码，需要编码（mstsc 支持密码加密存储，但这里我们留空让系统处理更安全）
        # 实际上 mstsc 的 .rdp 文件密码需要特殊加密，普通文本无法直接使用
        # 所以即使填写了密码，也不写入 rdp 文件，仍然让用户在弹窗中输入
        # 但保留用户名

        rdp_content += "autoreconnection enabled:i:1\n"
        rdp_content += "redirectclipboard:i:1\n"
        rdp_content += "redirectprinters:i:1\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".rdp", delete=False, encoding="utf-8") as f:
            f.write(rdp_content)
            temp_path = f.name

        try:
            subprocess.Popen(f"mstsc \"{temp_path}\"", shell=True)
        except Exception:
            os.unlink(temp_path)
            raise

        # 延迟清理临时文件
        from PySide6.QtCore import QTimer
        QTimer.singleShot(30000, lambda: self._safe_remove(temp_path))

    def _safe_remove(self, path):
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass

    def _add_or_update_history(self, host, port, username):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        key = (host, port, username)

        # 查找是否已有记录
        for item in self.history_data:
            if (item.get("host"), item.get("port"), item.get("username")) == key:
                item["last_connected"] = now
                self.save_history()
                self.refresh_table()
                return

        # 新增记录
        self.history_data.append({
            "host": host,
            "port": port,
            "username": username,
            "last_connected": now
        })
        self.save_history()
        self.refresh_table()

    def on_clear_form(self):
        self.host_input.clear()
        self.port_input.setText("3389")
        self.username_input.setText("Administrator")
        self.password_input.clear()
        self.resolution_combo.setCurrentIndex(0)

    def on_connect_selected(self):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一条历史记录")
            return
        self._connect_from_row(row)

    def on_fill_form(self):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一条历史记录")
            return

        host = self.history_table.item(row, 0).text()
        port = self.history_table.item(row, 1).text()
        username = self.history_table.item(row, 2).text()

        self.host_input.setText(host)
        self.port_input.setText(port)
        self.username_input.setText(username)
        self.password_input.clear()

    def on_delete_selected(self):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一条历史记录")
            return

        reply = QMessageBox.question(
            self, "确认", "确定要删除选中的历史记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if 0 <= row < len(self.history_data):
                self.history_data.pop(row)
                self.save_history()
                self.refresh_table()

    def on_table_double_click(self, index):
        row = index.row()
        if row >= 0:
            self._connect_from_row(row)

    def _connect_from_row(self, row):
        if row < 0 or row >= len(self.history_data):
            return
        item = self.history_data[row]
        host = item.get("host", "")
        port = item.get("port", "3389")
        username = item.get("username", "")
        resolution = self.resolution_combo.currentText()

        if not host:
            return

        try:
            self._launch_rdp(host, port, username, "", resolution)
            self._add_or_update_history(host, port, username)
        except Exception as e:
            logger.error(f"RDP连接失败: {e}")
            QMessageBox.critical(self, "错误", f"启动远程桌面失败: {e}")

    def load_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history_data = json.load(f)
                    if not isinstance(self.history_data, list):
                        self.history_data = []
        except Exception as e:
            logger.error(f"加载RDP历史失败: {e}")
            self.history_data = []
        self.refresh_table()

    def save_history(self):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存RDP历史失败: {e}")

    def refresh_table(self):
        self.history_table.setRowCount(len(self.history_data))
        for i, item in enumerate(self.history_data):
            self.history_table.setItem(i, 0, QTableWidgetItem(item.get("host", "")))
            self.history_table.setItem(i, 1, QTableWidgetItem(str(item.get("port", ""))))
            self.history_table.setItem(i, 2, QTableWidgetItem(item.get("username", "")))
            self.history_table.setItem(i, 3, QTableWidgetItem(item.get("last_connected", "")))

    def cleanup(self):
        pass

    def stop_update_timer(self):
        self.cleanup()
