"""网络服务页面 - 包含FTP客户端/FTP服务/HTTP服务/TFTP服务功能

本页面提供多种网络服务的配置和管理功能，所有服务均通过后台线程启动，
避免阻塞UI主线程。页面切换时会调用cleanup()终止所有服务。
"""
import socket
import os
import io
import ftplib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTabWidget, QComboBox,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QProgressBar, QHeaderView, QCheckBox, QSplitter
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QTextCursor, QIcon

from app.core.logger import Logger

logger = Logger("NetworkService")


class FTPThread(QThread):
    """FTP操作线程 - 支持上传/下载/文件列表操作"""
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str)
    history_signal = Signal(str, str, str, str, str)

    def __init__(self, operation, host, port, username, password, ssl, passive,
                 local_path=None, remote_path=None, file_list=None):
        super().__init__()
        self.operation = operation
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.ssl = ssl
        self.passive = passive
        self.local_path = local_path
        self.remote_path = remote_path
        self.file_list = file_list or []
        self._stop_flag = False

    def _ftp_path(self, *parts):
        """构建FTP路径（使用正斜杠 /）"""
        return '/'.join(parts).replace('\\', '/')

    def _connect_ftp(self):
        """建立FTP连接并返回ftp对象"""
        if self.ssl:
            ftp = ftplib.FTP_TLS()
        else:
            ftp = ftplib.FTP()

        ftp.connect(self.host, self.port)
        ftp.login(self.username, self.password)

        if self.passive:
            ftp.set_pasv(True)
        else:
            ftp.set_pasv(False)

        try:
            ftp.encoding = 'utf-8'
        except Exception:
            pass

        return ftp

    def run(self):
        try:
            if self.operation == 'download':
                self._download()
            elif self.operation == 'upload':
                self._upload()
        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def _download(self):
        try:
            ftp = self._connect_ftp()
            target_files = self.file_list if self.file_list else []

            if not target_files:
                try:
                    target_files = ftp.nlst(self.remote_path or '.')
                except Exception:
                    target_files = []

            if not target_files:
                ftp.quit()
                self.finished_signal.emit(True, "没有可下载的文件")
                return

            total = len(target_files)
            success_count = 0
            skip_count = 0

            for i, filename in enumerate(target_files):
                if self._stop_flag:
                    break

                try:
                    remote_file = self._ftp_path(self.remote_path or '.', filename)
                    local_file = os.path.join(self.local_path, filename)

                    with open(local_file, 'wb') as f:
                        ftp.retrbinary(f'RETR {remote_file}', f.write)

                    file_size = str(os.path.getsize(local_file)) if os.path.exists(local_file) else ''
                    success_count += 1
                    progress = int((i + 1) / total * 100)
                    self.progress_signal.emit(progress, filename)
                    self.history_signal.emit('下载', filename, remote_file, file_size, '成功')
                except Exception as e:
                    skip_count += 1
                    error_msg = str(e)
                    if '550' in error_msg:
                        self.progress_signal.emit(-1, f"跳过 {filename}: 权限不足(550)")
                        self.history_signal.emit('下载', filename, remote_file, '', '失败(权限不足)')
                    else:
                        self.progress_signal.emit(-1, f"跳过 {filename}: {error_msg}")
                        self.history_signal.emit('下载', filename, remote_file, '', f'失败({error_msg})')
                    continue

            ftp.quit()

            if success_count == total:
                self.finished_signal.emit(True, f"下载完成: {success_count} 个文件")
            elif success_count > 0:
                self.finished_signal.emit(True, f"部分完成: {success_count} 成功, {skip_count} 跳过")
            else:
                self.finished_signal.emit(False, f"下载失败: 所有文件都失败")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def _upload(self):
        try:
            ftp = self._connect_ftp()

            if os.path.isdir(self.local_path):
                files = [f for f in os.listdir(self.local_path)
                         if os.path.isfile(os.path.join(self.local_path, f))]
            else:
                files = [os.path.basename(self.local_path)]

            total = len(files)
            success_count = 0
            skip_count = 0

            for i, filename in enumerate(files):
                if self._stop_flag:
                    break

                try:
                    if os.path.isdir(self.local_path):
                        local_file = os.path.join(self.local_path, filename)
                    else:
                        local_file = self.local_path

                    remote_file = self._ftp_path(self.remote_path or '.', filename)
                    file_size = str(os.path.getsize(local_file)) if os.path.exists(local_file) else ''

                    with open(local_file, 'rb') as f:
                        ftp.storbinary(f'STOR {remote_file}', f)

                    success_count += 1
                    progress = int((i + 1) / total * 100)
                    self.progress_signal.emit(progress, filename)
                    self.history_signal.emit('上传', filename, remote_file, file_size, '成功')
                except Exception as e:
                    skip_count += 1
                    error_msg = str(e)
                    if '550' in error_msg:
                        self.progress_signal.emit(-1, f"跳过 {filename}: 权限不足(550)，请联系管理员开启写入权限")
                        self.history_signal.emit('上传', filename, remote_file, file_size, '失败(权限不足)')
                    else:
                        self.progress_signal.emit(-1, f"跳过 {filename}: {error_msg}")
                        self.history_signal.emit('上传', filename, remote_file, file_size, f'失败({error_msg})')
                    continue

            ftp.quit()

            if success_count == total:
                self.finished_signal.emit(True, f"上传完成: {success_count} 个文件")
            elif success_count > 0:
                self.finished_signal.emit(True, f"部分完成: {success_count} 成功, {skip_count} 跳过")
            else:
                self.finished_signal.emit(False, f"上传失败: 所有文件都失败(550权限不足)")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def stop(self):
        self._stop_flag = True


class FTPHandler:
    """FTP服务器处理器"""
    def __init__(self):
        self.server = None
        self.is_running = False
        self.thread = None
        self.log_callback = None
        self.session_callback = None

    def start(self, port, username, password, root_dir):
        try:
            from pyftpdlib.authorizers import DummyAuthorizer
            from pyftpdlib.handlers import FTPHandler
            from pyftpdlib.servers import FTPServer

            authorizer = DummyAuthorizer()
            if password:
                authorizer.add_user(username, password, root_dir, perm='elradfmw')
            else:
                authorizer.add_anonymous(root_dir, perm='elradfmw')

            class CustomFTPHandler(FTPHandler):
                def log(self, msg):
                    if self.log_callback:
                        self.log_callback(msg)

            handler = CustomFTPHandler
            handler.authorizer = authorizer
            handler.banner = "网络工具箱 FTP Server"

            self.server = FTPServer(('0.0.0.0', port), handler)
            self.server.max_cons = 256
            self.server.max_cons_per_ip = 5

            handler.log_callback = self.log_callback

            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()
            self.is_running = True
            return True, f"FTP服务器已启动在 0.0.0.0:{port}"
        except ImportError:
            return False, "未安装pyftpdlib库，请运行: pip install pyftpdlib"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def _run(self):
        try:
            self.server.serve_forever()
        except Exception:
            pass

    def stop(self):
        if self.server:
            self.server.close_all()
            self.server = None
        self.is_running = False
        return "FTP服务器已停止"


class HTTPFileServer:
    """HTTP文件分发服务器"""
    def __init__(self):
        self.server = None
        self.is_running = False
        self.thread = None
        self.log_callback = None

    def start(self, port, root_dir):
        try:
            class CustomHandler(SimpleHTTPRequestHandler):
                def log_message(self, format, *args):
                    msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {format % args}"
                    if hasattr(self.server, 'log_callback') and self.server.log_callback:
                        self.server.log_callback(msg)

            os.chdir(root_dir)
            self.server = HTTPServer(('0.0.0.0', port), CustomHandler)
            self.server.log_callback = self.log_callback
            self.thread = Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.is_running = True
            return True, f"HTTP文件服务器已启动在 http://localhost:{port}"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def stop(self):
        if self.server:
            self.server.shutdown()
        self.is_running = False
        return "HTTP文件服务器已停止"


class TFTPHandler:
    """TFTP服务器处理器"""
    def __init__(self):
        self.server = None
        self.is_running = False
        self.thread = None
        self.log_callback = None

    def start(self, port, root_dir):
        try:
            import tftpy
            self.server = tftpy.TftpServer(root_dir)
            self.thread = Thread(target=self._run, args=(port,), daemon=True)
            self.thread.start()
            self.is_running = True
            return True, f"TFTP服务器已启动在 0.0.0.0:{port}"
        except ImportError:
            return False, "未安装tftpy库，请运行: pip install tftpy"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def _run(self, port):
        try:
            self.server.listen('0.0.0.0', port)
        except Exception:
            pass

    def stop(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        self.is_running = False
        return "TFTP服务器已停止"


class NetworkServicePage(QWidget):
    """网络服务主页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.ftp_server_handler = FTPHandler()
        self.http_handler = HTTPFileServer()
        self.tftp_handler = TFTPHandler()
        self.ftp_client = None
        self.ftp_thread = None
        self.current_ftp_path = '.'
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::tab-bar { alignment: center; }
            QTabBar::tab {
                background-color: #5a6268;
                color: white;
                padding: 10px 25px;
                font-size: 13px;
                font-weight: bold;
                border: none;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #495057;
            }
            QTabBar::tab:hover {
                background-color: #6c757d;
            }
        """)

        self.ftp_client_page = self._build_ftp_client_page()
        self.tab_widget.addTab(self.ftp_client_page, "FTP客户端")

        self.ftp_server_page = self._build_ftp_server_page()
        self.tab_widget.addTab(self.ftp_server_page, "FTP服务")

        self.http_page = self._build_http_page()
        self.tab_widget.addTab(self.http_page, "HTTP服务")

        self.tftp_page = self._build_tftp_page()
        self.tab_widget.addTab(self.tftp_page, "TFTP服务")

        layout.addWidget(self.tab_widget)

    def _build_ftp_client_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(15, 12, 15, 12)
        config_layout.setSpacing(10)

        title_layout = QHBoxLayout()
        icon_label = QLabel("📁")
        icon_label.setStyleSheet("font-size: 20px;")
        title_label = QLabel("FTP客户端")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2d3436;")
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.ftp_client_status = QLabel("未连接")
        self.ftp_client_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        title_layout.addWidget(self.ftp_client_status)
        config_layout.addLayout(title_layout)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(15)

        host_layout = QVBoxLayout()
        host_layout.addWidget(QLabel("主机"))
        self.ftp_client_host = QLineEdit()
        self.ftp_client_host.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        host_layout.addWidget(self.ftp_client_host)
        form_layout.addLayout(host_layout)

        port_layout = QVBoxLayout()
        port_layout.addWidget(QLabel("端口"))
        self.ftp_client_port = QLineEdit("21")
        self.ftp_client_port.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        port_layout.addWidget(self.ftp_client_port)
        form_layout.addLayout(port_layout)

        user_layout = QVBoxLayout()
        user_layout.addWidget(QLabel("用户名"))
        self.ftp_client_user = QLineEdit("anonymous")
        self.ftp_client_user.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        user_layout.addWidget(self.ftp_client_user)
        form_layout.addLayout(user_layout)

        pass_layout = QVBoxLayout()
        pass_layout.addWidget(QLabel("密码"))
        self.ftp_client_pass = QLineEdit()
        self.ftp_client_pass.setEchoMode(QLineEdit.Password)
        self.ftp_client_pass.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        pass_layout.addWidget(self.ftp_client_pass)
        form_layout.addLayout(pass_layout)

        ssl_layout = QVBoxLayout()
        ssl_label = QLabel("SSL")
        ssl_label.setToolTip("FTPS: 使用TLS/SSL加密传输，保护密码和文件内容不被窃听")
        ssl_layout.addWidget(ssl_label)
        self.ftp_client_ssl = QCheckBox()
        self.ftp_client_ssl.setToolTip("勾选后使用加密连接(FTPS)，更安全但部分服务器不支持")
        ssl_layout.addWidget(self.ftp_client_ssl, alignment=Qt.AlignLeft)
        form_layout.addLayout(ssl_layout)

        passive_layout = QVBoxLayout()
        passive_layout.addWidget(QLabel("被动"))
        self.ftp_client_passive = QCheckBox()
        self.ftp_client_passive.setChecked(True)
        passive_layout.addWidget(self.ftp_client_passive, alignment=Qt.AlignLeft)
        form_layout.addLayout(passive_layout)

        form_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        connect_btn = QPushButton("连接")
        connect_btn.setStyleSheet("""
            QPushButton { background-color: #667eea; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6fd6; }
        """)
        connect_btn.clicked.connect(self.connect_ftp)
        btn_layout.addWidget(connect_btn)

        disconnect_btn = QPushButton("断开")
        disconnect_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #d63031; }
        """)
        disconnect_btn.clicked.connect(self.disconnect_ftp)
        disconnect_btn.setEnabled(False)
        self.ftp_disconnect_btn = disconnect_btn
        btn_layout.addWidget(disconnect_btn)

        btn_layout.addStretch()
        form_layout.addLayout(btn_layout)

        config_layout.addLayout(form_layout)

        path_layout = QHBoxLayout()
        self.ftp_client_path = QComboBox()
        self.ftp_client_path.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px; min-width: 200px;")
        self.ftp_client_path.currentTextChanged.connect(self.on_path_changed)
        path_layout.addWidget(self.ftp_client_path)

        back_btn = QPushButton("返回")
        back_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px;")
        back_btn.clicked.connect(self.go_back)
        path_layout.addWidget(back_btn)

        refresh_btn = QPushButton("加载")
        refresh_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px;")
        refresh_btn.clicked.connect(self.refresh_ftp_files)
        path_layout.addWidget(refresh_btn)

        save_btn = QPushButton("保存")
        save_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px;")
        path_layout.addWidget(save_btn)

        delete_btn = QPushButton("删除")
        delete_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px; color: #dc3545;")
        path_layout.addWidget(delete_btn)

        config_layout.addLayout(path_layout)
        layout.addWidget(config_frame)

        splitter = QSplitter(Qt.Horizontal)

        left_frame = QFrame()
        left_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(10, 10, 10, 10)

        left_title_layout = QHBoxLayout()
        left_title = QLabel("远程文件")
        left_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        left_title_layout.addWidget(left_title)
        left_title_layout.addStretch()

        refresh_btn2 = QPushButton("刷新")
        refresh_btn2.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        refresh_btn2.clicked.connect(self.refresh_ftp_files)
        left_title_layout.addWidget(refresh_btn2)

        new_btn = QPushButton("+新建")
        new_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        left_title_layout.addWidget(new_btn)

        rename_btn = QPushButton("重命名")
        rename_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        left_title_layout.addWidget(rename_btn)

        delete_btn2 = QPushButton("删除")
        delete_btn2.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px; color: #dc3545;")
        left_title_layout.addWidget(delete_btn2)

        left_layout.addLayout(left_title_layout)

        self.ftp_file_table = QTableWidget()
        self.ftp_file_table.setColumnCount(3)
        self.ftp_file_table.setHorizontalHeaderLabels(["名称", "大小", "修改时间"])
        self.ftp_file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ftp_file_table.setStyleSheet("""
            QTableWidget { border: none; }
            QHeaderView::section { background-color: #f8f9fa; padding: 8px; font-size: 12px; font-weight: bold; }
            QTableWidget::item { padding: 6px; }
        """)
        self.ftp_file_table.doubleClicked.connect(self.on_ftp_file_double_clicked)
        left_layout.addWidget(self.ftp_file_table)
        splitter.addWidget(left_frame)

        right_frame = QFrame()
        right_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(10, 10, 10, 10)

        right_title = QLabel("文件传输")
        right_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        right_layout.addWidget(right_title)

        upload_group = QFrame()
        upload_group.setStyleSheet("""
            QFrame { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; }
        """)
        upload_layout = QVBoxLayout(upload_group)
        upload_layout.setContentsMargins(10, 10, 10, 10)
        upload_layout.setSpacing(8)

        upload_label = QLabel("上传文件（支持多选/拖放）")
        upload_label.setStyleSheet("font-size: 12px; color: #495057;")
        upload_layout.addWidget(upload_label)

        upload_path_layout = QHBoxLayout()
        self.upload_path_input = QLineEdit()
        self.upload_path_input.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 4px; font-size: 12px;")
        upload_path_layout.addWidget(self.upload_path_input)
        upload_select_btn = QPushButton("选择")
        upload_select_btn.setStyleSheet("background-color: white; border: 1px solid #ced4da; padding: 3px 10px; border-radius: 4px; font-size: 12px;")
        upload_select_btn.clicked.connect(self.select_upload_files)
        upload_path_layout.addWidget(upload_select_btn)
        upload_layout.addLayout(upload_path_layout)

        upload_label2 = QLabel("上传到当前远程目录")
        upload_label2.setStyleSheet("font-size: 12px; color: #495057;")
        upload_layout.addWidget(upload_label2)

        upload_btn_layout = QHBoxLayout()
        upload_btn = QPushButton("上传")
        upload_btn.setStyleSheet("""
            QPushButton { background-color: #667eea; color: white; border: none; padding: 6px 20px; border-radius: 4px; font-weight: bold; font-size: 12px; }
            QPushButton:hover { background-color: #5a6fd6; }
        """)
        upload_btn.clicked.connect(self.upload_files)
        upload_btn_layout.addWidget(upload_btn)

        upload_folder_btn = QPushButton("上传目录")
        upload_folder_btn.setStyleSheet("background-color: white; border: 1px solid #ced4da; padding: 4px 10px; border-radius: 4px; font-size: 12px;")
        upload_folder_btn.clicked.connect(self.select_upload_folder)
        upload_btn_layout.addWidget(upload_folder_btn)
        upload_layout.addLayout(upload_btn_layout)
        right_layout.addWidget(upload_group)

        download_group = QFrame()
        download_group.setStyleSheet("""
            QFrame { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; }
        """)
        download_layout = QVBoxLayout(download_group)
        download_layout.setContentsMargins(10, 10, 10, 10)
        download_layout.setSpacing(8)

        download_label = QLabel("下载（左侧可多选）")
        download_label.setStyleSheet("font-size: 12px; color: #495057;")
        download_layout.addWidget(download_label)

        download_label2 = QLabel("（请在左侧选择文件）")
        download_label2.setStyleSheet("font-size: 12px; color: #495057;")
        download_layout.addWidget(download_label2)

        download_btn_layout = QHBoxLayout()
        download_btn = QPushButton("下载")
        download_btn.setStyleSheet("""
            QPushButton { background-color: #00b894; color: white; border: none; padding: 6px 20px; border-radius: 4px; font-weight: bold; font-size: 12px; }
            QPushButton:hover { background-color: #00a885; }
        """)
        download_btn.clicked.connect(self.download_files)
        download_btn_layout.addWidget(download_btn)

        download_folder_btn = QPushButton("下载目录")
        download_folder_btn.setStyleSheet("background-color: white; border: 1px solid #ced4da; padding: 4px 10px; border-radius: 4px; font-size: 12px;")
        download_folder_btn.clicked.connect(self.select_download_folder)
        download_btn_layout.addWidget(download_folder_btn)
        download_layout.addLayout(download_btn_layout)
        right_layout.addWidget(download_group)

        progress_group = QFrame()
        progress_group.setStyleSheet("""
            QFrame { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; }
        """)
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(10, 10, 10, 10)

        progress_label = QLabel("传输进度")
        progress_label.setStyleSheet("font-size: 12px; color: #495057;")
        progress_layout.addWidget(progress_label)

        self.transfer_progress = QProgressBar()
        self.transfer_progress.setStyleSheet("""
            QProgressBar { border: 1px solid #ced4da; border-radius: 4px; height: 20px; }
            QProgressBar::chunk { background-color: #667eea; }
        """)
        progress_layout.addWidget(self.transfer_progress)
        right_layout.addWidget(progress_group)

        right_layout.addStretch()
        splitter.addWidget(right_frame)

        splitter.setSizes([600, 300])
        layout.addWidget(splitter)

        history_frame = QFrame()
        history_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        history_layout = QVBoxLayout(history_frame)
        history_layout.setContentsMargins(10, 10, 10, 10)

        history_title_layout = QHBoxLayout()
        history_title = QLabel("传输历史")
        history_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        history_title_layout.addWidget(history_title)
        history_title_layout.addStretch()
        clear_btn = QPushButton("清空")
        clear_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        clear_btn.clicked.connect(self.clear_transfer_history)
        history_title_layout.addWidget(clear_btn)
        history_layout.addLayout(history_title_layout)

        self.transfer_history_table = QTableWidget()
        self.transfer_history_table.setColumnCount(6)
        self.transfer_history_table.setHorizontalHeaderLabels(["方向", "文件名", "远程路径", "大小", "状态", "时间"])
        self.transfer_history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.transfer_history_table.setStyleSheet("""
            QTableWidget { border: none; }
            QHeaderView::section { background-color: #f8f9fa; padding: 8px; font-size: 12px; font-weight: bold; }
            QTableWidget::item { padding: 6px; }
        """)
        history_layout.addWidget(self.transfer_history_table)
        layout.addWidget(history_frame)

        return page

    def _build_ftp_server_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(15, 12, 15, 12)
        config_layout.setSpacing(10)

        title_layout = QHBoxLayout()
        icon_label = QLabel("⬆️")
        icon_label.setStyleSheet("font-size: 20px;")
        title_label = QLabel("FTP服务配置")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2d3436;")
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.ftp_server_status = QLabel("Stopped")
        self.ftp_server_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        title_layout.addWidget(self.ftp_server_status)
        config_layout.addLayout(title_layout)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(15)

        port_layout = QVBoxLayout()
        port_layout.addWidget(QLabel("端口"))
        self.ftp_server_port = QLineEdit("21")
        self.ftp_server_port.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        port_layout.addWidget(self.ftp_server_port)
        form_layout.addLayout(port_layout)

        user_layout = QVBoxLayout()
        user_layout.addWidget(QLabel("用户名"))
        self.ftp_server_user = QLineEdit("anonymous")
        self.ftp_server_user.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        user_layout.addWidget(self.ftp_server_user)
        form_layout.addLayout(user_layout)

        pass_layout = QVBoxLayout()
        pass_layout.addWidget(QLabel("密码"))
        self.ftp_server_pass = QLineEdit()
        self.ftp_server_pass.setEchoMode(QLineEdit.Password)
        self.ftp_server_pass.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        pass_layout.addWidget(self.ftp_server_pass)
        form_layout.addLayout(pass_layout)

        form_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        start_btn = QPushButton("启动")
        start_btn.setStyleSheet("""
            QPushButton { background-color: #667eea; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6fd6; }
        """)
        start_btn.clicked.connect(self.start_ftp_server)
        btn_layout.addWidget(start_btn)

        stop_btn = QPushButton("停止")
        stop_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #d63031; }
        """)
        stop_btn.clicked.connect(self.stop_ftp_server)
        stop_btn.setEnabled(False)
        self.ftp_server_stop_btn = stop_btn
        btn_layout.addWidget(stop_btn)

        form_layout.addLayout(btn_layout)

        config_layout.addLayout(form_layout)

        root_layout = QHBoxLayout()
        root_layout.addWidget(QLabel("根目录"))
        self.ftp_server_root = QLineEdit()
        self.ftp_server_root.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px; flex: 1;")
        root_layout.addWidget(self.ftp_server_root)
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px;")
        browse_btn.clicked.connect(self.browse_ftp_server_root)
        root_layout.addWidget(browse_btn)
        config_layout.addLayout(root_layout)

        layout.addWidget(config_frame)

        sessions_frame = QFrame()
        sessions_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        sessions_layout = QVBoxLayout(sessions_frame)
        sessions_layout.setContentsMargins(10, 10, 10, 10)

        sessions_title_layout = QHBoxLayout()
        sessions_title = QLabel("👥 活动会话")
        sessions_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        sessions_title_layout.addWidget(sessions_title)
        sessions_title_layout.addStretch()
        sessions_layout.addLayout(sessions_title_layout)

        self.ftp_sessions_table = QTableWidget()
        self.ftp_sessions_table.setColumnCount(4)
        self.ftp_sessions_table.setHorizontalHeaderLabels(["文件名", "远程地址", "类型", "进度"])
        self.ftp_sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ftp_sessions_table.setStyleSheet("""
            QTableWidget { border: none; }
            QHeaderView::section { background-color: #f8f9fa; padding: 8px; font-size: 12px; font-weight: bold; }
            QTableWidget::item { padding: 6px; }
        """)
        sessions_layout.addWidget(self.ftp_sessions_table)
        layout.addWidget(sessions_frame)

        logs_frame = QFrame()
        logs_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        logs_layout = QVBoxLayout(logs_frame)
        logs_layout.setContentsMargins(10, 10, 10, 10)

        logs_title_layout = QHBoxLayout()
        logs_title = QLabel("📋 系统日志")
        logs_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        logs_title_layout.addWidget(logs_title)
        logs_title_layout.addStretch()
        clear_logs_btn = QPushButton("清空日志")
        clear_logs_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        clear_logs_btn.clicked.connect(self.clear_ftp_logs)
        logs_title_layout.addWidget(clear_logs_btn)
        logs_layout.addLayout(logs_title_layout)

        self.ftp_server_log = QTextEdit()
        self.ftp_server_log.setReadOnly(True)
        self.ftp_server_log.setStyleSheet("font-size: 12px; color: #495057; border: none;")
        logs_layout.addWidget(self.ftp_server_log)
        layout.addWidget(logs_frame)

        return page

    def _build_http_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(15, 12, 15, 12)
        config_layout.setSpacing(10)

        title_layout = QHBoxLayout()
        icon_label = QLabel("🌐")
        icon_label.setStyleSheet("font-size: 20px;")
        title_label = QLabel("HTTP服务配置")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2d3436;")
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.http_server_status = QLabel("Stopped")
        self.http_server_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        title_layout.addWidget(self.http_server_status)
        config_layout.addLayout(title_layout)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(15)

        port_layout = QVBoxLayout()
        port_layout.addWidget(QLabel("端口"))
        self.http_server_port = QLineEdit("8080")
        self.http_server_port.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        port_layout.addWidget(self.http_server_port)
        form_layout.addLayout(port_layout)

        form_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        start_btn = QPushButton("启动")
        start_btn.setStyleSheet("""
            QPushButton { background-color: #667eea; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6fd6; }
        """)
        start_btn.clicked.connect(self.start_http_server)
        btn_layout.addWidget(start_btn)

        stop_btn = QPushButton("停止")
        stop_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #d63031; }
        """)
        stop_btn.clicked.connect(self.stop_http_server)
        stop_btn.setEnabled(False)
        self.http_server_stop_btn = stop_btn
        btn_layout.addWidget(stop_btn)

        form_layout.addLayout(btn_layout)

        config_layout.addLayout(form_layout)

        root_layout = QHBoxLayout()
        root_layout.addWidget(QLabel("根目录"))
        self.http_server_root = QLineEdit()
        self.http_server_root.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px; flex: 1;")
        root_layout.addWidget(self.http_server_root)
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px;")
        browse_btn.clicked.connect(self.browse_http_server_root)
        root_layout.addWidget(browse_btn)
        config_layout.addLayout(root_layout)

        layout.addWidget(config_frame)

        access_frame = QFrame()
        access_frame.setStyleSheet("""
            QFrame { background-color: #e3f2fd; border: 1px solid #90caf9; border-radius: 8px; }
        """)
        access_layout = QHBoxLayout(access_frame)
        access_layout.setContentsMargins(15, 12, 15, 12)

        access_label = QLabel("🌐 本地访问:")
        access_label.setStyleSheet("font-weight: bold; color: #1565c0;")
        access_layout.addWidget(access_label)

        self.http_access_url = QLabel("http://localhost:8080")
        self.http_access_url.setStyleSheet("color: #1976d2; text-decoration: underline; font-size: 13px;")
        access_layout.addWidget(self.http_access_url)

        access_layout.addStretch()

        access_note = QLabel("支持文件浏览、上传、下载和新建文件夹")
        access_note.setStyleSheet("font-size: 12px; color: #546e7a;")
        access_layout.addWidget(access_note)

        layout.addWidget(access_frame)

        logs_frame = QFrame()
        logs_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        logs_layout = QVBoxLayout(logs_frame)
        logs_layout.setContentsMargins(10, 10, 10, 10)

        logs_title_layout = QHBoxLayout()
        logs_title = QLabel("📋 访问日志")
        logs_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        logs_title_layout.addWidget(logs_title)
        logs_title_layout.addStretch()
        clear_logs_btn = QPushButton("清空日志")
        clear_logs_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        clear_logs_btn.clicked.connect(self.clear_http_logs)
        logs_title_layout.addWidget(clear_logs_btn)
        logs_layout.addLayout(logs_title_layout)

        self.http_server_log = QTextEdit()
        self.http_server_log.setReadOnly(True)
        self.http_server_log.setStyleSheet("font-size: 12px; color: #495057; border: none;")
        logs_layout.addWidget(self.http_server_log)
        layout.addWidget(logs_frame)

        return page

    def _build_tftp_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(15, 12, 15, 12)
        config_layout.setSpacing(10)

        title_layout = QHBoxLayout()
        icon_label = QLabel("📡")
        icon_label.setStyleSheet("font-size: 20px;")
        title_label = QLabel("TFTP服务配置")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2d3436;")
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.tftp_server_status = QLabel("Stopped")
        self.tftp_server_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        title_layout.addWidget(self.tftp_server_status)
        config_layout.addLayout(title_layout)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(15)

        port_layout = QVBoxLayout()
        port_layout.addWidget(QLabel("端口"))
        self.tftp_server_port = QLineEdit("69")
        self.tftp_server_port.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        port_layout.addWidget(self.tftp_server_port)
        form_layout.addLayout(port_layout)

        root_layout = QVBoxLayout()
        root_layout.addWidget(QLabel("根目录"))
        self.tftp_server_root = QLineEdit()
        self.tftp_server_root.setStyleSheet("border: 1px solid #ced4da; border-radius: 4px; padding: 5px;")
        root_layout.addWidget(self.tftp_server_root)
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 4px 12px; border-radius: 4px;")
        browse_btn.clicked.connect(self.browse_tftp_server_root)
        root_layout.addWidget(browse_btn)
        form_layout.addLayout(root_layout)

        form_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        start_btn = QPushButton("启动")
        start_btn.setStyleSheet("""
            QPushButton { background-color: #667eea; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6fd6; }
        """)
        start_btn.clicked.connect(self.start_tftp_server)
        btn_layout.addWidget(start_btn)

        stop_btn = QPushButton("停止")
        stop_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #d63031; }
        """)
        stop_btn.clicked.connect(self.stop_tftp_server)
        stop_btn.setEnabled(False)
        self.tftp_server_stop_btn = stop_btn
        btn_layout.addWidget(stop_btn)

        form_layout.addLayout(btn_layout)

        config_layout.addLayout(form_layout)

        layout.addWidget(config_frame)

        transfers_frame = QFrame()
        transfers_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        transfers_layout = QVBoxLayout(transfers_frame)
        transfers_layout.setContentsMargins(10, 10, 10, 10)

        transfers_title_layout = QHBoxLayout()
        transfers_title = QLabel("📥 传输列表")
        transfers_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        transfers_title_layout.addWidget(transfers_title)
        transfers_title_layout.addStretch()
        transfers_layout.addLayout(transfers_title_layout)

        self.tftp_transfers_table = QTableWidget()
        self.tftp_transfers_table.setColumnCount(5)
        self.tftp_transfers_table.setHorizontalHeaderLabels(["文件名", "远程地址", "类型", "进度", "状态"])
        self.tftp_transfers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tftp_transfers_table.setStyleSheet("""
            QTableWidget { border: none; }
            QHeaderView::section { background-color: #f8f9fa; padding: 8px; font-size: 12px; font-weight: bold; }
            QTableWidget::item { padding: 6px; }
        """)
        transfers_layout.addWidget(self.tftp_transfers_table)
        layout.addWidget(transfers_frame)

        logs_frame = QFrame()
        logs_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e9ecef; border-radius: 8px; }
        """)
        logs_layout = QVBoxLayout(logs_frame)
        logs_layout.setContentsMargins(10, 10, 10, 10)

        logs_title_layout = QHBoxLayout()
        logs_title = QLabel("📋 系统日志")
        logs_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436;")
        logs_title_layout.addWidget(logs_title)
        logs_title_layout.addStretch()
        clear_logs_btn = QPushButton("清空日志")
        clear_logs_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 3px 10px; border-radius: 3px; font-size: 12px;")
        clear_logs_btn.clicked.connect(self.clear_tftp_logs)
        logs_title_layout.addWidget(clear_logs_btn)
        logs_layout.addLayout(logs_title_layout)

        self.tftp_server_log = QTextEdit()
        self.tftp_server_log.setReadOnly(True)
        self.tftp_server_log.setStyleSheet("font-size: 12px; color: #495057; border: none;")
        logs_layout.addWidget(self.tftp_server_log)
        layout.addWidget(logs_frame)

        return page

    def connect_ftp(self):
        host = self.ftp_client_host.text().strip()
        port = int(self.ftp_client_port.text().strip())
        user = self.ftp_client_user.text().strip()
        password = self.ftp_client_pass.text().strip()
        ssl = self.ftp_client_ssl.isChecked()
        passive = self.ftp_client_passive.isChecked()

        if not host:
            QMessageBox.warning(self, "提示", "请输入主机地址")
            return

        try:
            if ssl:
                self.ftp_client = ftplib.FTP_TLS()
            else:
                self.ftp_client = ftplib.FTP()

            self.ftp_client.connect(host, port)
            self.ftp_client.login(user, password)

            if passive:
                self.ftp_client.set_pasv(True)
            else:
                self.ftp_client.set_pasv(False)

            try:
                self.ftp_client.encoding = 'utf-8'
            except Exception:
                pass

            try:
                self.current_ftp_path = self.ftp_client.pwd()
            except Exception:
                self.current_ftp_path = '/'

            self.ftp_client_status.setText("已连接")
            self.ftp_client_status.setStyleSheet("color: #27ae60; font-size: 12px;")
            self.ftp_disconnect_btn.setEnabled(True)
            self.ftp_client_path.clear()
            self.ftp_client_path.addItem('/')
            if self.current_ftp_path != '/':
                self.ftp_client_path.addItem(self.current_ftp_path)
            self.ftp_client_path.setCurrentText(self.current_ftp_path)
            self.refresh_ftp_files()
            QMessageBox.information(self, "提示", "连接成功")
        except Exception as e:
            error_str = str(e)
            if error_str.startswith('530'):
                QMessageBox.warning(self, "提示", "连接失败：用户名或密码错误")
            else:
                QMessageBox.warning(self, "提示", f"连接失败: {error_str}")

    def disconnect_ftp(self):
        if self.ftp_client:
            try:
                self.ftp_client.quit()
            except Exception:
                pass
            self.ftp_client = None
        self.ftp_client_status.setText("未连接")
        self.ftp_client_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        self.ftp_disconnect_btn.setEnabled(False)
        self.ftp_file_table.setRowCount(0)
        self.current_ftp_path = '.'
        self.ftp_client_path.clear()
        self.ftp_client_path.addItem('.')

    def on_ftp_file_double_clicked(self, index):
        if not self.ftp_client:
            return

        row = index.row()
        filename_item = self.ftp_file_table.item(row, 0)
        size_item = self.ftp_file_table.item(row, 1)

        if not filename_item:
            return

        filename = filename_item.text()
        size = size_item.text() if size_item else ''

        if size == '4096' or size == '<DIR>':
            if self.current_ftp_path == '/' or self.current_ftp_path == '.':
                new_path = '/' + filename
            else:
                new_path = self.current_ftp_path + '/' + filename
            try:
                self.ftp_client.cwd(new_path)
                self.current_ftp_path = new_path
                self.ftp_client_path.clear()
                self.ftp_client_path.addItem('/')
                self.ftp_client_path.addItem(new_path)
                self.ftp_client_path.setCurrentText(new_path)
                self.refresh_ftp_files()
            except Exception as e:
                QMessageBox.warning(self, "提示", f"无法进入目录: {str(e)}")

    def _ftp_path(self, *parts):
        return '/'.join(parts).replace('\\', '/')

    def on_path_changed(self, path):
        if not self.ftp_client or not path or path == self.current_ftp_path:
            return

        try:
            self.ftp_client.cwd(path)
            self.current_ftp_path = path
            self.refresh_ftp_files()
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法切换到路径: {str(e)}")

    def go_back(self):
        if not self.ftp_client:
            return

        current_path = self.current_ftp_path.rstrip('/')
        if not current_path or current_path == '/':
            QMessageBox.information(self, "提示", "已经是根目录")
            return

        parts = current_path.split('/')
        if len(parts) > 1:
            parent_path = '/'.join(parts[:-1])
            if not parent_path:
                parent_path = '/'
        else:
            parent_path = '/'

        try:
            self.ftp_client.cwd(parent_path)
            self.current_ftp_path = parent_path
            self.ftp_client_path.clear()
            self.ftp_client_path.addItem('/')
            if parent_path != '/':
                self.ftp_client_path.addItem(parent_path)
            self.ftp_client_path.setCurrentText(parent_path)
            self.refresh_ftp_files()
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法返回上级目录: {str(e)}")

    def _decode_line(self, line_bytes):
        """多编码尝试解码FTP LIST数据，优先中文编码"""
        for encoding in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'cp936', 'latin-1']:
            try:
                decoded = line_bytes.decode(encoding)
                if decoded.strip():
                    return decoded
            except Exception:
                continue
        return line_bytes.decode('latin-1', errors='replace')

    def _parse_ftp_list_line(self, line):
        """解析FTP LIST格式行，支持Unix和Windows格式"""
        line = line.strip()
        if not line:
            return None

        try:
            parts = line.split()
            if len(parts) < 6:
                return None

            if line.startswith('d') or line.startswith('-'):
                file_type = 'dir' if line.startswith('d') else 'file'
                size = parts[4]
                date = f"{parts[5]} {parts[6]} {parts[7]}" if len(parts) >= 8 else f"{parts[5]} {parts[6]}"
                filename = ' '.join(parts[8:]) if len(parts) > 8 else parts[-1]
            else:
                file_type = 'dir' if '<DIR>' in parts else 'file'
                size = parts[-2] if parts[-2].isdigit() or parts[-2] == '<DIR>' else ''
                date = ' '.join(parts[:4]) if len(parts) >= 5 else ''
                filename = parts[-1]

            return {'name': filename, 'size': size, 'date': date}
        except Exception:
            return None

    def refresh_ftp_files(self):
        if not self.ftp_client:
            QMessageBox.warning(self, "提示", "请先连接FTP服务器")
            return

        try:
            files = []
            data_buffer = bytearray()

            def collect_data(data):
                data_buffer.extend(data)

            self.ftp_client.retrbinary('LIST', collect_data)

            lines = data_buffer.split(b'\n')
            for line_bytes in lines:
                if not line_bytes.strip():
                    continue

                line = self._decode_line(line_bytes)
                if not line:
                    continue

                if line.startswith('total '):
                    continue

                parsed = self._parse_ftp_list_line(line)
                if parsed:
                    files.append(parsed)

            self.ftp_file_table.setRowCount(0)
            for file_info in files:
                row = self.ftp_file_table.rowCount()
                self.ftp_file_table.insertRow(row)
                self.ftp_file_table.setItem(row, 0, QTableWidgetItem(file_info['name']))
                self.ftp_file_table.setItem(row, 1, QTableWidgetItem(file_info['size']))
                self.ftp_file_table.setItem(row, 2, QTableWidgetItem(file_info['date']))
        except Exception as e:
            error_str = str(e)
            if error_str.startswith('530'):
                QMessageBox.warning(self, "提示", "登录失败：用户名或密码错误")
            else:
                QMessageBox.warning(self, "提示", f"获取文件列表失败: {error_str}")

    def select_upload_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择上传文件")
        if files:
            self.upload_path_input.setText("; ".join(files))

    def select_upload_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择上传目录")
        if folder:
            self.upload_path_input.setText(folder)

    def select_download_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if folder:
            self.download_path = folder

    def upload_files(self):
        if not self.ftp_client:
            QMessageBox.warning(self, "提示", "请先连接FTP服务器")
            return

        path = self.upload_path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请选择上传文件或目录")
            return

        host = self.ftp_client_host.text().strip()
        port = int(self.ftp_client_port.text().strip())
        user = self.ftp_client_user.text().strip()
        password = self.ftp_client_pass.text().strip()
        ssl = self.ftp_client_ssl.isChecked()
        passive = self.ftp_client_passive.isChecked()

        remote_path = self.current_ftp_path

        self.ftp_thread = FTPThread('upload', host, port, user, password, ssl, passive, path, remote_path)
        self.ftp_thread.progress_signal.connect(self.update_transfer_progress)
        self.ftp_thread.finished_signal.connect(self.on_transfer_finished)
        self.ftp_thread.history_signal.connect(self.add_transfer_history)
        self.ftp_thread.start()

    def download_files(self):
        if not self.ftp_client:
            QMessageBox.warning(self, "提示", "请先连接FTP服务器")
            return

        selected_rows = set()
        for item in self.ftp_file_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.warning(self, "提示", "请在左侧选择要下载的文件")
            return

        folder = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if not folder:
            return

        host = self.ftp_client_host.text().strip()
        port = int(self.ftp_client_port.text().strip())
        user = self.ftp_client_user.text().strip()
        password = self.ftp_client_pass.text().strip()
        ssl = self.ftp_client_ssl.isChecked()
        passive = self.ftp_client_passive.isChecked()

        remote_files = []
        for row in selected_rows:
            filename = self.ftp_file_table.item(row, 0).text()
            remote_files.append(filename)

        self.ftp_thread = FTPThread('download', host, port, user, password, ssl, passive, folder, self.current_ftp_path, remote_files)
        self.ftp_thread.progress_signal.connect(self.update_transfer_progress)
        self.ftp_thread.finished_signal.connect(self.on_transfer_finished)
        self.ftp_thread.history_signal.connect(self.add_transfer_history)
        self.ftp_thread.start()

    def update_transfer_progress(self, progress, filename):
        self.transfer_progress.setValue(progress)

    def on_transfer_finished(self, success, msg):
        if success:
            QMessageBox.information(self, "提示", msg)
        else:
            QMessageBox.warning(self, "提示", msg)
        self.transfer_progress.setValue(0)
        self.refresh_ftp_files()

    def add_transfer_history(self, direction, filename, remote_path, size, status):
        row = self.transfer_history_table.rowCount()
        self.transfer_history_table.insertRow(row)
        self.transfer_history_table.setItem(row, 0, QTableWidgetItem(direction))
        self.transfer_history_table.setItem(row, 1, QTableWidgetItem(filename))
        self.transfer_history_table.setItem(row, 2, QTableWidgetItem(remote_path))
        self.transfer_history_table.setItem(row, 3, QTableWidgetItem(size))
        self.transfer_history_table.setItem(row, 4, QTableWidgetItem(status))
        self.transfer_history_table.setItem(row, 5, QTableWidgetItem(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    def clear_transfer_history(self):
        self.transfer_history_table.setRowCount(0)

    def browse_ftp_server_root(self):
        directory = QFileDialog.getExistingDirectory(self, "选择FTP根目录")
        if directory:
            self.ftp_server_root.setText(directory)

    def start_ftp_server(self):
        port = int(self.ftp_server_port.text().strip())
        user = self.ftp_server_user.text().strip()
        password = self.ftp_server_pass.text().strip()
        root_dir = self.ftp_server_root.text().strip()

        if not root_dir:
            QMessageBox.warning(self, "提示", "请选择根目录")
            return

        if not os.path.isdir(root_dir):
            QMessageBox.warning(self, "提示", "根目录不存在")
            return

        self.ftp_server_handler.log_callback = self._on_ftp_server_log
        success, msg = self.ftp_server_handler.start(port, user, password, root_dir)
        self.ftp_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

        if success:
            self.ftp_server_status.setText("Running")
            self.ftp_server_status.setStyleSheet("color: #27ae60; font-size: 12px;")
            self.ftp_server_stop_btn.setEnabled(True)
            QMessageBox.information(self, "提示", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def stop_ftp_server(self):
        msg = self.ftp_server_handler.stop()
        self.ftp_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")
        self.ftp_server_status.setText("Stopped")
        self.ftp_server_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        self.ftp_server_stop_btn.setEnabled(False)
        QMessageBox.information(self, "提示", msg)

    def clear_ftp_logs(self):
        self.ftp_server_log.clear()

    def _on_ftp_server_log(self, msg):
        self.ftp_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

    def browse_http_server_root(self):
        directory = QFileDialog.getExistingDirectory(self, "选择HTTP根目录")
        if directory:
            self.http_server_root.setText(directory)

    def start_http_server(self):
        port = int(self.http_server_port.text().strip())
        root_dir = self.http_server_root.text().strip()

        if not root_dir:
            QMessageBox.warning(self, "提示", "请选择根目录")
            return

        if not os.path.isdir(root_dir):
            QMessageBox.warning(self, "提示", "根目录不存在")
            return

        self.http_handler.log_callback = self._on_http_server_log
        success, msg = self.http_handler.start(port, root_dir)
        self.http_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

        if success:
            self.http_server_status.setText("Running")
            self.http_server_status.setStyleSheet("color: #27ae60; font-size: 12px;")
            self.http_server_stop_btn.setEnabled(True)
            self.http_access_url.setText(f"http://localhost:{port}")
            QMessageBox.information(self, "提示", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def stop_http_server(self):
        msg = self.http_handler.stop()
        self.http_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")
        self.http_server_status.setText("Stopped")
        self.http_server_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        self.http_server_stop_btn.setEnabled(False)
        QMessageBox.information(self, "提示", msg)

    def clear_http_logs(self):
        self.http_server_log.clear()

    def _on_http_server_log(self, msg):
        self.http_server_log.append(msg)

    def browse_tftp_server_root(self):
        directory = QFileDialog.getExistingDirectory(self, "选择TFTP根目录")
        if directory:
            self.tftp_server_root.setText(directory)

    def start_tftp_server(self):
        port = int(self.tftp_server_port.text().strip())
        root_dir = self.tftp_server_root.text().strip()

        if not root_dir:
            QMessageBox.warning(self, "提示", "请选择根目录")
            return

        if not os.path.isdir(root_dir):
            QMessageBox.warning(self, "提示", "根目录不存在")
            return

        self.tftp_handler.log_callback = self._on_tftp_server_log
        success, msg = self.tftp_handler.start(port, root_dir)
        self.tftp_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

        if success:
            self.tftp_server_status.setText("Running")
            self.tftp_server_status.setStyleSheet("color: #27ae60; font-size: 12px;")
            self.tftp_server_stop_btn.setEnabled(True)
            QMessageBox.information(self, "提示", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def stop_tftp_server(self):
        msg = self.tftp_handler.stop()
        self.tftp_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")
        self.tftp_server_status.setText("Stopped")
        self.tftp_server_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        self.tftp_server_stop_btn.setEnabled(False)
        QMessageBox.information(self, "提示", msg)

    def clear_tftp_logs(self):
        self.tftp_server_log.clear()

    def _on_tftp_server_log(self, msg):
        self.tftp_server_log.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

    def cleanup(self):
        if self.ftp_server_handler.is_running:
            self.ftp_server_handler.stop()
        if self.http_handler.is_running:
            self.http_handler.stop()
        if self.tftp_handler.is_running:
            self.tftp_handler.stop()
        if self.ftp_thread:
            self.ftp_thread.stop()