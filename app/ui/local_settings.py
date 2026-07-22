"""本机设置页面 - 包含系统工具、网络配置等功能

本页面提供常用系统管理功能的快捷入口，包括命令行工具、
系统配置、网络修复等。所有功能通过系统命令或API实现。
"""
import subprocess
import platform
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt

from app.core.logger import Logger

logger = Logger("LocalSettings")


class LocalSettingsPage(QWidget):
    """本机设置主页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # 系统工具区域
        tools_frame = QFrame()
        tools_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        tools_layout = QVBoxLayout(tools_frame)
        tools_layout.setContentsMargins(15, 12, 15, 12)
        tools_layout.setSpacing(12)

        title = QLabel("⚙️ 系统工具")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        tools_layout.addWidget(title)

        # 工具按钮网格（4列）
        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)

        tools = [
            ("💻 打开CMD控制台", self.open_cmd),
            ("💻 打开PowerShell", self.open_powershell),
            ("🛡️ 管理员CMD", self.open_admin_cmd),
            ("🔌 IP地址设置", self.open_ip_settings),
            ("⛔ 关闭防火墙", self.disable_firewall),
            ("✅ 开启防火墙", self.enable_firewall),
            ("📊 防火墙状态", self.check_firewall_status),
            ("🔧 设备管理器", self.open_device_manager),
            ("📋 任务管理器", self.open_task_manager),
            ("📊 系统信息", self.show_system_info),
            ("📝 注册表编辑器", self.open_regedit),
            ("📂 事件查看器", self.open_event_viewer),
            ("💾 磁盘管理", self.open_disk_management),
            ("🔧 服务管理", self.open_service_manager),
            ("📊 资源监视器", self.open_resource_monitor),
            ("🖥️ 计算机管理", self.open_computer_management),
            ("⚙️ 控制面板", self.open_control_panel),
            ("📡 远程桌面", self.open_remote_desktop),
            ("🔢 修改3389端口", self.change_rdp_port),
            ("🔄 恢复3389端口", self.restore_rdp_port),
            ("🔧 网络修复工具", self.run_network_repair),
            ("🔍 网络诊断", self.run_network_diagnostic),
            ("📊 性能监视器", self.open_performance_monitor),
            ("⚙️ 网络设置", self.open_network_settings),
        ]

        for i, (name, callback) in enumerate(tools):
            btn = QPushButton(name)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f5f7fa;
                    color: #333;
                    border: 1px solid #e0e0e0;
                    padding: 12px 8px;
                    border-radius: 5px;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #e8f4fd;
                    border-color: #1976d2;
                    color: #1976d2;
                }
            """)
            btn.clicked.connect(callback)
            grid_layout.addWidget(btn, i // 4, i % 4)

        tools_layout.addLayout(grid_layout)
        layout.addWidget(tools_frame)

        # 操作结果区域
        result_frame = QFrame()
        result_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(15, 12, 15, 12)
        result_layout.setSpacing(8)

        result_title = QLabel("📋 操作结果")
        result_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        result_layout.addWidget(result_title)

        separator = QFrame()
        separator.setStyleSheet("QFrame { background-color: #e0e0e0; height: 1px; }")
        result_layout.addWidget(separator)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit { font-size: 12px; color: #555; border: none; background-color: transparent; }
        """)
        self.result_text.setPlainText("""欢迎使用本机设置工具！这里提供了常用的系统管理功能：

📋 可用功能：
• 打开CMD控制台 - 启动命令提示符
• 打开PowerShell - 启动PowerShell控制台
• 管理员CMD - 以管理员身份启动CMD
• 关闭防火墙 - 关闭Windows防火墙保护
• 开启防火墙 - 启用Windows防火墙保护
• 防火墙状态 - 查看当前防火墙状态
• IP地址设置 - 配置网卡IP地址
• 设备管理器 - 打开设备管理器
• 任务管理器 - 打开任务管理器
• 远程桌面 - 打开远程桌面连接 (mstsc)
• 修改3389端口 - 修改远程桌面端口号
• 恢复3389端口 - 恢复远程桌面默认端口
• 网络修复工具 - 修复Winsock/LSP、TCP/IP协议栈等网络问题

⚠️ 安全提示：
• 关闭防火墙会降低系统安全性
• 修改远程桌面端口需要管理员权限
• 修改端口后需要重启计算机才能生效""")
        result_layout.addWidget(self.result_text)

        layout.addWidget(result_frame, 1)

    def append_result(self, text):
        """追加操作结果"""
        current = self.result_text.toPlainText()
        self.result_text.setPlainText(current + "\n\n" + text)

    def _safe_popen(self, command, use_shell=False, new_console=False):
        """安全地启动外部程序，避免 WinError 193 错误

        Windows 下 Popen 传入字符串时会被当作单个可执行文件路径，
        对于 .msc/.cpl 等文件或带参数的命令需要加 shell=True，
        普通可执行文件应使用列表参数传递。
        当程序需要管理员权限时，自动尝试使用 UAC 提升。

        new_console=True 时强制打开新的控制台窗口（仅 Windows）。
        """
        try:
            popen_kwargs = {"shell": use_shell}
            if new_console and platform.system() == "Windows":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(command, **popen_kwargs)
        except OSError as e:
            # WinError 740 表示请求的操作需要提升，尝试以管理员身份运行
            if getattr(e, 'winerror', None) == 740:
                self.append_result("⚠️ 当前操作需要管理员权限，正在请求提升...")
                self._run_as_admin(command, use_shell=use_shell)
            else:
                self.append_result(f"❌ 启动失败: {str(e)}")
                QMessageBox.warning(self, "提示", f"启动失败: {str(e)}")
        except Exception as e:
            self.append_result(f"❌ 启动失败: {str(e)}")
            QMessageBox.warning(self, "提示", f"启动失败: {str(e)}")

    def _run_as_admin(self, command, use_shell=False):
        """尝试以管理员身份运行程序

        通过 PowerShell 的 Start-Process -Verb RunAs 触发 UAC 提权。
        """
        try:
            if isinstance(command, list):
                program = command[0]
                args = " ".join(f'"{arg}"' for arg in command[1:])
                ps_cmd = f'Start-Process "{program}"'
                if args:
                    ps_cmd += f" -ArgumentList {args}"
                ps_cmd += " -Verb RunAs"
                subprocess.Popen(["powershell", "-Command", ps_cmd])
            else:
                # 字符串命令（通常配合 shell=True 使用）
                subprocess.Popen([
                    "powershell", "-Command",
                    f'Start-Process "{command}" -Verb RunAs'
                ])
        except Exception as e:
            self.append_result(f"❌ 管理员启动失败: {str(e)}")
            QMessageBox.warning(
                self, "提示",
                "需要以管理员身份运行本程序才能执行此操作。\n"
                "请右键点击程序图标选择\"以管理员身份运行\"。"
            )

    def open_cmd(self):
        """打开CMD控制台（新窗口）"""
        self._safe_popen(["cmd.exe"], new_console=True)
        self.append_result("✅ 已启动CMD控制台（新窗口）")

    def open_powershell(self):
        """打开PowerShell（新窗口）"""
        self._safe_popen(["powershell.exe"], new_console=True)
        self.append_result("✅ 已启动PowerShell控制台（新窗口）")

    def open_admin_cmd(self):
        """以管理员身份打开CMD（新窗口）"""
        self._run_as_admin(["cmd.exe"])
        self.append_result("✅ 已请求以管理员身份启动CMD控制台（新窗口）")

    def open_ip_settings(self):
        """打开IP地址设置"""
        # ncpa.cpl 是控制面板小程序，需通过 control.exe 启动
        self._safe_popen(["control.exe", "ncpa.cpl"])
        self.append_result("✅ 已打开网络连接设置")

    def disable_firewall(self):
        """关闭防火墙"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.append_result("✅ Windows防火墙已关闭")
                QMessageBox.information(self, "提示", "防火墙已关闭，系统安全性会降低")
            else:
                self.append_result(f"❌ 关闭失败: {result.stderr}")
                QMessageBox.warning(
                    self, "提示",
                    "需要以管理员身份运行本程序才能修改防火墙设置。\n"
                    "请右键点击程序图标选择\"以管理员身份运行\"。"
                )
        except Exception as e:
            self.append_result(f"❌ 操作失败: {str(e)}")

    def enable_firewall(self):
        """开启防火墙"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.append_result("✅ Windows防火墙已开启")
                QMessageBox.information(self, "提示", "防火墙已开启")
            else:
                self.append_result(f"❌ 开启失败: {result.stderr}")
                QMessageBox.warning(
                    self, "提示",
                    "需要以管理员身份运行本程序才能修改防火墙设置。\n"
                    "请右键点击程序图标选择\"以管理员身份运行\"。"
                )
        except Exception as e:
            self.append_result(f"❌ 操作失败: {str(e)}")

    def check_firewall_status(self):
        """检查防火墙状态"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-NetFirewallProfile | Select-Object Name, Enabled"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.append_result(f"📊 防火墙状态:\n{result.stdout}")
            else:
                self.append_result(f"❌ 查询失败: {result.stderr}")
        except Exception as e:
            self.append_result(f"❌ 操作失败: {str(e)}")

    def open_device_manager(self):
        """打开设备管理器"""
        # .msc 文件需要 shell=True 才能正确打开
        self._run_as_admin("devmgmt.msc", use_shell=True)
        self.append_result("✅ 已请求以管理员身份打开设备管理器")

    def open_task_manager(self):
        """打开任务管理器"""
        self._safe_popen(["taskmgr.exe"])
        self.append_result("✅ 已打开任务管理器")

    def show_system_info(self):
        """显示系统信息"""
        try:
            result = subprocess.run(
                ["systeminfo"], capture_output=True, text=True, errors='ignore'
            )
            info = result.stdout[:2000]
            self.append_result(f"📊 系统信息:\n{info}")
        except OSError as e:
            if getattr(e, 'winerror', None) == 740:
                self.append_result("⚠️ 获取系统信息需要管理员权限")
                QMessageBox.warning(
                    self, "提示",
                    "需要以管理员身份运行本程序才能获取系统信息。\n"
                    "请右键点击程序图标选择\"以管理员身份运行\"。"
                )
            else:
                self.append_result(f"❌ 获取失败: {str(e)}")
        except Exception as e:
            self.append_result(f"❌ 获取失败: {str(e)}")

    def open_regedit(self):
        """打开注册表编辑器（需要管理员权限）"""
        self._run_as_admin(["regedit.exe"])
        self.append_result("✅ 已请求以管理员身份打开注册表编辑器")

    def open_event_viewer(self):
        """打开事件查看器"""
        self._safe_popen("eventvwr.msc", use_shell=True)
        self.append_result("✅ 已打开事件查看器")

    def open_disk_management(self):
        """打开磁盘管理"""
        self._safe_popen("diskmgmt.msc", use_shell=True)
        self.append_result("✅ 已打开磁盘管理")

    def open_service_manager(self):
        """打开服务管理"""
        self._safe_popen("services.msc", use_shell=True)
        self.append_result("✅ 已打开服务管理器")

    def open_resource_monitor(self):
        """打开资源监视器"""
        self._safe_popen(["resmon.exe"])
        self.append_result("✅ 已打开资源监视器")

    def open_computer_management(self):
        """打开计算机管理"""
        self._safe_popen("compmgmt.msc", use_shell=True)
        self.append_result("✅ 已打开计算机管理")

    def open_control_panel(self):
        """打开控制面板"""
        self._safe_popen(["control.exe"])
        self.append_result("✅ 已打开控制面板")

    def open_remote_desktop(self):
        """打开远程桌面连接"""
        self._safe_popen(["mstsc.exe"])
        self.append_result("✅ 已打开远程桌面连接")

    def change_rdp_port(self):
        """修改远程桌面端口"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", """
                    Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name PortNumber -Value 3390
                    netsh advfirewall firewall add rule name="RemoteDesktop3390" dir=in action=allow protocol=TCP localport=3390
                """],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.append_result("✅ 远程桌面端口已修改为3390")
                QMessageBox.information(self, "提示", "端口已修改，需要重启计算机才能生效")
            else:
                self.append_result(f"❌ 修改失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "需要管理员权限")
        except Exception as e:
            self.append_result(f"❌ 操作失败: {str(e)}")

    def restore_rdp_port(self):
        """恢复远程桌面默认端口"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", """
                    Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name PortNumber -Value 3389
                    netsh advfirewall firewall add rule name="RemoteDesktop3389" dir=in action=allow protocol=TCP localport=3389
                """],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.append_result("✅ 远程桌面端口已恢复为3389")
                QMessageBox.information(self, "提示", "端口已恢复，需要重启计算机才能生效")
            else:
                self.append_result(f"❌ 恢复失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "需要管理员权限")
        except Exception as e:
            self.append_result(f"❌ 操作失败: {str(e)}")

    def run_network_repair(self):
        """运行网络修复工具"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", """
                    netsh winsock reset
                    netsh int ip reset
                    ipconfig /release
                    ipconfig /renew
                    ipconfig /flushdns
                """],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.append_result("✅ 网络修复工具已执行")
                QMessageBox.information(self, "提示", "网络修复完成，建议重启计算机")
            else:
                self.append_result(f"❌ 修复失败: {result.stderr}")
                QMessageBox.warning(self, "提示", "需要管理员权限")
        except Exception as e:
            self.append_result(f"❌ 操作失败: {str(e)}")

    def run_network_diagnostic(self):
        """运行网络诊断"""
        self._safe_popen(["msdt.exe", "/id", "NetworkDiagnosticsNetworkAdapter"])
        self.append_result("✅ 已启动网络诊断工具")

    def open_performance_monitor(self):
        """打开性能监视器（建议管理员权限以获取完整数据）"""
        self._run_as_admin(["perfmon.exe"])
        self.append_result("✅ 已请求以管理员身份打开性能监视器")

    def open_network_settings(self):
        """打开网络设置"""
        # ms-settings: 协议需要 start 命令配合 shell=True
        self._safe_popen(["start", "ms-settings:network"], use_shell=True)
        self.append_result("✅ 已打开网络设置")