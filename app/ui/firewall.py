"""防火墙配置页面 - 包含快速配置、高级规则、规则管理功能

本页面提供Windows防火墙的可视化配置功能，支持快速配置、
高级规则设置和规则管理。所有功能通过PowerShell命令实现。
"""
import subprocess
import platform
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTabWidget, QComboBox,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor

from app.core.logger import Logger

logger = Logger("Firewall")


class FirewallPage(QWidget):
    """防火墙配置主页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._first_show = True
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # 左侧：配置区域
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)

        # Tab导航
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                background-color: #f5f7fa;
                color: #555;
                padding: 8px 16px;
                font-size: 12px;
                border: 1px solid #e0e0e0;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #1976d2;
                border-color: #1976d2;
            }
        """)

        # 快速配置Tab
        self.quick_config_page = self._build_quick_config_page()
        self.tab_widget.addTab(self.quick_config_page, "⚡ 快速配置")

        # 高级规则Tab（占位）
        self.advanced_rules_page = self._build_advanced_rules_page()
        self.tab_widget.addTab(self.advanced_rules_page, "🔧 高级规则")

        # 规则管理Tab（占位）
        self.rule_management_page = self._build_rule_management_page()
        self.tab_widget.addTab(self.rule_management_page, "📋 规则管理")

        left_layout.addWidget(self.tab_widget)
        layout.addLayout(left_layout, 1)

        # 右侧：操作日志
        right_layout = QVBoxLayout()

        log_frame = QFrame()
        log_frame.setStyleSheet("""
            QFrame { background-color: #1a1a1a; border: 1px solid #333; border-radius: 5px; }
        """)
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(8)

        log_title = QLabel("🔥 防火墙操作日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        log_layout.addWidget(log_title)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit { font-size: 12px; color: #00ff00; background-color: #1a1a1a; border: none; font-family: Consolas; }
        """)
        log_layout.addWidget(self.log_text)

        right_layout.addWidget(log_frame)
        layout.addLayout(right_layout, 1)

        # 初始化日志
        self.append_log("=== 防火墙配置面板已加载 ===")

    def showEvent(self, event):
        """页面显示事件（保留占位，目前不需要延迟加载）"""
        super().showEvent(event)

    def _build_quick_config_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        # 规则名称
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("规则名称:"))
        self.rule_name_input = QLineEdit("网络工具箱_远程桌面放行")
        row1.addWidget(self.rule_name_input)
        layout.addLayout(row1)

        # 方向
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("方向:"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["in", "out"])
        self.direction_combo.setCurrentText("in")
        row2.addWidget(self.direction_combo)
        layout.addLayout(row2)

        # 动作
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("动作:"))
        self.action_combo = QComboBox()
        self.action_combo.addItems(["allow", "block"])
        self.action_combo.setCurrentText("allow")
        row3.addWidget(self.action_combo)
        layout.addLayout(row3)

        # 配置文件
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("配置文件:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["any", "domain", "public", "private"])
        self.profile_combo.setCurrentText("any")
        row4.addWidget(self.profile_combo)
        layout.addLayout(row4)

        # 应用路径
        row5 = QHBoxLayout()
        row5.addWidget(QLabel("应用路径:"))
        self.app_path_input = QLineEdit("")
        row5.addWidget(self.app_path_input)

        browse_btn = QPushButton("📁")
        browse_btn.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd; padding: 4px 8px; border-radius: 3px;")
        browse_btn.clicked.connect(self.browse_app_path)
        row5.addWidget(browse_btn)
        layout.addLayout(row5)

        add_app_btn = QPushButton("➕ 添加应用规则")
        add_app_btn.setStyleSheet("background-color: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        add_app_btn.clicked.connect(self.add_app_rule)
        layout.addWidget(add_app_btn)

        # 分隔线
        separator = QFrame()
        separator.setStyleSheet("QFrame { background-color: #e0e0e0; height: 1px; }")
        layout.addWidget(separator)

        # 端口/协议
        row6 = QHBoxLayout()
        row6.addWidget(QLabel("端口/协议:"))
        self.port_input = QLineEdit("3389")
        row6.addWidget(self.port_input)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["TCP", "UDP"])
        self.protocol_combo.setCurrentText("TCP")
        row6.addWidget(self.protocol_combo)
        layout.addLayout(row6)

        add_port_btn = QPushButton("➕ 添加端口规则")
        add_port_btn.setStyleSheet("background-color: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        add_port_btn.clicked.connect(self.add_port_rule)
        layout.addWidget(add_port_btn)

        # 分隔线
        separator2 = QFrame()
        separator2.setStyleSheet("QFrame { background-color: #e0e0e0; height: 1px; }")
        layout.addWidget(separator2)

        # 一键模板
        template_title = QLabel("⚡ 一键模板")
        template_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        layout.addWidget(template_title)

        template_row = QHBoxLayout()
        template_row.setSpacing(8)

        rdp_btn = QPushButton("🖥️ 远程桌面")
        rdp_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 6px 12px; border-radius: 3px;")
        rdp_btn.clicked.connect(lambda: self.apply_template("rdp"))
        template_row.addWidget(rdp_btn)

        web_btn = QPushButton("🌐 网页服务")
        web_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 6px 12px; border-radius: 3px;")
        web_btn.clicked.connect(lambda: self.apply_template("web"))
        template_row.addWidget(web_btn)

        ftp_btn = QPushButton("📁 FTP")
        ftp_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 6px 12px; border-radius: 3px;")
        ftp_btn.clicked.connect(lambda: self.apply_template("ftp"))
        template_row.addWidget(ftp_btn)

        status_btn = QPushButton("📊 查看状态")
        status_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 6px 12px; border-radius: 3px;")
        status_btn.clicked.connect(self.check_status)
        template_row.addWidget(status_btn)

        template_row.addStretch()
        layout.addLayout(template_row)

        # 模板下拉
        template_combo_row = QHBoxLayout()
        template_combo_row.setSpacing(10)

        template_combo_row.addWidget(QLabel("模板:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "放行远程桌面 (3389)",
            "放行网页服务 (80/443)",
            "放行FTP服务 (21)",
            "放行SSH (22)",
            "放行TFTP (69)",
            "放行HTTP文件服务 (8080)",
        ])
        template_combo_row.addWidget(self.template_combo)

        apply_btn = QPushButton("📋 套用")
        apply_btn.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd; padding: 6px 12px; border-radius: 3px;")
        apply_btn.clicked.connect(self.apply_selected_template)
        template_combo_row.addWidget(apply_btn)

        quick_add_btn = QPushButton("⚡ 一键添加")
        quick_add_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 6px 12px; border-radius: 3px;")
        quick_add_btn.clicked.connect(self.quick_add_rule)
        template_combo_row.addWidget(quick_add_btn)

        template_combo_row.addStretch()
        layout.addLayout(template_combo_row)

        # 使用建议
        help_frame = QFrame()
        help_frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        help_layout = QVBoxLayout(help_frame)
        help_layout.setContentsMargins(12, 10, 12, 10)
        help_layout.setSpacing(6)

        help_title = QLabel("📖 使用建议")
        help_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        help_layout.addWidget(help_title)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setStyleSheet("""
            QTextEdit { font-size: 11px; color: #555; border: none; background-color: transparent; }
        """)
        help_text.setPlainText("""• 建议：优先使用"快捷模板"
• 方向: in=入站(外面访问你), out=出站(你访问外面)
• 动作: allow=允许, block=拦截
• 需要管理员权限才能成功写入规则""")
        help_layout.addWidget(help_text)

        layout.addWidget(help_frame)

        return page

    def _build_advanced_rules_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        # 五元组 + 应用 + 域名 标题
        section_title = QLabel("🔧 五元组 + 应用 + 域名")
        section_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #1976d2;")
        layout.addWidget(section_title)

        # 源IP
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("源IP:"))
        self.adv_src_ip = QLineEdit("any")
        row1.addWidget(self.adv_src_ip)
        layout.addLayout(row1)

        # 目的IP
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("目的IP:"))
        self.adv_dst_ip = QLineEdit("any")
        row2.addWidget(self.adv_dst_ip)
        layout.addLayout(row2)

        # 源端口
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("源端口:"))
        self.adv_src_port = QLineEdit("any")
        row3.addWidget(self.adv_src_port)
        layout.addLayout(row3)

        # 目的端口
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("目的端口:"))
        self.adv_dst_port = QLineEdit("any")
        row4.addWidget(self.adv_dst_port)
        layout.addLayout(row4)

        # 绑定应用
        row5 = QHBoxLayout()
        row5.addWidget(QLabel("绑定应用:"))
        self.adv_app_path = QLineEdit("")
        row5.addWidget(self.adv_app_path)

        adv_browse_btn = QPushButton("📁")
        adv_browse_btn.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd; padding: 4px 8px; border-radius: 3px;")
        adv_browse_btn.clicked.connect(self.browse_adv_app_path)
        row5.addWidget(adv_browse_btn)
        layout.addLayout(row5)

        # 添加五元组规则按钮
        add_five_tuple_btn = QPushButton("✅ 添加五元组规则")
        add_five_tuple_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white;
                border: 1px solid #229954; padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        add_five_tuple_btn.clicked.connect(self.add_five_tuple_rule)
        layout.addWidget(add_five_tuple_btn)

        # 分隔线
        separator = QFrame()
        separator.setStyleSheet("QFrame { background-color: #e0e0e0; height: 1px; }")
        layout.addWidget(separator)

        # 域名规则
        row6 = QHBoxLayout()
        row6.addWidget(QLabel("域名:"))
        self.adv_domain = QLineEdit("")
        row6.addWidget(self.adv_domain)

        add_domain_btn = QPushButton("🌐 添加域名规则")
        add_domain_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white;
                border: 1px solid #229954; padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #229954; }
        """)
        add_domain_btn.clicked.connect(self.add_domain_rule)
        row6.addWidget(add_domain_btn)
        layout.addLayout(row6)

        # 说明
        tip = QLabel("说明：域名规则会先解析为IP，再下发到防火墙（建议定期刷新）。")
        tip.setStyleSheet("font-size: 11px; color: #888;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        layout.addStretch()
        return page

    def _build_rule_management_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        # 常用管理操作 标题
        section_title = QLabel("🛠️ 常用管理操作")
        section_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #1976d2;")
        layout.addWidget(section_title)

        # 提示文字
        tip_label = QLabel("按当前\"规则名称\"执行以下操作：")
        tip_label.setStyleSheet("font-size: 12px; color: #555;")
        layout.addWidget(tip_label)

        # 规则名称输入框
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("规则名称:"))
        self.mgmt_rule_name = QLineEdit("")
        self.mgmt_rule_name.setPlaceholderText("输入要操作的规则名称")
        name_row.addWidget(self.mgmt_rule_name)
        layout.addLayout(name_row)

        # 按钮网格：2行3列
        mgmt_grid = QGridLayout()
        mgmt_grid.setSpacing(8)

        btn_style = """
            QPushButton {
                background-color: #f5f7fa;
                color: #333;
                border: 1px solid #e0e0e0;
                padding: 10px 8px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e8f4fd;
                border-color: #1976d2;
                color: #1976d2;
            }
        """

        query_btn = QPushButton("🔍 查询规则")
        query_btn.setStyleSheet(btn_style)
        query_btn.clicked.connect(self.query_rule)
        mgmt_grid.addWidget(query_btn, 0, 0)

        enable_btn = QPushButton("✅ 启用规则")
        enable_btn.setStyleSheet(btn_style)
        enable_btn.clicked.connect(self.enable_rule)
        mgmt_grid.addWidget(enable_btn, 0, 1)

        disable_btn = QPushButton("⛔ 禁用规则")
        disable_btn.setStyleSheet(btn_style)
        disable_btn.clicked.connect(self.disable_rule)
        mgmt_grid.addWidget(disable_btn, 0, 2)

        delete_btn = QPushButton("🗑️ 删除规则")
        delete_btn.setStyleSheet(btn_style)
        delete_btn.clicked.connect(self.delete_rule_by_name)
        mgmt_grid.addWidget(delete_btn, 1, 0)

        fw_on_btn = QPushButton("🔥 开启防火墙")
        fw_on_btn.setStyleSheet(btn_style)
        fw_on_btn.clicked.connect(self.turn_on_firewall)
        mgmt_grid.addWidget(fw_on_btn, 1, 1)

        status_btn = QPushButton("📊 查看状态")
        status_btn.setStyleSheet(btn_style)
        status_btn.clicked.connect(self.check_status)
        mgmt_grid.addWidget(status_btn, 1, 2)

        layout.addLayout(mgmt_grid)

        # 底部提示
        bottom_tip = QLabel("提示：如果命令失败，请以管理员身份运行程序。")
        bottom_tip.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(bottom_tip)

        layout.addStretch()
        return page

    def browse_app_path(self):
        """浏览选择应用路径"""
        filepath, _ = QFileDialog.getOpenFileName(self, "选择应用程序", "", "可执行文件 (*.exe)")
        if filepath:
            self.app_path_input.setText(filepath)

    def append_log(self, msg):
        """追加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def add_app_rule(self):
        """添加应用规则"""
        rule_name = self.rule_name_input.text().strip()
        direction = self.direction_combo.currentText()
        action = self.action_combo.currentText()
        profile = self.profile_combo.currentText()
        app_path = self.app_path_input.text().strip()

        if not rule_name:
            QMessageBox.warning(self, "提示", "请输入规则名称")
            return

        if not app_path:
            QMessageBox.warning(self, "提示", "请选择应用路径")
            return

        try:
            cmd = f"""
                netsh advfirewall firewall add rule name="{rule_name}" dir={direction} action={action} program="{app_path}" enable=yes profile={profile}
            """
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"✅ 已添加应用规则: {rule_name}")
                QMessageBox.information(self, "提示", "应用规则添加成功")
            else:
                self.append_log(f"❌ 添加失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "需要管理员权限")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")

    def add_port_rule(self):
        """添加端口规则"""
        rule_name = self.rule_name_input.text().strip()
        direction = self.direction_combo.currentText()
        action = self.action_combo.currentText()
        profile = self.profile_combo.currentText()
        port = self.port_input.text().strip()
        protocol = self.protocol_combo.currentText()

        if not rule_name:
            QMessageBox.warning(self, "提示", "请输入规则名称")
            return

        if not port:
            QMessageBox.warning(self, "提示", "请输入端口号")
            return

        try:
            cmd = f"""
                netsh advfirewall firewall add rule name="{rule_name}" dir={direction} action={action} protocol={protocol} localport={port} enable=yes profile={profile}
            """
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"✅ 已添加端口规则: {rule_name} ({port}/{protocol})")
                QMessageBox.information(self, "提示", "端口规则添加成功")
            else:
                self.append_log(f"❌ 添加失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "需要管理员权限")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")

    def apply_template(self, template_type):
        """应用一键模板"""
        templates = {
            "rdp": {"name": "远程桌面 (3389)", "port": "3389", "protocol": "TCP", "direction": "in", "action": "allow"},
            "web": {"name": "网页服务 (80/443)", "port": "80,443", "protocol": "TCP", "direction": "in", "action": "allow"},
            "ftp": {"name": "FTP服务 (21)", "port": "21", "protocol": "TCP", "direction": "in", "action": "allow"},
        }

        template = templates.get(template_type)
        if not template:
            return

        self.rule_name_input.setText(f"网络工具箱_{template['name']}")
        self.port_input.setText(template['port'])
        self.protocol_combo.setCurrentText(template['protocol'])
        self.direction_combo.setCurrentText(template['direction'])
        self.action_combo.setCurrentText(template['action'])

        self.append_log(f"📋 已套用模板: {template['name']}")

    def apply_selected_template(self):
        """套用选中的模板"""
        selected = self.template_combo.currentText()
        if "远程桌面" in selected:
            self.apply_template("rdp")
        elif "网页服务" in selected:
            self.apply_template("web")
        elif "FTP" in selected:
            self.apply_template("ftp")

    def quick_add_rule(self):
        """一键添加规则"""
        self.add_port_rule()

    def check_status(self):
        """查看防火墙状态"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-NetFirewallProfile | Select-Object Name, Enabled"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                self.append_log(f"📊 防火墙状态:\n{result.stdout}")
            else:
                self.append_log(f"❌ 查询失败: {result.stderr}")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")

    def browse_adv_app_path(self):
        """高级规则 - 浏览选择绑定应用路径"""
        filepath, _ = QFileDialog.getOpenFileName(self, "选择应用程序", "", "可执行文件 (*.exe)")
        if filepath:
            self.adv_app_path.setText(filepath)

    def add_five_tuple_rule(self):
        """添加五元组规则"""
        src_ip = self.adv_src_ip.text().strip() or "any"
        dst_ip = self.adv_dst_ip.text().strip() or "any"
        src_port = self.adv_src_port.text().strip() or "any"
        dst_port = self.adv_dst_port.text().strip() or "any"
        app_path = self.adv_app_path.text().strip()
        rule_name = f"网络工具箱_五元组_{src_ip}_{dst_ip}_{dst_port}"

        try:
            cmd_parts = [f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow']

            if src_ip != "any":
                cmd_parts.append(f'localip={src_ip}')
            if dst_ip != "any":
                cmd_parts.append(f'remoteip={dst_ip}')
            if src_port != "any":
                cmd_parts.append(f'localport={src_port}')
            if dst_port != "any":
                cmd_parts.append(f'remoteport={dst_port}')

            if app_path:
                cmd_parts.append(f'program="{app_path}"')
            else:
                cmd_parts.append('protocol=TCP')

            cmd = " ".join(cmd_parts)
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"✅ 已添加五元组规则: {rule_name}")
                QMessageBox.information(self, "提示", "五元组规则添加成功")
            else:
                self.append_log(f"❌ 添加失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "添加失败，请以管理员身份运行程序")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")
            QMessageBox.warning(self, "提示", f"操作失败: {str(e)}")

    def add_domain_rule(self):
        """添加域名规则（先解析IP再下发）"""
        domain = self.adv_domain.text().strip()
        if not domain:
            QMessageBox.warning(self, "提示", "请输入域名")
            return

        import socket
        try:
            # 解析域名为IP
            ip_list = socket.gethostbyname_ex(domain)[2]
            if not ip_list:
                QMessageBox.warning(self, "提示", "无法解析该域名")
                return

            rule_name = f"网络工具箱_域名_{domain}"
            ips = ",".join(ip_list)
            cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=out action=allow remoteip={ips} description="域名规则: {domain}"'
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"✅ 已添加域名规则: {rule_name} (解析到 {len(ip_list)} 个IP)")
                QMessageBox.information(self, "提示", f"域名规则添加成功，解析到 {len(ip_list)} 个IP")
            else:
                self.append_log(f"❌ 添加失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "添加失败，请以管理员身份运行程序")
        except Exception as e:
            self.append_log(f"❌ 解析或添加失败: {str(e)}")
            QMessageBox.warning(self, "提示", f"操作失败: {str(e)}")

    def query_rule(self):
        """查询指定规则"""
        rule_name = self.mgmt_rule_name.text().strip()
        if not rule_name:
            QMessageBox.warning(self, "提示", "请输入规则名称")
            return

        try:
            result = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
                capture_output=True, text=True, errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and "规则名称" in result.stdout:
                self.append_log(f"📋 查询规则 [{rule_name}]:\n{result.stdout.strip()}")
            else:
                self.append_log(f"❌ 未找到规则: {rule_name}")
                QMessageBox.warning(self, "提示", f"未找到规则: {rule_name}")
        except Exception as e:
            self.append_log(f"❌ 查询失败: {str(e)}")

    def enable_rule(self):
        """启用指定规则"""
        rule_name = self.mgmt_rule_name.text().strip()
        if not rule_name:
            QMessageBox.warning(self, "提示", "请输入规则名称")
            return

        try:
            cmd = f'netsh advfirewall firewall set rule name="{rule_name}" new enable=yes'
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"✅ 已启用规则: {rule_name}")
                QMessageBox.information(self, "提示", "规则已启用")
            else:
                self.append_log(f"❌ 启用失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "启用失败，请以管理员身份运行程序")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")

    def disable_rule(self):
        """禁用指定规则"""
        rule_name = self.mgmt_rule_name.text().strip()
        if not rule_name:
            QMessageBox.warning(self, "提示", "请输入规则名称")
            return

        try:
            cmd = f'netsh advfirewall firewall set rule name="{rule_name}" new enable=no'
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"⛔ 已禁用规则: {rule_name}")
                QMessageBox.information(self, "提示", "规则已禁用")
            else:
                self.append_log(f"❌ 禁用失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "禁用失败，请以管理员身份运行程序")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")

    def delete_rule_by_name(self):
        """按名称删除规则"""
        rule_name = self.mgmt_rule_name.text().strip()
        if not rule_name:
            QMessageBox.warning(self, "提示", "请输入规则名称")
            return

        reply = QMessageBox.question(self, "确认", f"确定要删除规则 [{rule_name}] 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No:
            return

        try:
            cmd = f'netsh advfirewall firewall delete rule name="{rule_name}"'
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log(f"🗑️ 已删除规则: {rule_name}")
                QMessageBox.information(self, "提示", "规则已删除")
            else:
                self.append_log(f"❌ 删除失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "删除失败，请以管理员身份运行程序")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")

    def turn_on_firewall(self):
        """开启防火墙"""
        try:
            cmd = 'Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True'
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                self.append_log("🔥 防火墙已开启（域/专用/公用）")
                QMessageBox.information(self, "提示", "防火墙已开启")
            else:
                self.append_log(f"❌ 开启失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "开启失败，请以管理员身份运行程序")
        except Exception as e:
            self.append_log(f"❌ 操作失败: {str(e)}")
