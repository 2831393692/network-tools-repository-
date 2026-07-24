"""
远程终端页面 - 集成SFTP文件管理器

功能：
1. SSH终端连接和命令执行
2. 远程文件浏览（目录树 + 文件列表）
3. 文件操作（上传、下载、删除、重命名、新建文件夹）
4. 拖拽上传支持
5. 传输进度显示
"""
import os
import sys
import re
import threading
import paramiko
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QLineEdit, QPushButton, QPlainTextEdit,
    QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu, QFileDialog,
    QMessageBox, QProgressDialog, QGroupBox, QToolBar,
    QSizePolicy, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QThread, QEvent, QMimeData
from PySide6.QtGui import QFont, QColor, QTextCursor, QIcon, QAction, QKeyEvent, QTextCharFormat

from app.core.sftp_manager import SftpManager, SftpFileInfo, TransferThread

ANSI_ESCAPE_PATTERN = re.compile(
    r'\x1B\[[0-?]*[ -/]*[@-~]'
    r'|\x1B\]0;[^\x07]*\x07'
)

OCTAL_ESCAPE_PATTERN = re.compile(r"\$'([^']+)'")


def _decode_octal_escape(match):
    escaped = match.group(1)
    result = []
    i = 0
    while i < len(escaped):
        if escaped[i] == '\\' and i + 1 < len(escaped):
            if escaped[i+1] in '01234567':
                octal_start = i + 1
                while octal_start < len(escaped) and escaped[octal_start] in '01234567':
                    octal_start += 1
                octal_str = escaped[i+1:octal_start]
                try:
                    result.append(chr(int(octal_str, 8)))
                except ValueError:
                    result.append(escaped[i])
                    result.append(escaped[i+1])
                i = octal_start
                continue
            elif escaped[i+1] == '\\':
                result.append('\\')
                i += 2
                continue
            elif escaped[i+1] == "'":
                result.append("'")
                i += 2
                continue
            elif escaped[i+1] == 'n':
                result.append('\n')
                i += 2
                continue
            elif escaped[i+1] == 't':
                result.append('\t')
                i += 2
                continue
        result.append(escaped[i])
        i += 1
    return ''.join(result)


class SshWorker(QThread):
    connected = Signal(paramiko.SSHClient)
    disconnected = Signal()
    error = Signal(str)
    output = Signal(str)

    def __init__(self):
        super().__init__()
        self.client = None
        self.host = None
        self.port = 22
        self.username = None
        self.password = None
        self.pkey = None
        self.channel = None
        self._running = False

    def set_params(self, host, port, username, password=None, pkey=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.pkey = pkey

    def run(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if self.pkey:
                self.client.connect(
                    self.host, port=self.port,
                    username=self.username, pkey=self.pkey,
                    timeout=10, banner_timeout=10, auth_timeout=10
                )
            else:
                self.client.connect(
                    self.host, port=self.port,
                    username=self.username, password=self.password,
                    timeout=10, banner_timeout=10, auth_timeout=10
                )
            
            self.connected.emit(self.client)
            self._running = True
            
            self.channel = self.client.invoke_shell()
            self.channel.settimeout(1.0)
            self.channel.set_combine_stderr(True)
            
            while self._running:
                try:
                    if self.channel.recv_ready():
                        data = self.channel.recv(8192)
                        output = self._decode_bytes(data)
                        self.output.emit(output)
                except Exception:
                    pass
                
                if not self._running:
                    break
                
                try:
                    if self.channel.exit_status_ready():
                        break
                except Exception:
                    pass
                
                QThread.msleep(50)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if self.channel:
                try:
                    self.channel.close()
                except Exception:
                    pass
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.disconnected.emit()

    def execute_command(self, command):
        if self.channel and self._running:
            self.channel.send(command + '\n')

    def send_enter(self):
        if self.channel and self._running:
            self.channel.send('\n')

    def stop(self):
        self._running = False

    def _decode_bytes(self, data):
        encodings = ['utf-8', 'gbk', 'gb18030', 'gb2312', 'cp936', 'latin-1']
        for enc in encodings:
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('latin-1', errors='replace')


class TerminalEdit(QPlainTextEdit):
    command_entered = Signal(str)
    enter_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(False)
        self.command_start_pos = 0
        self._buffer = ""
        font = QFont("Consolas", 10)
        self.setFont(font)
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        self._connected = False
        self._last_output_time = 0

    def set_connected(self, connected):
        self._connected = connected

    def append_output(self, text):
        clean_text = ANSI_ESCAPE_PATTERN.sub('', text)
        clean_text = OCTAL_ESCAPE_PATTERN.sub(_decode_octal_escape, clean_text)
        
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(clean_text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self.command_start_pos = cursor.position()

    def keyPressEvent(self, event):
        if not self._connected:
            event.ignore()
            return

        cursor = self.textCursor()
        
        if cursor.position() < self.command_start_pos:
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)

        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            cursor.movePosition(QTextCursor.End)
            cursor.setPosition(self.command_start_pos, QTextCursor.KeepAnchor)
            command = cursor.selectedText()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText('\n')
            self.command_start_pos = cursor.position()
            self.command_entered.emit(command)
            event.accept()
            return
        elif event.key() == Qt.Key_Backspace:
            if cursor.position() <= self.command_start_pos:
                event.ignore()
                return
        elif event.key() == Qt.Key_Left:
            if cursor.position() <= self.command_start_pos:
                event.ignore()
                return
        elif event.key() == Qt.Key_Home:
            cursor.setPosition(self.command_start_pos)
            self.setTextCursor(cursor)
            event.accept()
            return
        elif event.key() == Qt.Key_Up or event.key() == Qt.Key_Down:
            event.ignore()
            return

        super().keyPressEvent(event)


class DropTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            file_paths = []
            for url in urls:
                local_path = url.toLocalFile()
                if os.path.exists(local_path):
                    file_paths.append(local_path)
            if file_paths:
                self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class RemoteTerminalPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sftp_manager = None
        self.transfer_thread = None
        self.ssh_worker = None
        self.sftp = None
        self.ssh_client = None
        self.home_path = '/'
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        self.splitter_main = QSplitter(Qt.Vertical)
        self.main_layout.addWidget(self.splitter_main)

        self.setup_terminal_panel()
        self.setup_file_panel()

        self.setLayout(self.main_layout)

    def setup_terminal_panel(self):
        self.terminal_widget = QWidget()
        self.terminal_layout = QVBoxLayout()
        self.terminal_layout.setContentsMargins(2, 2, 2, 2)

        self.terminal_header = QHBoxLayout()
        self.terminal_header.setContentsMargins(0, 0, 0, 0)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("主机地址")
        self.host_input.setFixedWidth(150)

        self.port_input = QLineEdit("22")
        self.port_input.setFixedWidth(60)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("用户名")
        self.username_input.setFixedWidth(100)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedWidth(120)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.connect_ssh)

        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.clicked.connect(self.disconnect_ssh)
        self.disconnect_btn.setEnabled(False)

        self.terminal_header.addWidget(self.host_input)
        self.terminal_header.addWidget(self.port_input)
        self.terminal_header.addWidget(self.username_input)
        self.terminal_header.addWidget(self.password_input)
        self.terminal_header.addWidget(self.connect_btn)
        self.terminal_header.addWidget(self.disconnect_btn)
        self.terminal_header.addStretch()

        self.terminal_output = TerminalEdit(self)
        self.terminal_output.command_entered.connect(self.send_command)
        self.terminal_output.set_connected(False)

        self.terminal_layout.addLayout(self.terminal_header)
        self.terminal_layout.addWidget(self.terminal_output)

        self.terminal_widget.setLayout(self.terminal_layout)
        self.splitter_main.addWidget(self.terminal_widget)

        self.splitter_main.setStretchFactor(0, 3)

    def setup_file_panel(self):
        self.file_widget = QWidget()
        self.file_layout = QVBoxLayout()
        self.file_layout.setContentsMargins(2, 2, 2, 2)

        self.file_toolbar = QToolBar()
        self.file_toolbar.setFixedHeight(32)

        self.action_upload = QAction("上传", self)
        self.action_upload.triggered.connect(self.upload_files)
        self.file_toolbar.addAction(self.action_upload)

        self.action_download = QAction("下载", self)
        self.action_download.triggered.connect(self.download_files)
        self.file_toolbar.addAction(self.action_download)

        self.action_new_folder = QAction("新建文件夹", self)
        self.action_new_folder.triggered.connect(self.create_new_folder)
        self.file_toolbar.addAction(self.action_new_folder)

        self.action_delete = QAction("删除", self)
        self.action_delete.triggered.connect(self.delete_selected)
        self.file_toolbar.addAction(self.action_delete)

        self.action_refresh = QAction("刷新", self)
        self.action_refresh.triggered.connect(self.refresh_file_list)
        self.file_toolbar.addAction(self.action_refresh)

        self.action_go_up = QAction("返回上级", self)
        self.action_go_up.triggered.connect(self.go_up_directory)
        self.file_toolbar.addAction(self.action_go_up)

        self.file_toolbar.addSeparator()

        self.path_label = QLabel("/")
        self.path_label.setStyleSheet("font-weight: bold; color: #333;")
        self.file_toolbar.addWidget(self.path_label)

        self.file_layout.addWidget(self.file_toolbar)

        self.splitter_file = QSplitter(Qt.Horizontal)

        self.directory_tree = QTreeWidget()
        self.directory_tree.setHeaderHidden(True)
        self.directory_tree.setFixedWidth(200)
        self.directory_tree.itemClicked.connect(self.on_tree_click)
        self.directory_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)

        self.file_table = DropTable()
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels(
            ["文件名", "大小", "类型", "修改时间", "权限"]
        )
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.file_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.doubleClicked.connect(self.on_file_double_clicked)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_file_context_menu)
        self.file_table.files_dropped.connect(self.handle_drop_files)

        self.splitter_file.addWidget(self.directory_tree)
        self.splitter_file.addWidget(self.file_table)
        self.splitter_file.setStretchFactor(0, 1)
        self.splitter_file.setStretchFactor(1, 4)

        self.file_layout.addWidget(self.splitter_file)

        self.file_widget.setLayout(self.file_layout)
        self.splitter_main.addWidget(self.file_widget)

        self.splitter_main.setStretchFactor(1, 2)

    def connect_ssh(self):
        host = self.host_input.text().strip()
        port = int(self.port_input.text().strip()) if self.port_input.text().strip() else 22
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not host or not username:
            QMessageBox.warning(self, "提示", "请填写主机地址和用户名")
            return

        self.terminal_output.clear()
        self.terminal_output.append_output(f"连接主机...\n")
        self.terminal_output.append_output(f"正在连接 {username}@{host}:{port}...\n")

        self.ssh_worker = SshWorker()
        self.ssh_worker.set_params(host, port, username, password)
        self.ssh_worker.connected.connect(self.on_ssh_connected)
        self.ssh_worker.disconnected.connect(self.on_ssh_disconnected)
        self.ssh_worker.error.connect(self.on_ssh_error)
        self.ssh_worker.output.connect(self.on_ssh_output)
        self.ssh_worker.start()

        self.connect_btn.setEnabled(False)

    def on_ssh_connected(self, client):
        self.terminal_output.append_output("连接主机成功\n\n")

        self.ssh_client = client
        self.sftp = client.open_sftp()
        
        # 使用 exec_command 获取准确的家目录
        try:
            stdin, stdout, stderr = client.exec_command('echo $HOME')
            home = stdout.read().strip().decode('utf-8', errors='replace')
            if home and home.startswith('/'):
                self.home_path = home
            else:
                self.home_path = '/home/' + self.username_input.text().strip()
        except Exception:
            self.home_path = '/home/' + self.username_input.text().strip()
        
        self.sftp_manager = SftpManager(self.sftp, client)
        self.sftp_manager.file_list_updated.connect(self.update_file_table)
        self.sftp_manager.current_path_changed.connect(self.update_path_label)
        self.sftp_manager.error_occurred.connect(self.show_sftp_error)

        # 进入家目录
        self.sftp_manager.list_directory(self.home_path)
        self.init_directory_tree()

        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.terminal_output.set_connected(True)

    def init_directory_tree(self):
        self.directory_tree.clear()
        root_item = QTreeWidgetItem(self.directory_tree)
        root_item.setText(0, "/")
        root_item.setData(0, Qt.UserRole, "/")
        root_item.setExpanded(True)
        self._add_tree_child(root_item, "/")

    def _add_tree_child(self, parent_item, parent_path):
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(
                f'ls -1 "{parent_path}" 2>/dev/null'
            )
            output = stdout.read().decode('utf-8', errors='replace')
            names = [line.strip() for line in output.splitlines() if line.strip()]
            for name in names:
                name = OCTAL_ESCAPE_PATTERN.sub(_decode_octal_escape, name)
                if name in ('.', '..'):
                    continue
                fpath = (parent_path.rstrip('/') + '/' + name).replace('\\', '/')
                try:
                    stdin2, stdout2, stderr2 = self.ssh_client.exec_command(
                        f'test -d "{fpath}" && echo "dir" || echo "file"'
                    )
                    ftype = stdout2.read().decode('utf-8', errors='replace').strip()
                    if ftype == 'dir':
                        child_item = QTreeWidgetItem(parent_item)
                        child_item.setText(0, name)
                        child_item.setData(0, Qt.UserRole, fpath)
                        child_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                except Exception:
                    pass
        except Exception:
            pass

    def on_tree_click(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path:
            if item.childCount() == 0:
                self._add_tree_child(item, path)
            self.sftp_manager.change_directory(path)

    def on_ssh_disconnected(self):
        self.terminal_output.append_output("\n连接已断开\n")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.terminal_output.set_connected(False)
        self.sftp_manager = None
        self.file_table.setRowCount(0)
        self.directory_tree.clear()
        self.path_label.setText("/")

    def on_ssh_error(self, error):
        self.terminal_output.append_output(f"错误: {error}\n")
        self.connect_btn.setEnabled(True)

    def on_ssh_output(self, output):
        self.terminal_output.append_output(output)

    def disconnect_ssh(self):
        if self.ssh_worker:
            self.ssh_worker.stop()
            self.ssh_worker.wait()
        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass

    def send_command(self, command):
        if self.ssh_worker:
            if command:
                self.ssh_worker.execute_command(command)
            else:
                self.ssh_worker.send_enter()

    def go_up_directory(self):
        if self.sftp_manager:
            self.sftp_manager.go_up()

    def update_file_table(self, files):
        self.file_table.setRowCount(0)
        for i, file_info in enumerate(files):
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)

            name_item = QTableWidgetItem(file_info.name)
            name_item.setData(Qt.UserRole, file_info)
            if file_info.is_directory:
                name_item.setForeground(QColor("#3498db"))

            size_item = QTableWidgetItem(file_info.size_str)
            type_item = QTableWidgetItem(file_info.type_str)
            time_item = QTableWidgetItem(file_info.modify_time)
            perm_item = QTableWidgetItem(file_info.permissions)

            self.file_table.setItem(row, 0, name_item)
            self.file_table.setItem(row, 1, size_item)
            self.file_table.setItem(row, 2, type_item)
            self.file_table.setItem(row, 3, time_item)
            self.file_table.setItem(row, 4, perm_item)

    def update_path_label(self, path):
        self.path_label.setText(path)

    def on_file_double_clicked(self, index):
        row = index.row()
        name_item = self.file_table.item(row, 0)
        if name_item:
            file_info = name_item.data(Qt.UserRole)
            if file_info and file_info.is_directory:
                self.sftp_manager.change_directory(file_info.path)
                self.update_tree_selection(file_info.path)

    def update_tree_selection(self, path):
        items = self.directory_tree.findItems(path, Qt.MatchRecursive, column=0)
        if items:
            self.directory_tree.setCurrentItem(items[0])
            items[0].setExpanded(True)

    def show_file_context_menu(self, pos):
        index = self.file_table.indexAt(pos)
        if not index.isValid():
            menu = QMenu(self)
            menu.addAction("新建文件夹", self.create_new_folder)
            menu.addAction("刷新", self.refresh_file_list)
            menu.exec(self.file_table.mapToGlobal(pos))
            return

        row = index.row()
        name_item = self.file_table.item(row, 0)
        if not name_item:
            return

        file_info = name_item.data(Qt.UserRole)
        if not file_info:
            return

        menu = QMenu(self)
        menu.addAction("打开", lambda: self.open_file(file_info))
        menu.addAction("下载", lambda: self.download_single(file_info))
        menu.addAction("重命名", lambda: self.rename_file(file_info))
        menu.addAction("删除", lambda: self.delete_single(file_info))
        menu.addSeparator()
        menu.addAction("复制路径", lambda: self.copy_path(file_info))
        menu.exec(self.file_table.mapToGlobal(pos))

    def open_file(self, file_info):
        if file_info.is_directory:
            self.sftp_manager.change_directory(file_info.path)
        else:
            QMessageBox.information(self, "提示", f"无法直接打开远程文件: {file_info.name}\n请先下载到本地。")

    def download_single(self, file_info):
        if not file_info.is_file:
            QMessageBox.warning(self, "提示", "只能下载文件")
            return

        local_path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", file_info.name
        )
        if local_path:
            self.start_download(file_info.path, local_path)

    def download_files(self):
        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要下载的文件")
            return

        local_dir = QFileDialog.getExistingDirectory(
            self, "选择保存目录"
        )
        if not local_dir:
            return

        for row in selected_rows:
            name_item = self.file_table.item(row, 0)
            if name_item:
                file_info = name_item.data(Qt.UserRole)
                if file_info and file_info.is_file:
                    local_path = os.path.join(local_dir, file_info.name)
                    self.start_download(file_info.path, local_path)

    def start_download(self, remote_path, local_path):
        if self.transfer_thread and self.transfer_thread.isRunning():
            QMessageBox.warning(self, "提示", "正在传输中，请等待完成")
            return

        file_info = self.sftp_manager.get_file_stat(remote_path)
        if not file_info:
            return

        self.transfer_thread = TransferThread(
            self.sftp_manager, 'download', remote_path, local_path
        )

        self.progress_dialog = QProgressDialog(
            f"正在下载: {file_info.name}", "取消", 0, file_info.size, self
        )
        self.progress_dialog.setWindowTitle("下载进度")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        self.transfer_thread.progress.connect(self.update_progress)
        self.transfer_thread.completed.connect(lambda s, e: self.on_transfer_completed(s, e, "下载"))
        self.transfer_thread.start()

        self.progress_dialog.canceled.connect(self.transfer_thread.abort)

    def upload_files(self):
        if not self.sftp_manager:
            QMessageBox.warning(self, "提示", "请先连接SSH")
            return

        local_files, _ = QFileDialog.getOpenFileNames(
            self, "选择要上传的文件"
        )
        if not local_files:
            return

        current_path = self.sftp_manager.get_current_path()
        for local_path in local_files:
            file_name = os.path.basename(local_path)
            remote_path = (current_path.rstrip('/') + '/' + file_name).replace('\\', '/')
            self.start_upload(local_path, remote_path)

    def handle_drop_files(self, file_paths):
        if not self.sftp_manager:
            QMessageBox.warning(self, "提示", "请先连接SSH")
            return

        current_path = self.sftp_manager.get_current_path()
        for local_path in file_paths:
            file_name = os.path.basename(local_path)
            remote_path = (current_path.rstrip('/') + '/' + file_name).replace('\\', '/')
            self.start_upload(local_path, remote_path)

    def start_upload(self, local_path, remote_path):
        if self.transfer_thread and self.transfer_thread.isRunning():
            QMessageBox.warning(self, "提示", "正在传输中，请等待完成")
            return

        file_size = os.path.getsize(local_path)
        file_name = os.path.basename(local_path)

        self.transfer_thread = TransferThread(
            self.sftp_manager, 'upload', local_path, remote_path
        )

        self.progress_dialog = QProgressDialog(
            f"正在上传: {file_name}", "取消", 0, file_size, self
        )
        self.progress_dialog.setWindowTitle("上传进度")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        self.transfer_thread.progress.connect(self.update_progress)
        self.transfer_thread.completed.connect(lambda s, e: self.on_transfer_completed(s, e, "上传"))
        self.transfer_thread.start()

        self.progress_dialog.canceled.connect(self.transfer_thread.abort)

    def update_progress(self, transferred, total):
        if self.progress_dialog:
            self.progress_dialog.setValue(transferred)

    def on_transfer_completed(self, success, error, operation):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "完成", f"{operation}成功")
            self.refresh_file_list()
        else:
            QMessageBox.warning(self, "失败", f"{operation}失败: {error}")

    def create_new_folder(self):
        if not self.sftp_manager:
            QMessageBox.warning(self, "提示", "请先连接SSH")
            return

        name, ok = QInputDialog.getText(self, "新建文件夹", "请输入文件夹名称:")
        if ok and name.strip():
            self.sftp_manager.create_directory(name.strip())

    def rename_file(self, file_info):
        if not self.sftp_manager:
            QMessageBox.warning(self, "提示", "请先连接SSH")
            return

        new_name, ok = QInputDialog.getText(
            self, "重命名", "请输入新名称:", text=file_info.name
        )
        if ok and new_name.strip() and new_name != file_info.name:
            self.sftp_manager.rename_file(file_info.path, new_name.strip())

    def delete_single(self, file_info):
        if not self.sftp_manager:
            QMessageBox.warning(self, "提示", "请先连接SSH")
            return

        result = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {'文件夹' if file_info.is_directory else '文件'} '{file_info.name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if result == QMessageBox.Yes:
            self.sftp_manager.delete_file(file_info.path)

    def delete_selected(self):
        if not self.sftp_manager:
            QMessageBox.warning(self, "提示", "请先连接SSH")
            return

        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的文件")
            return

        files_to_delete = []
        for row in selected_rows:
            name_item = self.file_table.item(row, 0)
            if name_item:
                file_info = name_item.data(Qt.UserRole)
                if file_info:
                    files_to_delete.append(file_info)

        if not files_to_delete:
            return

        result = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(files_to_delete)} 个 {'文件和文件夹' if any(f.is_directory for f in files_to_delete) else '文件'} 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if result == QMessageBox.Yes:
            for file_info in files_to_delete:
                self.sftp_manager.delete_file(file_info.path)

    def refresh_file_list(self):
        if self.sftp_manager:
            self.sftp_manager.list_directory()

    def copy_path(self, file_info):
        from PySide6.QtGui import QClipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(file_info.path)

    def show_sftp_error(self, error):
        QMessageBox.warning(self, "SFTP错误", error)

    def closeEvent(self, event):
        if self.ssh_worker and self.ssh_worker.isRunning():
            self.ssh_worker.stop()
            self.ssh_worker.wait()
        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
        if self.transfer_thread and self.transfer_thread.isRunning():
            self.transfer_thread.abort()
            self.transfer_thread.wait()
        super().closeEvent(event)


from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RemoteTerminalPage()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())
