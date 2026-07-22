import threading
import time
import socket
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QComboBox,
    QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QObject, Signal

from app.core.logger import Logger

try:
    from scapy.all import (
        sniff, get_if_list, get_if_addr, get_if_hwaddr,
        Ether, IP, UDP, BOOTP, DHCP, sendp
    )
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


class DHCPCheckerWorker(QObject):
    log_signal = Signal(str)
    result_signal = Signal(list)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False
        self.interface = None
        self.dhcp_servers = []
        self.logger = Logger("DHCPChecker")

    def start_check(self, interface):
        self.interface = interface
        self.is_running = True
        self.dhcp_servers = []
        self.thread = threading.Thread(target=self._run_check)
        self.thread.start()

    def _run_check(self):
        self.log_signal.emit(f"[{datetime.now().strftime('%H:%M:%S')}] 开始DHCP服务器检测...")

        try:
            interfaces = get_if_list()
        except Exception as e:
            self.log_signal.emit(f"❌ 获取网卡失败: {str(e)}")
            self.logger.error(f"获取网卡失败: {e}")
            self.is_running = False
            self.finished_signal.emit()
            return

        if self.interface not in interfaces:
            self.log_signal.emit(f"❌ 指定的网卡 '{self.interface}' 不存在")
            self.logger.error(f"指定的网卡不存在: {self.interface}")
            self.is_running = False
            self.finished_signal.emit()
            return

        self.log_signal.emit(f"[{datetime.now().strftime('%H:%M:%S')}] 选择网卡: {self.interface}")

        self.log_signal.emit("\n📡 开始发送DHCP DISCOVER请求...")
        self._send_dhcp_discover()

        if self.is_running:
            self._listen_dhcp_response()

        self.log_signal.emit("\n📊 检测完成")

        if self.dhcp_servers:
            self.log_signal.emit(f"✅ 检测到 {len(self.dhcp_servers)} 个DHCP服务器:")
            for i, server in enumerate(self.dhcp_servers, 1):
                self.log_signal.emit(f"  [{i}] {server}")

            if len(self.dhcp_servers) > 1:
                self.log_signal.emit("\n⚠️ 警告: 检测到多个DHCP服务器，可能存在私接路由器！")
        else:
            self.log_signal.emit("\n⚠️ 未检测到DHCP服务器")
            self.log_signal.emit("\n可能原因:")
            self.log_signal.emit("  • 网段内确实没有DHCP服务器")
            self.log_signal.emit("  • DHCP服务器配置了响应过滤")
            self.log_signal.emit("  • 网络防火墙阻止了DHCP报文")
            self.log_signal.emit("  • 扫描超时时间过短")

        self.log_signal.emit("-" * 60)
        self.result_signal.emit(self.dhcp_servers)
        self.is_running = False
        self.finished_signal.emit()

    def _send_dhcp_discover(self):
        try:
            mac = self._get_mac_address()
            if not mac or mac == b'\x00' * 6:
                self.log_signal.emit("❌ 无法获取网卡MAC地址")
                self.logger.error("无法获取网卡MAC地址")
                return

            discover = Ether(dst="ff:ff:ff:ff:ff:ff", src=mac) / \
                       IP(src="0.0.0.0", dst="255.255.255.255") / \
                       UDP(sport=68, dport=67) / \
                       BOOTP(chaddr=mac, xid=0x12345678) / \
                       DHCP(options=[("message-type", "discover"), "end"])

            sendp(discover, iface=self.interface, verbose=0)
            self.log_signal.emit(f"DHCP DISCOVER已发送 (MAC: {mac.hex()})")
        except Exception as e:
            self.log_signal.emit(f"❌ 发送DHCP请求失败: {str(e)}")
            self.logger.error(f"发送DHCP请求失败: {e}")

    def _listen_dhcp_response(self):
        self.log_signal.emit("⏳ 等待DHCP响应 (最多10秒)...")
        timeout = time.time() + 10
        while self.is_running and time.time() < timeout:
            try:
                packets = sniff(
                    iface=self.interface,
                    filter="udp and port 68",
                    count=1,
                    timeout=1,
                    store=False
                )
                for pkt in packets:
                    self._process_dhcp_response(pkt)
            except Exception:
                break

    def _process_dhcp_response(self, packet):
        if not self.is_running:
            return

        if packet.haslayer(DHCP) and packet.haslayer(BOOTP):
            dhcp_options = packet[DHCP].options
            msg_type = None
            server_id = None
            subnet_mask = None
            gateway = None
            dns_servers = []
            lease_time = None

            for opt in dhcp_options:
                if isinstance(opt, tuple):
                    if opt[0] == "message-type":
                        msg_type = opt[1]
                    elif opt[0] == "server_id":
                        server_id = opt[1]
                    elif opt[0] == "subnet_mask":
                        subnet_mask = opt[1]
                    elif opt[0] == "router":
                        gateway = opt[1]
                    elif opt[0] == "name_server":
                        dns_servers.append(opt[1])
                    elif opt[0] == "lease_time":
                        lease_time = opt[1]

            if msg_type == 2 and server_id:
                if server_id not in [s['server_id'] for s in self.dhcp_servers]:
                    self.dhcp_servers.append({
                        'server_id': server_id,
                        'subnet_mask': subnet_mask,
                        'gateway': gateway,
                        'dns_servers': dns_servers,
                        'lease_time': lease_time
                    })

                    self.log_signal.emit(f"\n📨 收到DHCP OFFER:")
                    self.log_signal.emit(f"   服务器IP: {server_id}")
                    if subnet_mask:
                        self.log_signal.emit(f"   子网掩码: {subnet_mask}")
                    if gateway:
                        self.log_signal.emit(f"   默认网关: {gateway}")
                    if dns_servers:
                        self.log_signal.emit(f"   DNS服务器: {', '.join(dns_servers)}")
                    if lease_time:
                        self.log_signal.emit(f"   租约时间: {lease_time}秒")

    def _get_mac_address(self):
        try:
            mac_str = get_if_hwaddr(self.interface)
            return bytes.fromhex(mac_str.replace(':', ''))
        except Exception:
            try:
                import psutil
                addrs = psutil.net_if_addrs()
                sip = get_if_addr(self.interface)
                for pname, paddrs in addrs.items():
                    found_mac = None
                    has_ip = False
                    for addr in paddrs:
                        if addr.family == psutil.AF_LINK:
                            found_mac = addr.address
                        if addr.family == socket.AF_INET and addr.address == sip:
                            has_ip = True
                    if has_ip and found_mac:
                        return bytes.fromhex(found_mac.replace('-', '').replace(':', ''))
                    if pname == self.interface:
                        for addr in paddrs:
                            if addr.family == psutil.AF_LINK:
                                return bytes.fromhex(addr.address.replace('-', '').replace(':', ''))
            except Exception as e:
                self.logger.error(f"获取MAC地址失败: {e}")
        return b'\x00' * 6

    def stop_check(self):
        self.is_running = False
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=2)


class DHCPCheckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = Logger("DHCPCheckPage")
        self.worker = DHCPCheckerWorker()
        self.worker.log_signal.connect(self.on_log)
        self.worker.result_signal.connect(self.on_result)
        self.worker.finished_signal.connect(self.on_finished)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        self._build_warning_area(main_layout)
        self._build_interface_area(main_layout)
        self._build_control_area(main_layout)
        self._build_result_area(main_layout)

    def _build_warning_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #fff3cd;
                border: 1px solid #ffeeba;
                border-radius: 5px;
            }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)

        warning_icon = QLabel("⚠")
        warning_icon.setStyleSheet("font-size: 18px;")
        layout.addWidget(warning_icon)

        warning_text = QLabel("重要提示：DHCP检测功能需要管理员权限运行，请右键选择\"以管理员身份运行\"")
        warning_text.setStyleSheet("font-size: 12px; color: #856404;")
        layout.addWidget(warning_text)

        parent_layout.addWidget(frame)

    def _build_interface_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; background: #fafafa; }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("🔌 选择网卡:"))
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(400)
        self._refresh_interfaces()
        layout.addWidget(self.iface_combo)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_interfaces)
        layout.addWidget(refresh_btn)

        parent_layout.addWidget(frame)

    def _build_control_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; background: #fafafa; }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        title = QLabel("🔍 DHCP服务器检测")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        layout.addWidget(title)

        self.start_btn = QPushButton("🚀 开始检测")
        self.start_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.start_btn.clicked.connect(self.start_check)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止检测")
        self.stop_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_check)
        layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🗑 清空结果")
        self.clear_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.clear_btn.clicked.connect(self.clear_results)
        layout.addWidget(self.clear_btn)

        self.help_btn = QPushButton("❓ 使用说明")
        self.help_btn.setStyleSheet("background-color: #3498db; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        self.help_btn.clicked.connect(self.show_help)
        layout.addWidget(self.help_btn)

        layout.addStretch()
        parent_layout.addWidget(frame)

    def _build_result_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title_bar = QHBoxLayout()
        title = QLabel("📊 DHCP服务器检测结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        title_bar.addWidget(title)

        self.result_count = QLabel("检测到的DHCP服务器数量: 0")
        self.result_count.setStyleSheet("font-size: 12px; color: #e74c3c;")
        title_bar.addStretch()
        title_bar.addWidget(self.result_count)

        layout.addLayout(title_bar)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #00ff41;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                border: none;
            }
        """)
        self.result_text.append("等待检测开始...")
        layout.addWidget(self.result_text)

        parent_layout.addWidget(frame)

    def _get_interface_mapping(self):
        mapping = {}
        if not SCAPY_AVAILABLE:
            return mapping
        try:
            import psutil
            psutil_addrs = psutil.net_if_addrs()
            scapy_ifaces = get_if_list()
            for siface in scapy_ifaces:
                sip = ""
                try:
                    sip = get_if_addr(siface)
                except Exception:
                    pass

                friendly_name = siface
                mac = ""
                for pname, paddrs in psutil_addrs.items():
                    for addr in paddrs:
                        if addr.family == socket.AF_INET and addr.address == sip:
                            friendly_name = pname
                            for a in paddrs:
                                if a.family == psutil.AF_LINK:
                                    mac = a.address
                                    break
                            break
                    if friendly_name != siface:
                        break

                if mac and sip:
                    display = f"{friendly_name} (MAC: {mac}, IP: {sip})"
                elif mac:
                    display = f"{friendly_name} (MAC: {mac})"
                elif sip:
                    display = f"{friendly_name} (IP: {sip})"
                else:
                    display = friendly_name

                mapping[siface] = display
        except Exception as e:
            self.logger.error(f"构建网卡映射失败: {e}")
            for siface in get_if_list():
                mapping[siface] = siface
        return mapping

    def _refresh_interfaces(self):
        self.iface_combo.clear()
        if not SCAPY_AVAILABLE:
            QMessageBox.warning(self, "警告", "scapy 模块未安装，请先安装 scapy")
            return

        mapping = self._get_interface_mapping()
        for siface, display in mapping.items():
            self.iface_combo.addItem(display, siface)

    def start_check(self):
        if not SCAPY_AVAILABLE:
            QMessageBox.warning(self, "警告", "scapy 模块未安装，请先安装 scapy")
            return

        interface = self.iface_combo.currentData()
        if not interface:
            QMessageBox.warning(self, "提示", "请选择网卡")
            return

        self.worker.start_check(interface)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.result_text.clear()
        self.result_count.setText("检测到的DHCP服务器数量: 0")

    def stop_check(self):
        self.worker.stop_check()
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(True)

    def on_log(self, log):
        self.result_text.append(log)
        scroll_bar = self.result_text.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def on_result(self, servers):
        self.result_count.setText(f"检测到的DHCP服务器数量: {len(servers)}")

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def clear_results(self):
        self.result_text.clear()
        self.result_text.append("等待检测开始...")
        self.result_count.setText("检测到的DHCP服务器数量: 0")
        self.worker.dhcp_servers = []

    def show_help(self):
        help_text = """
DHCP检测功能说明:

1. 功能介绍:
   - 检测网络中所有响应DHCP请求的服务器
   - 识别是否存在私接路由器（多个DHCP服务器）
   - 显示DHCP服务器提供的网络配置信息

2. 使用方法:
   - 选择要检测的网络适配器
   - 点击"开始检测"按钮
   - 等待10秒左右，查看检测结果

3. 需要管理员权限:
   - 发送和接收DHCP广播包需要管理员权限
   - 如果没有权限，可能无法正常检测

4. 结果解读:
   - 检测到1个DHCP服务器: 正常网络环境
   - 检测到多个DHCP服务器: 可能存在私接路由器，需要排查
   - 未检测到DHCP服务器: 检查网络连接或防火墙设置

5. 常见问题:
   - 无法检测到服务器: 检查防火墙设置、网卡选择是否正确
   - 检测到多个服务器: 可能有人私接了路由器，请联系网络管理员
        """
        QMessageBox.information(self, "使用说明", help_text)

    def cleanup(self):
        """页面关闭时清理资源，防止C++对象已删除崩溃"""
        try:
            self.worker.stop_check()
            self.worker.log_signal.disconnect(self.on_log)
            self.worker.result_signal.disconnect(self.on_result)
            self.worker.finished_signal.disconnect(self.on_finished)
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
