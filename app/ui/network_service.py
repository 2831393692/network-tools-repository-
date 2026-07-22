"""网络服务页面 - 包含TFTP/FTP/Syslog/HTTP文件分发/DHCP服务器功能

本页面提供多种网络服务的配置和管理功能，所有服务均通过后台线程启动，
避免阻塞UI主线程。页面切换时会调用cleanup()终止所有服务。
"""
import socket
import subprocess
import os
import platform
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTabWidget, QComboBox,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QTextCursor

from app.core.logger import Logger

logger = Logger("NetworkService")


class TFTPHandler:
    """TFTP服务器处理器"""
    def __init__(self):
        self.server = None
        self.is_running = False

    def start(self, host, port, root_dir):
        """启动TFTP服务器"""
        try:
            import tftpy
            self.server = tftpy.TftpServer(root_dir)
            Thread(target=self._run, args=(host, port), daemon=True).start()
            self.is_running = True
            return True, f"TFTP服务器已启动在 {host}:{port}"
        except ImportError:
            return False, "未安装tftpy库，请运行: pip install tftpy"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def _run(self, host, port):
        try:
            self.server.listen(host, port)
        except Exception:
            pass

    def stop(self):
        """停止TFTP服务器"""
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        self.is_running = False
        return "TFTP服务器已停止"


class HTTPFileServer:
    """HTTP文件分发服务器"""
    def __init__(self):
        self.server = None
        self.is_running = False

    def start(self, host, port, root_dir):
        """启动HTTP文件服务器"""
        try:
            os.chdir(root_dir)
            self.server = HTTPServer((host, port), SimpleHTTPRequestHandler)
            Thread(target=self.server.serve_forever, daemon=True).start()
            self.is_running = True
            return True, f"HTTP文件服务器已启动在 http://{host}:{port}"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def stop(self):
        """停止HTTP文件服务器"""
        if self.server:
            self.server.shutdown()
        self.is_running = False
        return "HTTP文件服务器已停止"


class NetworkServicePage(QWidget):
    """网络服务主页面"""
    
    log_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.tftp_handler = TFTPHandler()
        self.http_handler = HTTPFileServer()
        self.init_ui()
        self.log_signal.connect(self.append_log)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(0)

        # 顶部Tab导航
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::tab-bar { alignment: center; }
            QTabBar::tab {
                background-color: #00bcd4;
                color: white;
                padding: 10px 25px;
                font-size: 13px;
                font-weight: bold;
                border: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #0097a7;
            }
            QTabBar::tab:hover {
                background-color: #00acc1;
            }
        """)

        # TFTP服务器页面
        self.tftp_page = self._build_tftp_page()
        self.tab_widget.addTab(self.tftp_page, "📦 TFTP服务器")

        # FTP服务器页面（占位）
        self.ftp_page = self._build_ftp_page()
        self.tab_widget.addTab(self.ftp_page, "📁 FTP服务器")

        # Syslog服务器页面（占位）
        self.syslog_page = self._build_syslog_page()
        self.tab_widget.addTab(self.syslog_page, "📋 Syslog服务器")

        # HTTP文件分发页面
        self.http_page = self._build_http_page()
        self.tab_widget.addTab(self.http_page, "🌐 HTTP文件分发")

        # DHCP服务器页面（占位）
        self.dhcp_page = self._build_dhcp_page()
        self.tab_widget.addTab(self.dhcp_page, "🔌 DHCP服务器")

        layout.addWidget(self.tab_widget)

    def _build_tftp_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(12)

        # 左侧：配置和说明区域
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)

        # TFTP服务器配置
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(15, 12, 15, 12)
        config_layout.setSpacing(10)

        title = QLabel("⚙️ TFTP服务器配置")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        config_layout.addWidget(title)

        # 监听地址
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("监听地址:"))
        self.tftp_host_input = QLineEdit("0.0.0.0")
        row1.addWidget(self.tftp_host_input)
        config_layout.addLayout(row1)

        # 监听端口
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("监听端口:"))
        self.tftp_port_input = QLineEdit("69")
        row2.addWidget(self.tftp_port_input)
        config_layout.addLayout(row2)

        # 根目录
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("根目录:"))
        self.tftp_dir_input = QLineEdit("")
        row3.addWidget(self.tftp_dir_input)

        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd; padding: 4px 10px; border-radius: 3px;")
        browse_btn.clicked.connect(self.browse_tftp_dir)
        row3.addWidget(browse_btn)
        config_layout.addLayout(row3)

        # 启动/停止按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        self.tftp_start_btn = QPushButton("🚀 启动TFTP服务器")
        self.tftp_start_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.tftp_start_btn.clicked.connect(self.start_tftp_server)
        btn_row.addWidget(self.tftp_start_btn)

        self.tftp_stop_btn = QPushButton("⏹️ 停止服务器")
        self.tftp_stop_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.tftp_stop_btn.clicked.connect(self.stop_tftp_server)
        self.tftp_stop_btn.setEnabled(False)
        btn_row.addWidget(self.tftp_stop_btn)

        btn_row.addStretch()
        config_layout.addLayout(btn_row)

        left_layout.addWidget(config_frame)

        # 使用说明
        help_frame = QFrame()
        help_frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        help_layout = QVBoxLayout(help_frame)
        help_layout.setContentsMargins(15, 12, 15, 12)
        help_layout.setSpacing(6)

        help_title = QLabel("📖 使用说明")
        help_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        help_layout.addWidget(help_title)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setStyleSheet("""
            QTextEdit { font-size: 12px; color: #555; border: none; background-color: transparent; }
        """)
        help_text.setPlainText("""TFTP (Trivial File Transfer Protocol) 简单文件传输协议

用途：网络设备固件升级、配置文件传输
端口：UDP 69（默认）
特点：无需认证、传输简单、适合小文件

使用步骤：
1. 设置根目录（存放文件的文件夹）
2. 点击"启动TFTP服务器"
3. 在网络设备中配置TFTP服务器地址
4. 设备即可上传/下载文件

⚠️ 注意事项与风险提示：
• 权限要求：端口69需要管理员权限，请以管理员身份运行
• 网络安全：建议在内网环境使用，避免在公网暴露服务
• 传输安全：不支持加密传输，请勿传输敏感数据
• 端口占用：启动服务会占用UDP 69端口，确保端口未被占用
• 防火墙规则：可能需要配置防火墙允许UDP 69端口通信
• 数据安全：建议仅访问非敏感文件，避免泄露重要信息
• 访问控制：默认无访问控制，建议在内网隔离环境使用
• 性能影响：大量文件传输可能影响网络性能，请合理安排
• 法规合规：请确保文件传输符合相关法律法规要求""")
        help_layout.addWidget(help_text)

        left_layout.addWidget(help_frame)

        layout.addLayout(left_layout, 1)

        # 右侧：服务器日志
        right_layout = QVBoxLayout()
        
        log_frame = QFrame()
        log_frame.setStyleSheet("""
            QFrame { background-color: #1a1a1a; border: 1px solid #333; border-radius: 5px; }
        """)
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(8)

        log_title = QLabel("📊 服务器日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        log_layout.addWidget(log_title)

        self.tftp_log = QTextEdit()
        self.tftp_log.setReadOnly(True)
        self.tftp_log.setStyleSheet("""
            QTextEdit { font-size: 12px; color: #00ff00; background-color: #1a1a1a; border: none; font-family: Consolas; }
        """)
        log_layout.addWidget(self.tftp_log)

        right_layout.addWidget(log_frame)
        layout.addLayout(right_layout, 1)

        return page

    def _build_ftp_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 12, 15, 12)
        
        label = QLabel("FTP服务器功能开发中...")
        label.setStyleSheet("font-size: 14px; color: #999;")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        return page

    def _build_syslog_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 12, 15, 12)
        
        label = QLabel("Syslog服务器功能开发中...")
        label.setStyleSheet("font-size: 14px; color: #999;")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        return page

    def _build_http_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(12)

        # 左侧：配置区域
        left_layout = QVBoxLayout()
        
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(15, 12, 15, 12)
        config_layout.setSpacing(10)

        title = QLabel("⚙️ HTTP文件分发配置")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        config_layout.addWidget(title)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("监听地址:"))
        self.http_host_input = QLineEdit("0.0.0.0")
        row1.addWidget(self.http_host_input)
        config_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("监听端口:"))
        self.http_port_input = QLineEdit("8080")
        row2.addWidget(self.http_port_input)
        config_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("根目录:"))
        self.http_dir_input = QLineEdit("")
        row3.addWidget(self.http_dir_input)

        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd; padding: 4px 10px; border-radius: 3px;")
        browse_btn.clicked.connect(self.browse_http_dir)
        row3.addWidget(browse_btn)
        config_layout.addLayout(row3)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        self.http_start_btn = QPushButton("🚀 启动HTTP服务器")
        self.http_start_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.http_start_btn.clicked.connect(self.start_http_server)
        btn_row.addWidget(self.http_start_btn)

        self.http_stop_btn = QPushButton("⏹️ 停止服务器")
        self.http_stop_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.http_stop_btn.clicked.connect(self.stop_http_server)
        self.http_stop_btn.setEnabled(False)
        btn_row.addWidget(self.http_stop_btn)

        btn_row.addStretch()
        config_layout.addLayout(btn_row)

        left_layout.addWidget(config_frame)
        left_layout.addStretch()
        layout.addLayout(left_layout, 1)

        # 右侧：日志
        right_layout = QVBoxLayout()
        
        log_frame = QFrame()
        log_frame.setStyleSheet("""
            QFrame { background-color: #1a1a1a; border: 1px solid #333; border-radius: 5px; }
        """)
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        
        log_title = QLabel("📊 服务器日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        log_layout.addWidget(log_title)

        self.http_log = QTextEdit()
        self.http_log.setReadOnly(True)
        self.http_log.setStyleSheet("""
            QTextEdit { font-size: 12px; color: #00ff00; background-color: #1a1a1a; border: none; font-family: Consolas; }
        """)
        log_layout.addWidget(self.http_log)

        right_layout.addWidget(log_frame)
        layout.addLayout(right_layout, 1)

        return page

    def _build_dhcp_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 12, 15, 12)
        
        label = QLabel("DHCP服务器功能开发中...")
        label.setStyleSheet("font-size: 14px; color: #999;")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        return page

    def browse_tftp_dir(self):
        """浏览选择TFTP根目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择TFTP根目录")
        if directory:
            self.tftp_dir_input.setText(directory)

    def browse_http_dir(self):
        """浏览选择HTTP根目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择HTTP根目录")
        if directory:
            self.http_dir_input.setText(directory)

    def start_tftp_server(self):
        """启动TFTP服务器"""
        host = self.tftp_host_input.text().strip()
        port = int(self.tftp_port_input.text().strip())
        root_dir = self.tftp_dir_input.text().strip()

        if not root_dir:
            QMessageBox.warning(self, "提示", "请选择根目录")
            return

        if not os.path.isdir(root_dir):
            QMessageBox.warning(self, "提示", "根目录不存在")
            return

        success, msg = self.tftp_handler.start(host, port, root_dir)
        self.append_log(msg)

        if success:
            self.tftp_start_btn.setEnabled(False)
            self.tftp_stop_btn.setEnabled(True)
            QMessageBox.information(self, "提示", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def stop_tftp_server(self):
        """停止TFTP服务器"""
        msg = self.tftp_handler.stop()
        self.append_log(msg)
        self.tftp_start_btn.setEnabled(True)
        self.tftp_stop_btn.setEnabled(False)
        QMessageBox.information(self, "提示", msg)

    def start_http_server(self):
        """启动HTTP文件服务器"""
        host = self.http_host_input.text().strip()
        port = int(self.http_port_input.text().strip())
        root_dir = self.http_dir_input.text().strip()

        if not root_dir:
            QMessageBox.warning(self, "提示", "请选择根目录")
            return

        if not os.path.isdir(root_dir):
            QMessageBox.warning(self, "提示", "根目录不存在")
            return

        success, msg = self.http_handler.start(host, port, root_dir)
        self.http_log.append(msg)

        if success:
            self.http_start_btn.setEnabled(False)
            self.http_stop_btn.setEnabled(True)
            QMessageBox.information(self, "提示", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def stop_http_server(self):
        """停止HTTP文件服务器"""
        msg = self.http_handler.stop()
        self.http_log.append(msg)
        self.http_start_btn.setEnabled(True)
        self.http_stop_btn.setEnabled(False)
        QMessageBox.information(self, "提示", msg)

    def append_log(self, msg):
        """追加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.tftp_log.append(f"[{timestamp}] {msg}")
        cursor = self.tftp_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.tftp_log.setTextCursor(cursor)

    def cleanup(self):
        """页面清理"""
        if self.tftp_handler.is_running:
            self.tftp_handler.stop()
        if self.http_handler.is_running:
            self.http_handler.stop()