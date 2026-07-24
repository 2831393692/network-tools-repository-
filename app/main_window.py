from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QPushButton, QStatusBar,
    QLabel, QFrame, QSizePolicy, QMessageBox,
    QScrollArea
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon

from app.ui.dashboard import DashboardPage
from app.ui.ping_test import PingTestPage
from app.ui.traceroute import TraceroutePage
from app.ui.port_scan import PortScanPage
from app.ui.host_discovery import HostDiscoveryPage
from app.ui.camera_scan import CameraScanPage
from app.ui.tools import ToolsPage
from app.ui.network_health import NetworkHealthPage
from app.ui.speed_external import SpeedExternalPage
from app.ui.speed_internal import SpeedInternalPage
from app.ui.speed_session import SpeedSessionPage
from app.ui.packet_capture import PacketCapturePage
from app.ui.protocol_analysis import ProtocolAnalysisPage
from app.ui.dhcp_check import DHCPCheckPage
from app.ui.subnet_calc import SubnetCalcPage
from app.ui.mac_tool import MACAddressToolPage
from app.ui.ip_info import IPInfoCheckPage
from app.ui.route_table import RouteTablePage
from app.ui.connection_test import ConnectionTestPage
from app.ui.network_service import NetworkServicePage
from app.ui.local_settings import LocalSettingsPage
from app.ui.firewall import FirewallPage
from app.ui.remote_terminal import RemoteTerminalPage
from app.ui.link_monitor import LinkMonitorPage
from app.ui.traffic_monitor import TrafficMonitorPage
from app.ui.about import AboutPage
from app.ui.remote_desktop import RemoteDesktopPage
from app.ui.serial_debug import SerialDebugPage
from app.ui.placeholder import PlaceholderPage
from app.core.permission import AdminChecker
from app.core.logger import Logger


class NavGroupButton(QPushButton):
    def __init__(self, title, color, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = color
        self.is_expanded = True
        self.setText(f"▼  {title}")
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self.get_style())
        self.setFixedHeight(38)
    
    def get_style(self):
        return f"""
            QPushButton {{
                background-color: {self.color};
                color: white;
                border: none;
                padding: 10px 15px;
                text-align: left;
                font-size: 13px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {self.color};
                opacity: 0.9;
            }}
        """
    
    def set_expanded(self, expanded):
        self.is_expanded = expanded
        if expanded:
            self.setText(f"▼  {self.title}")
        else:
            self.setText(f"▶  {self.title}")


class NavItemButton(QPushButton):
    def __init__(self, name, key, page_class, parent=None):
        super().__init__(parent)
        self.name = name
        self.key = key
        self.page_class = page_class
        self.setText(f"      {name}")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                color: #555;
                background-color: transparent;
                border: none;
                padding: 8px 15px 8px 30px;
                text-align: left;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #e8f4fd;
                color: #1976d2;
            }
            QPushButton:checked {
                background-color: #e3f2fd;
                color: #1976d2;
                border-left: 3px solid #1976d2;
                font-weight: bold;
            }
        """)
        self.setFixedHeight(32)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = Logger()
        self.current_page = None
        self.current_key = None
        self.all_nav_buttons = []
        self.group_widgets = {}
        self.init_ui()
        self.switch_page("dashboard", DashboardPage)
    
    def init_ui(self):
        self.setWindowTitle("网络测试工具箱")
        self.setMinimumSize(1100, 650)
        self.resize(1280, 720)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.splitter)
        
        self.create_sidebar()
        self.create_content_area()
        self.create_status_bar()
    
    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet("""
            QFrame {
                background-color: #f5f7fa;
                border-right: 1px solid #e0e0e0;
            }
        """)
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        title_label = QLabel("网络测试工具箱")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 15px;
                background-color: #2c3e50;
                border-bottom: 2px solid #34495e;
                font-family: "Microsoft YaHei";
            }
        """)
        sidebar_layout.addWidget(title_label)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f5f7fa;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #ccc;
                border-radius: 3px;
            }
        """)
        
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        
        nav_groups = [
            ("概览", "#5b9bd5", [
                ("仪表盘", "dashboard", DashboardPage),
            ]),
            ("诊断检测", "#70ad47", [
                ("网络健康", "network_health", NetworkHealthPage),
                ("Ping测试", "ping", PingTestPage),
                ("路由追踪", "traceroute", TraceroutePage),
                ("端口扫描", "port_scan", PortScanPage),
                ("主机发现", "host_discovery", HostDiscoveryPage),
                ("摄像头扫描", "camera_scan", CameraScanPage),
                ("安全自测", "security_test", None),
                ("日志审计", "log_audit", None),
            ]),
            ("速度测试", "#ed7d31", [
                ("外网测速", "speed_external", SpeedExternalPage),
                ("内网测速", "speed_internal", SpeedInternalPage),
                ("会话测试", "speed_session", SpeedSessionPage),
            ]),
            ("网络分析", "#7030a0", [
                ("数据包抓包", "packet_capture", PacketCapturePage),
                ("协议分析", "protocol_analysis", ProtocolAnalysisPage),
                ("DHCP检测", "dhcp_check", DHCPCheckPage),
            ]),
            ("实用工具", "#4472c4", [
                ("子网计算", "subnet_calc", SubnetCalcPage),
                ("IP信息检测", "ip_info", IPInfoCheckPage),
                ("MAC地址", "mac_tool", MACAddressToolPage),
                ("路由表", "route_table", RouteTablePage),
                ("连接测试", "connection_test", ConnectionTestPage),
            ]),
            ("网络服务", "#a5a5a5", [
                ("网络服务", "network_service", NetworkServicePage),
                ("本机设置", "local_settings", LocalSettingsPage),
                ("防火墙配置", "firewall", FirewallPage),
            ]),
            ("监控运维", "#264478", [
                ("链路监控", "link_monitor", LinkMonitorPage),
                ("流量监控", "traffic_monitor", TrafficMonitorPage),
            ]),
            ("远程工具", "#636363", [
                ("远程终端", "remote_terminal", RemoteTerminalPage),
                ("远程桌面", "remote_desktop", RemoteDesktopPage),
                ("串口调试", "serial_debug", SerialDebugPage),
            ]),
            ("智能系统", "#7e6000", [
                ("关于和支持", "about", AboutPage),
            ]),
        ]
        
        for group_title, color, items in nav_groups:
            group_btn = NavGroupButton(group_title, color)
            group_btn.clicked.connect(lambda checked, gt=group_title: self.toggle_group(gt))
            nav_layout.addWidget(group_btn)
            
            for item_name, item_key, page_class in items:
                if page_class is None:
                    page_class = PlaceholderPage
                
                item_btn = NavItemButton(item_name, item_key, page_class)
                item_btn.clicked.connect(lambda checked, k=item_key, pc=page_class, n=item_name: self.switch_page(k, pc, n))
                nav_layout.addWidget(item_btn)
                self.all_nav_buttons.append((item_btn, item_key))
                self.group_widgets.setdefault(group_title, []).append(item_btn)
        
        nav_layout.addStretch()
        scroll_area.setWidget(nav_container)
        sidebar_layout.addWidget(scroll_area, 1)
        
        admin_status = QLabel("管理员: " + ("是" if AdminChecker.is_admin() else "否"))
        admin_status.setAlignment(Qt.AlignCenter)
        admin_status.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 10px;
                padding: 8px;
                background-color: #ecf0f1;
                border-top: 1px solid #ddd;
            }
        """)
        sidebar_layout.addWidget(admin_status)
        
        self.splitter.addWidget(self.sidebar)
    
    def toggle_group(self, group_title):
        if group_title not in self.group_widgets:
            return
        
        items = self.group_widgets[group_title]
        any_visible = any(item.isVisible() for item in items)
        new_state = not any_visible
        
        for item in items:
            item.setVisible(new_state)
        
        for i in range(self.sidebar.findChildren(NavGroupButton).__len__()):
            btn = self.sidebar.findChildren(NavGroupButton)[i]
            if btn.title == group_title:
                btn.set_expanded(new_state)
                break
    
    def create_content_area(self):
        self.content_area = QFrame()
        self.content_area.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        
        self.page_container = QWidget()
        self.page_layout = QVBoxLayout(self.page_container)
        self.page_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addWidget(self.page_container)
        
        self.splitter.addWidget(self.content_area)
        self.splitter.setSizes([200, 1100])
    
    def create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        
        self.network_status = QLabel("网络: 正常")
        self.status_bar.addPermanentWidget(self.network_status)
    
    def switch_page(self, page_key, page_class, page_name=None):
        for btn, key in self.all_nav_buttons:
            btn.setChecked(key == page_key)
        
        if self.current_page:
            # 优先调用清理方法，防止后台线程继续向已删除的UI对象发信号
            for cleanup_method in ['cleanup', 'stop_all', 'stop_update_timer']:
                if hasattr(self.current_page, cleanup_method):
                    try:
                        getattr(self.current_page, cleanup_method)()
                    except Exception:
                        pass
                    break
            self.current_page.deleteLater()
        
        try:
            if page_name is None:
                page_name = page_key
            
            if page_class is PlaceholderPage:
                self.current_page = page_class(page_name, self)
            else:
                self.current_page = page_class(self)
            self.page_layout.addWidget(self.current_page)
            self.current_key = page_key
            
            display_name = self.get_page_name(page_key) if not page_name else page_name
            self.status_label.setText(f"当前页面: {display_name}")
            self.logger.info(f"切换到页面: {page_key}")
        except Exception as e:
            self.logger.error(f"切换页面失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"加载页面失败: {str(e)}")
    
    def get_page_name(self, page_key):
        names = {
            "dashboard": "仪表盘",
            "ping": "Ping测试",
            "traceroute": "路由追踪",
            "port_scan": "端口扫描",
            "host_discovery": "主机发现",
            "route_table": "路由表",
            "tools": "实用工具",
        }
        return names.get(page_key, page_key)
    
    def update_status(self, text):
        self.status_label.setText(text)
    
    def show_message(self, message, type="info"):
        if type == "error":
            QMessageBox.critical(self, "错误", message)
        elif type == "warning":
            QMessageBox.warning(self, "警告", message)
        elif type == "question":
            return QMessageBox.question(self, "确认", message, QMessageBox.Yes | QMessageBox.No)
        else:
            QMessageBox.information(self, "提示", message)
