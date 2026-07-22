"""子网计算页面 - 提供IPv4/IPv6子网计算、VLSM、子网划分、路由汇总、反掩码计算功能"""
import ipaddress
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget, QMessageBox, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from app.core.logger import Logger

logger = Logger("SubnetCalc")


def ip_to_int(ip):
    return int(ipaddress.IPv4Address(ip))


def int_to_ip(n):
    return str(ipaddress.IPv4Address(n))


def get_class(first_octet):
    """根据IP地址第一段判断网络类别"""
    if 1 <= first_octet <= 126:
        return "A类"
    elif 128 <= first_octet <= 191:
        return "B类"
    elif 192 <= first_octet <= 223:
        return "C类"
    elif 224 <= first_octet <= 239:
        return "D类(组播)"
    elif 240 <= first_octet <= 255:
        return "E类(保留)"
    return "未知"


def get_ipv6_type(addr):
    """判断IPv6地址类型"""
    ip = ipaddress.IPv6Address(addr)
    if ip.is_loopback:
        return "回环地址 (::1)"
    if ip.is_link_local:
        return "链路本地地址 (FE80::/10)"
    if ip.is_site_local:
        return "站点本地地址 (FEC0::/10)"
    if ip.is_multicast:
        return "组播地址"
    if ip.is_unspecified:
        return "未指定地址 (::)"
    if ip.is_private:
        return "私有地址 (Private/ULA)"
    if ip.is_reserved:
        return "保留地址"
    # 2001:db8::/32 文档示例
    if ip in ipaddress.IPv6Network("2001:db8::/32"):
        return "文档示例地址 (2001:db8::/32)"
    if int(ip) >> 32 == 0x20010000:
        return "全球单播地址 (2000::/3)"
    return "全球单播地址"


def calculate_ipv4(network_str):
    """计算IPv4子网信息"""
    try:
        network = ipaddress.IPv4Network(network_str, strict=False)
        net_int = int(network.network_address)
        prefix = network.prefixlen
        total = 2 ** (32 - prefix)
        broadcast_int = net_int + total - 1

        first_usable_int = net_int + 1
        last_usable_int = broadcast_int - 1

        return {
            'network': str(network.network_address),
            'broadcast': str(network.broadcast_address),
            'mask': str(network.netmask),
            'prefix': f"/{prefix}",
            'total': total,
            'usable': max(0, total - 2),
            'first_usable': int_to_ip(first_usable_int) if total > 2 else "-",
            'last_usable': int_to_ip(last_usable_int) if total > 2 else "-",
            'class': get_class(int(str(network.network_address).split('.')[0])),
            'wildcard': str(network.hostmask),
            'is_private': network.is_private,
            'is_multicast': network.is_multicast,
            'is_loopback': network.is_loopback,
        }
    except Exception as e:
        raise ValueError(f"无效的IPv4地址: {e}")


def calculate_ipv6(network_str):
    """计算IPv6子网信息"""
    try:
        network = ipaddress.IPv6Network(network_str, strict=False)
        prefix = network.prefixlen
        total = 2 ** (128 - prefix)

        first_int = int(network.network_address)
        last_int = first_int + total - 1
        first_usable = ipaddress.IPv6Address(first_int + 1) if total > 2 else network.network_address
        last_usable = ipaddress.IPv6Address(last_int - 1) if total > 2 else network.network_address

        return {
            'network': str(network.network_address) + "::" if not str(network.network_address).endswith("::") else str(network.network_address),
            'prefix': f"/{prefix}",
            'total': total,
            'first_usable': str(first_usable),
            'last_usable': str(last_usable),
            'type': get_ipv6_type(str(network.network_address)),
        }
    except Exception as e:
        raise ValueError(f"无效的IPv6地址: {e}")


def vlsm_calculate(base_network, requirements):
    """VLSM变长子网划分算法
    requirements: [(name, host_count), ...]
    """
    base_net = ipaddress.IPv4Network(base_network, strict=False)
    base_int = int(base_net.network_address)
    base_prefix = base_net.prefixlen

    # 按主机数从大到小排序（VLSM标准做法）
    sorted_reqs = sorted(enumerate(requirements), key=lambda x: -x[1][1])

    allocations = [None] * len(requirements)
    current_int = base_int

    for orig_idx, (name, host_count) in sorted_reqs:
        if host_count < 1:
            raise ValueError(f"主机数必须大于0: {name}")
        # 计算满足主机数所需的主机位数
        needed_bits = 0
        while (2 ** needed_bits) - 2 < host_count:
            needed_bits += 1
        new_prefix = 32 - needed_bits

        # 网络大小
        net_size = 2 ** needed_bits
        # 找到当前指针所在网络的开始位置（对齐到net_size）
        # 如果当前指针不在边界上，向后对齐
        if current_int % net_size != 0:
            current_int = ((current_int // net_size) + 1) * net_size

        if current_int + net_size > base_int + (2 ** (32 - base_prefix)):
            raise ValueError(f"地址空间不足，无法为 '{name}' 分配 {host_count} 个主机")

        new_net = ipaddress.IPv4Network(f"{int_to_ip(current_int)}/{new_prefix}", strict=False)
        allocations[orig_idx] = {
            'name': name,
            'hosts': host_count,
            'network': str(new_net.network_address),
            'prefix': f"/{new_prefix}",
            'mask': str(new_net.netmask),
            'first_usable': str(int_to_ip(current_int + 1)),
            'last_usable': str(int_to_ip(current_int + net_size - 2)),
            'broadcast': str(int_to_ip(current_int + net_size - 1)),
            'total': net_size - 2,
        }
        current_int += net_size

    return allocations


def equal_subnet_calculate(base_network, new_prefix):
    """等长子网划分"""
    base_net = ipaddress.IPv4Network(base_network, strict=False)
    if new_prefix <= base_net.prefixlen:
        raise ValueError(f"新前缀必须大于原前缀 /{base_net.prefixlen}")

    subnets = list(base_net.subnets(new_prefix=new_prefix))
    results = []
    for i, subnet in enumerate(subnets, 1):
        net_int = int(subnet.network_address)
        size = 2 ** (32 - new_prefix)
        results.append({
            'index': i,
            'network': str(subnet.network_address),
            'prefix': f"/{new_prefix}",
            'mask': str(subnet.netmask),
            'first_usable': str(int_to_ip(net_int + 1)),
            'last_usable': str(int_to_ip(net_int + size - 2)),
            'broadcast': str(int_to_ip(net_int + size - 1)),
            'usable': size - 2,
        })
    return results


def route_summarize(networks_str):
    """路由汇总 - 找最优汇总路由"""
    networks = []
    for line in networks_str.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            networks.append(ipaddress.IPv4Network(line, strict=False))
        except Exception as e:
            raise ValueError(f"无效的子网 '{line}': {e}")

    if not networks:
        raise ValueError("请输入至少一个子网")

    # 计算所有地址范围的最大公共前缀
    # 需要考虑每个子网覆盖的所有地址（从网络地址到广播地址）
    min_addr = min(int(n.network_address) for n in networks)
    max_addr = max(int(n.broadcast_address) for n in networks)

    # 找到 min_addr 和 max_addr 的共同前缀
    xor = min_addr ^ max_addr
    if xor == 0:
        common_bits = 32
    else:
        # bit_length()返回最高位1的位置（从1开始），所以共同前缀 = 32 - bit_length
        common_bits = 32 - xor.bit_length()

    summary_int = min_addr & (((1 << 32) - 1) ^ ((1 << (32 - common_bits)) - 1))
    summary = ipaddress.IPv4Network(f"{int_to_ip(summary_int)}/{common_bits}", strict=False)

    return {
        'summary_network': str(summary.network_address),
        'summary_prefix': f"/{common_bits}",
        'summary_mask': str(summary.netmask),
        'prefix_len': common_bits,
        'address_range': f"{int_to_ip(summary_int)} - {int_to_ip(summary_int + (1 << (32 - common_bits)) - 1)}",
        'total_addresses': 1 << (32 - common_bits),
        'input_count': len(networks),
        'used_addresses': sum(2 ** (32 - n.prefixlen) for n in networks),
        'coverage': 100.0 if common_bits == 22 else None,
    }


def calculate_wildcard(mask_str):
    """计算反掩码"""
    try:
        if mask_str.startswith('/'):
            prefix = int(mask_str[1:])
        elif '/' in mask_str:
            prefix = int(mask_str.split('/')[1])
        else:
            try:
                prefix = int(mask_str)
                if 0 <= prefix <= 32:
                    pass
                else:
                    prefix = None
            except ValueError:
                prefix = None

        if prefix is not None and 0 <= prefix <= 32:
            mask_int = ((1 << 32) - 1) ^ ((1 << (32 - prefix)) - 1) if prefix > 0 else 0
        else:
            mask_int = ip_to_int(mask_str)
            prefix = bin(mask_int).count('1')
        wildcard_int = mask_int ^ ((1 << 32) - 1)
        return {
            'mask': int_to_ip(mask_int),
            'wildcard': int_to_ip(wildcard_int),
            'prefix': f"/{prefix}",
            'binary_mask': '.'.join([bin((mask_int >> (8 * i)) & 0xff)[2:].zfill(8) for i in range(3, -1, -1)]),
            'binary_wildcard': '.'.join([bin((wildcard_int >> (8 * i)) & 0xff)[2:].zfill(8) for i in range(3, -1, -1)]),
        }
    except Exception as e:
        raise ValueError(f"无效的子网掩码: {e}")


def calculate_wildcard_full(network_str):
    """计算网络/掩码的完整信息（含ACL参考）"""
    try:
        if '/' in network_str:
            network = ipaddress.IPv4Network(network_str, strict=False)
            network_addr = str(network.network_address)
            mask = str(network.netmask)
            prefix = network.prefixlen
        else:
            network_addr = network_str.strip()
            mask = "255.255.255.0"
            prefix = 24

        mask_int = ip_to_int(mask)
        wildcard_int = mask_int ^ ((1 << 32) - 1)
        total = 2 ** (32 - prefix)
        net_int = ip_to_int(network_addr)

        # 对齐到子网边界
        aligned_net = net_int & mask_int
        broadcast_int = aligned_net | wildcard_int
        first_usable = int_to_ip(aligned_net + 1) if total > 2 else int_to_ip(aligned_net)
        last_usable = int_to_ip(broadcast_int - 1) if total > 2 else int_to_ip(broadcast_int)
        usable_count = max(0, total - 2)

        return {
            'network': int_to_ip(aligned_net),
            'prefix': f"/{prefix}",
            'mask': mask,
            'wildcard': int_to_ip(wildcard_int),
            'total': total,
            'usable': usable_count,
            'first_usable': first_usable,
            'last_usable': last_usable,
            'cisco_acl': f"permit ip any {int_to_ip(aligned_net)} {int_to_ip(wildcard_int)}",
            'huawei_acl': f"rule permit source {int_to_ip(aligned_net)} {int_to_ip(wildcard_int)}",
            'binary_mask': '.'.join([bin((mask_int >> (8 * i)) & 0xff)[2:].zfill(8) for i in range(3, -1, -1)]),
            'binary_wildcard': '.'.join([bin((wildcard_int >> (8 * i)) & 0xff)[2:].zfill(8) for i in range(3, -1, -1)]),
        }
    except Exception as e:
        raise ValueError(f"无效的网络地址: {e}")


def calculate_wildcard_batch(text):
    """批量计算反掩码"""
    results = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            if '/' in line:
                # 网络/掩码格式
                info = calculate_wildcard_full(line)
            else:
                # 纯掩码格式
                info = calculate_wildcard(line)
                info['network'] = '-'
            results.append({'input': line, **info, 'success': True})
        except Exception as e:
            results.append({'input': line, 'error': str(e), 'success': False})
    return results


class SubnetCalcPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 顶部Tab导航
        self.tab_frame = QFrame()
        self.tab_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        tab_layout = QHBoxLayout(self.tab_frame)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        self.tab_buttons = {}
        tabs = [
            ("IPv4", "ipv4"),
            ("IPv6", "ipv6"),
            ("VLSM", "vlsm"),
            ("子网划分", "subnet"),
            ("路由汇总", "summary"),
            ("反掩码", "wildcard"),
        ]
        for name, key in tabs:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #555;
                    border: none;
                    padding: 12px 20px;
                    font-size: 13px;
                    border-bottom: 2px solid transparent;
                }
                QPushButton:checked {
                    background-color: #e3f2fd;
                    color: #00bcd4;
                    border-bottom: 2px solid #00bcd4;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #f5f5f5; }
            """)
            btn.clicked.connect(lambda checked, k=key: self.switch_tab(k))
            tab_layout.addWidget(btn)
            self.tab_buttons[key] = btn
        tab_layout.addStretch()

        main_layout.addWidget(self.tab_frame)

        # 内容区域
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        self.page_ipv4 = self._build_ipv4_page()
        self.page_ipv6 = self._build_ipv6_page()
        self.page_vlsm = self._build_vlsm_page()
        self.page_subnet = self._build_subnet_page()
        self.page_summary = self._build_summary_page()
        self.page_wildcard = self._build_wildcard_page()

        self.stack.addWidget(self.page_ipv4)
        self.stack.addWidget(self.page_ipv6)
        self.stack.addWidget(self.page_vlsm)
        self.stack.addWidget(self.page_subnet)
        self.stack.addWidget(self.page_summary)
        self.stack.addWidget(self.page_wildcard)

        self.switch_tab("ipv4")

    def switch_tab(self, key):
        for k, btn in self.tab_buttons.items():
            btn.setChecked(k == key)
        index_map = {
            "ipv4": 0, "ipv6": 1, "vlsm": 2,
            "subnet": 3, "summary": 4, "wildcard": 5
        }
        self.stack.setCurrentIndex(index_map[key])

    def _build_section_frame(self, title_text):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)
        title = QLabel(title_text)
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        layout.addWidget(title)
        return frame, layout

    def _build_result_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)
        return frame, layout

    def _build_ipv4_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # 输入区
        input_frame, input_layout = self._build_section_frame("🌐 IPv4网络参数输入")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("网络地址:"))
        self.ipv4_input = QLineEdit("192.168.1.0/24")
        self.ipv4_input.setMinimumWidth(300)
        row.addWidget(self.ipv4_input)
        row.addStretch()
        calc_btn = QPushButton("🔢 开始计算")
        calc_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        calc_btn.clicked.connect(self.calculate_ipv4)
        row.addWidget(calc_btn)
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        # 结果区
        result_frame, result_layout = self._build_result_frame()
        title = QLabel("📊 IPv4计算结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(title)

        self.ipv4_result = QTextEdit()
        self.ipv4_result.setReadOnly(True)
        self.ipv4_result.setMinimumHeight(350)
        self.ipv4_result.setStyleSheet("""
            QTextEdit {
                background-color: white;
                color: #333;
                font-size: 13px;
                line-height: 1.8;
                border: 1px solid #f0f0f0;
                border-radius: 3px;
                padding: 10px;
            }
        """)
        result_layout.addWidget(self.ipv4_result)

        layout.addWidget(result_frame, 1)
        return page

    def calculate_ipv4(self):
        try:
            text = self.ipv4_input.text().strip()
            info = calculate_ipv4(text)
            output = (
                f"<b>网络地址:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['network']}</span><br><br>"
                f"<b>广播地址:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['broadcast']}</span><br><br>"
                f"<b>子网掩码:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['mask']}</span><br><br>"
                f"<b>主机数量:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['total']}</span><br><br>"
                f"<b>可用主机:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['usable']} ({info['first_usable']} ~ {info['last_usable']})</span><br><br>"
                f"<b>网络类别:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['class']}</span><br><br>"
                f"<b>反掩码:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['wildcard']}</span><br><br>"
                f"<b>前缀长度:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['prefix']}</span><br><br>"
            )
            if info.get('is_private'):
                output += "<b>地址类型:</b>  <span style='color:#e74c3c;'>私有地址</span><br>"
            elif info.get('is_multicast'):
                output += "<b>地址类型:</b>  <span style='color:#e74c3c;'>组播地址</span><br>"
            elif info.get('is_loopback'):
                output += "<b>地址类型:</b>  <span style='color:#e74c3c;'>回环地址</span><br>"
            else:
                output += "<b>地址类型:</b>  <span style='color:#27ae60;'>公有地址</span><br>"

            self.ipv4_result.setHtml(output)
        except Exception as e:
            self.ipv4_result.setHtml(f"<span style='color:#e74c3c;'>❌ {e}</span>")

    def _build_ipv6_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        input_frame, input_layout = self._build_section_frame("🌐 IPv6网络参数输入")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("网络地址:"))
        self.ipv6_input = QLineEdit("2001:db8::/64")
        self.ipv6_input.setMinimumWidth(300)
        row.addWidget(self.ipv6_input)
        row.addStretch()
        calc_btn = QPushButton("🔢 开始计算")
        calc_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        calc_btn.clicked.connect(self.calculate_ipv6)
        row.addWidget(calc_btn)
        input_layout.addLayout(row)
        layout.addWidget(input_frame)

        result_frame, result_layout = self._build_result_frame()
        title = QLabel("📊 IPv6计算结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(title)

        self.ipv6_result = QTextEdit()
        self.ipv6_result.setReadOnly(True)
        self.ipv6_result.setMinimumHeight(350)
        self.ipv6_result.setStyleSheet("""
            QTextEdit {
                background-color: white;
                color: #333;
                font-size: 13px;
                line-height: 1.8;
                border: 1px solid #f0f0f0;
                border-radius: 3px;
                padding: 10px;
            }
        """)
        result_layout.addWidget(self.ipv6_result)

        layout.addWidget(result_frame, 1)
        return page

    def calculate_ipv6(self):
        try:
            text = self.ipv6_input.text().strip()
            info = calculate_ipv6(text)
            output = (
                f"<b>网络地址:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['network']}</span><br><br>"
                f"<b>子网前缀:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['prefix']}</span><br><br>"
                f"<b>主机数量:</b>  <span style='color:#00bcd4; font-weight:bold;'>2<sup>{128 - int(info['prefix'].replace('/', ''))}</sup> ({info['total']:,})</span><br><br>"
                f"<b>可用主机:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['first_usable']} ... {info['last_usable']}</span><br><br>"
                f"<b>地址类型:</b>  <span style='color:#00bcd4; font-weight:bold;'>{info['type']}</span><br>"
            )
            self.ipv6_result.setHtml(output)
        except Exception as e:
            self.ipv6_result.setHtml(f"<span style='color:#e74c3c;'>❌ {e}</span>")

    def _build_vlsm_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # 参数区
        param_frame, param_layout = self._build_section_frame("⚙️ VLSM子网划分参数")
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel("主网络地址:"))
        self.vlsm_base = QLineEdit("192.168.1.0/24")
        self.vlsm_base.setMinimumWidth(300)
        row1.addWidget(self.vlsm_base)
        param_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel("子网需求:"))
        hint = QLabel("（每行一个，格式: 名称,主机数）")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        row2.addWidget(hint)
        row2.addStretch()
        param_layout.addLayout(row2)

        self.vlsm_input = QTextEdit()
        self.vlsm_input.setPlainText("部门A,50\n部门B,30\n部门C,20\n部门D,10")
        self.vlsm_input.setMaximumHeight(120)
        param_layout.addWidget(self.vlsm_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        calc_btn = QPushButton("🚀 开始划分")
        calc_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        calc_btn.clicked.connect(self.calculate_vlsm)
        clear_btn = QPushButton("🗑 清空")
        clear_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        clear_btn.clicked.connect(self.clear_vlsm)
        btn_row.addWidget(calc_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        param_layout.addLayout(btn_row)
        layout.addWidget(param_frame)

        # 结果区
        result_frame, result_layout = self._build_result_frame()
        title = QLabel("📊 VLSM划分结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(title)

        self.vlsm_table = QTableWidget()
        self.vlsm_table.setColumnCount(7)
        self.vlsm_table.setHorizontalHeaderLabels(["子网名称", "需求主机数", "网络地址", "子网掩码", "首个可用IP", "最后可用IP", "广播地址"])
        self.vlsm_table.setAlternatingRowColors(True)
        self.vlsm_table.setStyleSheet("""
            QTableWidget { font-size: 12px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 6px; font-weight: bold; }
        """)
        header = self.vlsm_table.horizontalHeader()
        for i in range(7):
            header.setSectionResizeMode(i, QHeaderView.Stretch if i in [3, 4, 5] else QHeaderView.ResizeToContents)
        result_layout.addWidget(self.vlsm_table)
        layout.addWidget(result_frame, 1)
        return page

    def calculate_vlsm(self):
        try:
            base = self.vlsm_base.text().strip()
            lines = self.vlsm_input.toPlainText().strip().split('\n')
            reqs = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) != 2:
                    raise ValueError(f"格式错误: '{line}' 应为 名称,主机数")
                name = parts[0].strip()
                count = int(parts[1].strip())
                reqs.append((name, count))

            if not reqs:
                raise ValueError("请输入至少一个子网需求")

            results = vlsm_calculate(base, reqs)
            self.vlsm_table.setRowCount(len(results))
            for i, r in enumerate(results):
                self.vlsm_table.setItem(i, 0, QTableWidgetItem(r['name']))
                self.vlsm_table.setItem(i, 1, QTableWidgetItem(str(r['hosts'])))
                self.vlsm_table.setItem(i, 2, QTableWidgetItem(f"{r['network']}{r['prefix']}"))
                self.vlsm_table.setItem(i, 3, QTableWidgetItem(r['mask']))
                self.vlsm_table.setItem(i, 4, QTableWidgetItem(r['first_usable']))
                self.vlsm_table.setItem(i, 5, QTableWidgetItem(r['last_usable']))
                self.vlsm_table.setItem(i, 6, QTableWidgetItem(r['broadcast']))

        except Exception as e:
            QMessageBox.warning(self, "错误", f"VLSM计算失败: {e}")

    def clear_vlsm(self):
        self.vlsm_table.setRowCount(0)

    def _build_subnet_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        param_frame, param_layout = self._build_section_frame("⚙️ 子网划分参数")
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(QLabel("主网络地址:"))
        self.subnet_base = QLineEdit("192.168.0.0/22")
        self.subnet_base.setMinimumWidth(300)
        row1.addWidget(self.subnet_base)
        param_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel("子网前缀:"))
        self.subnet_prefix = QLineEdit("24")
        self.subnet_prefix.setMaximumWidth(100)
        row2.addWidget(self.subnet_prefix)
        hint = QLabel("（例如: 24 表示 /24 子网）")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        row2.addWidget(hint)
        row2.addStretch()
        param_layout.addLayout(row2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        calc_btn = QPushButton("🚀 开始划分")
        calc_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        calc_btn.clicked.connect(self.calculate_subnet)
        export_btn = QPushButton("📤 导出CSV")
        export_btn.setStyleSheet("background-color: #3498db; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        export_btn.clicked.connect(self.export_subnet_csv)
        btn_row.addWidget(calc_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        param_layout.addLayout(btn_row)
        layout.addWidget(param_frame)

        # 分页控制
        pager_frame = QFrame()
        pager_layout = QHBoxLayout(pager_frame)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        self.subnet_page_info = QLabel("第 0 页 / 共 0 页 (共 0 个子网)")
        self.subnet_page_info.setStyleSheet("color: #555; font-size: 12px;")
        pager_layout.addWidget(self.subnet_page_info)

        self.btn_first = QPushButton("⏮ 首页")
        self.btn_first.setStyleSheet("padding: 5px 12px;")
        self.btn_first.clicked.connect(lambda: self.subnet_goto_page(0))
        pager_layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.setStyleSheet("padding: 5px 12px;")
        self.btn_prev.clicked.connect(self.subnet_prev_page)
        pager_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.setStyleSheet("padding: 5px 12px;")
        self.btn_next.clicked.connect(self.subnet_next_page)
        pager_layout.addWidget(self.btn_next)

        self.btn_last = QPushButton("末页 ⏭")
        self.btn_last.setStyleSheet("padding: 5px 12px;")
        self.btn_last.clicked.connect(self.subnet_last_page)
        pager_layout.addWidget(self.btn_last)

        pager_layout.addWidget(QLabel("每页显示:"))
        self.subnet_page_size = QComboBox()
        self.subnet_page_size.addItems(["20", "50", "100", "200"])
        self.subnet_page_size.setCurrentText("50")
        self.subnet_page_size.currentTextChanged.connect(lambda: self.subnet_goto_page(0))
        pager_layout.addWidget(self.subnet_page_size)

        pager_layout.addStretch()
        layout.addWidget(pager_frame)

        # 结果区
        result_frame, result_layout = self._build_result_frame()
        title = QLabel("📊 子网划分结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(title)

        self.subnet_table = QTableWidget()
        self.subnet_table.setColumnCount(7)
        self.subnet_table.setHorizontalHeaderLabels(["序号", "网络地址", "子网掩码", "首个可用IP", "最后可用IP", "广播地址", "可用主机数"])
        self.subnet_table.setAlternatingRowColors(True)
        self.subnet_table.setStyleSheet("""
            QTableWidget { font-size: 12px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 6px; font-weight: bold; }
        """)
        header = self.subnet_table.horizontalHeader()
        for i in range(7):
            header.setSectionResizeMode(i, QHeaderView.Stretch if i in [1, 2, 3, 4] else QHeaderView.ResizeToContents)
        result_layout.addWidget(self.subnet_table)
        layout.addWidget(result_frame, 1)

        self.subnet_all_results = []
        self.subnet_current_page = 0
        return page

    def calculate_subnet(self):
        try:
            base = self.subnet_base.text().strip()
            new_prefix = int(self.subnet_prefix.text().strip())
            self.subnet_all_results = equal_subnet_calculate(base, new_prefix)
            self.subnet_goto_page(0)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"子网划分失败: {e}")

    def subnet_goto_page(self, page):
        if not self.subnet_all_results:
            self.subnet_table.setRowCount(0)
            self.subnet_page_info.setText("第 0 页 / 共 0 页 (共 0 个子网)")
            return
        page_size = int(self.subnet_page_size.currentText())
        total = len(self.subnet_all_results)
        total_pages = (total + page_size - 1) // page_size
        self.subnet_current_page = max(0, min(page, total_pages - 1))

        start = self.subnet_current_page * page_size
        end = min(start + page_size, total)
        page_data = self.subnet_all_results[start:end]

        self.subnet_table.setRowCount(len(page_data))
        for i, r in enumerate(page_data):
            self.subnet_table.setItem(i, 0, QTableWidgetItem(str(r['index'])))
            self.subnet_table.setItem(i, 1, QTableWidgetItem(f"{r['network']}{r['prefix']}"))
            self.subnet_table.setItem(i, 2, QTableWidgetItem(r['mask']))
            self.subnet_table.setItem(i, 3, QTableWidgetItem(r['first_usable']))
            self.subnet_table.setItem(i, 4, QTableWidgetItem(r['last_usable']))
            self.subnet_table.setItem(i, 5, QTableWidgetItem(r['broadcast']))
            self.subnet_table.setItem(i, 6, QTableWidgetItem(str(r['usable'])))

        self.subnet_page_info.setText(f"第 {self.subnet_current_page + 1} 页 / 共 {total_pages} 页 (共 {total} 个子网)")

    def subnet_prev_page(self):
        if self.subnet_current_page > 0:
            self.subnet_goto_page(self.subnet_current_page - 1)

    def subnet_next_page(self):
        page_size = int(self.subnet_page_size.currentText())
        total_pages = (len(self.subnet_all_results) + page_size - 1) // page_size
        if self.subnet_current_page < total_pages - 1:
            self.subnet_goto_page(self.subnet_current_page + 1)

    def subnet_last_page(self):
        page_size = int(self.subnet_page_size.currentText())
        total_pages = (len(self.subnet_all_results) + page_size - 1) // page_size
        self.subnet_goto_page(total_pages - 1)

    def export_subnet_csv(self):
        if not self.subnet_all_results:
            QMessageBox.warning(self, "提示", "没有可导出的数据")
            return
        from PySide6.QtWidgets import QFileDialog
        import csv
        from datetime import datetime
        filepath, _ = QFileDialog.getSaveFileName(self, "保存CSV", f"subnet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "CSV文件 (*.csv)")
        if filepath:
            try:
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(["序号", "网络地址", "子网掩码", "首个可用IP", "最后可用IP", "广播地址", "可用主机数"])
                    for r in self.subnet_all_results:
                        writer.writerow([r['index'], f"{r['network']}{r['prefix']}", r['mask'], r['first_usable'], r['last_usable'], r['broadcast'], r['usable']])
                QMessageBox.information(self, "成功", f"已导出到 {filepath}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导出失败: {e}")

    def _build_summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        param_frame, param_layout = self._build_section_frame("📋 路由汇总参数")
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("输入多个子网地址（每行一个，格式: IP/前缀长度）"))
        row1.addStretch()
        param_layout.addLayout(row1)

        self.summary_input = QTextEdit()
        self.summary_input.setPlainText("192.168.0.0/24\n192.168.1.0/24\n192.168.2.0/24\n192.168.3.0/24")
        self.summary_input.setMaximumHeight(150)
        param_layout.addWidget(self.summary_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        calc_btn = QPushButton("🧮 计算汇总")
        calc_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        calc_btn.clicked.connect(self.calculate_summary)
        clear_btn = QPushButton("🗑 清空")
        clear_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        clear_btn.clicked.connect(lambda: self.summary_input.clear())
        btn_row.addWidget(calc_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        param_layout.addLayout(btn_row)
        layout.addWidget(param_frame)

        result_frame, result_layout = self._build_result_frame()
        title = QLabel("📊 路由汇总结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(title)

        self.summary_result = QTextEdit()
        self.summary_result.setReadOnly(True)
        self.summary_result.setStyleSheet("""
            QTextEdit {
                background-color: white;
                color: #333;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                line-height: 1.6;
                border: 1px solid #f0f0f0;
                border-radius: 3px;
                padding: 10px;
            }
        """)
        result_layout.addWidget(self.summary_result)
        layout.addWidget(result_frame, 1)
        return page

    def calculate_summary(self):
        try:
            text = self.summary_input.toPlainText()
            summary = route_summarize(text)

            # 解析输入的子网列表
            networks = []
            for line in text.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    networks.append(ipaddress.IPv4Network(line, strict=False))
                except:
                    pass

            output_lines = []
            output_lines.append("=" * 60)
            output_lines.append("📋 输入的子网列表：")
            output_lines.append("=" * 60)
            for i, net in enumerate(networks, 1):
                size = 2 ** (32 - net.prefixlen)
                output_lines.append(f"  {i}. {str(net.network_address):18}  ({size:>4} 地址)")
            output_lines.append("")
            output_lines.append("=" * 60)
            output_lines.append("🎯 路由汇总结果：")
            output_lines.append("=" * 60)
            output_lines.append(f"  汇总路由: {summary['summary_network']}{summary['summary_prefix']}")
            output_lines.append(f"  网络地址: {summary['summary_network']}")
            output_lines.append(f"  子网掩码: {summary['summary_mask']}")
            output_lines.append(f"  前缀长度: {summary['summary_prefix']}")
            output_lines.append(f"  地址范围: {summary['address_range']}")
            output_lines.append(f"  总地址数: {summary['total_addresses']:,}")
            output_lines.append("")
            output_lines.append("=" * 60)
            output_lines.append("📈 空间利用率：")
            output_lines.append("=" * 60)
            output_lines.append(f"  已使用地址: {summary['used_addresses']:,}")
            output_lines.append(f"  汇总后总数: {summary['total_addresses']:,}")
            wasted = summary['total_addresses'] - summary['used_addresses']
            output_lines.append(f"  浪费地址数: {wasted:,}")
            usage_rate = (summary['used_addresses'] / summary['total_addresses'] * 100) if summary['total_addresses'] > 0 else 0
            output_lines.append(f"  利用率: {usage_rate:.1f}%")
            output_lines.append("")
            if wasted == 0:
                output_lines.append("✅ 所有输入的子网都被汇总路由覆盖")
            else:
                output_lines.append(f"⚠️ 汇总后还有 {wasted:,} 个地址未被使用")

            self.summary_result.setPlainText("\n".join(output_lines))
        except Exception as e:
            self.summary_result.setPlainText(f"❌ {e}")

    def _build_wildcard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # 输入区
        input_frame, input_layout = self._build_section_frame("⚙ 反掩码计算输入")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("输入网络/掩码:"))
        self.wildcard_input = QLineEdit("192.168.1.0/24")
        self.wildcard_input.setMinimumWidth(300)
        row.addWidget(self.wildcard_input)
        row.addStretch()
        input_layout.addLayout(row)

        hint = QLabel("支持格式: 192.168.1.0/24   |   255.255.255.0   |   /24   |   多行批量")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        input_layout.addWidget(hint)

        # 批量输入区
        batch_label = QLabel("📋 批量输入（每行一个网络）")
        batch_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #00bcd4; margin-top: 5px;")
        input_layout.addWidget(batch_label)

        self.wildcard_batch_input = QTextEdit()
        self.wildcard_batch_input.setPlainText("10.0.0.0/8\n172.16.0.0/12\n192.168.1.0/24\n192.168.0.0/255.255.255.0")
        self.wildcard_batch_input.setMaximumHeight(90)
        self.wildcard_batch_input.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                padding: 6px;
            }
        """)
        input_layout.addWidget(self.wildcard_batch_input)

        # 按钮区
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        calc_btn = QPushButton("🔍 计算反掩码")
        calc_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        calc_btn.clicked.connect(self.calculate_wildcard_single)
        batch_btn = QPushButton("📋 批量计算")
        batch_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 8px 20px; border-radius: 3px;")
        batch_btn.clicked.connect(self.calculate_wildcard_batch)
        btn_row.addWidget(calc_btn)
        btn_row.addWidget(batch_btn)
        btn_row.addStretch()
        input_layout.addLayout(btn_row)

        layout.addWidget(input_frame)

        # 结果区
        result_frame, result_layout = self._build_result_frame()
        title = QLabel("📋 计算结果")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(title)

        self.wildcard_result = QTextEdit()
        self.wildcard_result.setReadOnly(True)
        self.wildcard_result.setStyleSheet("""
            QTextEdit {
                background-color: white;
                color: #333;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                line-height: 1.6;
                border: 1px solid #f0f0f0;
                border-radius: 3px;
                padding: 12px;
            }
        """)
        result_layout.addWidget(self.wildcard_result)
        layout.addWidget(result_frame, 1)
        return page

    def calculate_wildcard_single(self):
        """计算单个网络/掩码的完整信息"""
        try:
            text = self.wildcard_input.text().strip()
            if not text:
                self.wildcard_result.setPlainText("❌ 请输入网络地址或子网掩码")
                return

            if '/' in text or any(c.isdigit() for c in text.split('.') if len(c) <= 3):
                # 优先当作网络/掩码
                try:
                    info = calculate_wildcard_full(text)
                except Exception:
                    info = calculate_wildcard(text)
                    info['network'] = '-'
            else:
                info = calculate_wildcard(text)
                info['network'] = '-'

            output = []
            output.append("─" * 50)
            if info.get('network') and info['network'] != '-':
                output.append(f"网络地址      : <span style='color:#27ae60; font-weight:bold;'>{info['network']}</span>")
            output.append(f"前缀长度      : <span style='color:#27ae60; font-weight:bold;'>{info['prefix']}</span>")
            output.append(f"子网掩码      : <span style='color:#27ae60; font-weight:bold;'>{info['mask']}</span>")
            output.append(f"反掩码        : <span style='color:#27ae60; font-weight:bold;'>{info['wildcard']}</span>")
            if info.get('network') and info['network'] != '-':
                output.append(f"主机总数      : <span style='color:#27ae60; font-weight:bold;'>{info.get('total', '-')}</span>")
                output.append(f"可用主机数    : <span style='color:#27ae60; font-weight:bold;'>{info.get('usable', '-')}</span>")
            output.append("─" * 50)
            output.append("")

            if info.get('network') and info['network'] != '-':
                output.append("ACL 配置参考 (Cisco / 华为):")
                output.append(f"  <span style='color:#3498db;'>{info['cisco_acl']}</span>")
                output.append(f"  <span style='color:#3498db;'>{info['huawei_acl']}</span>")
                output.append("")
                output.append(f"掩码二进制    : <span style='color:#888;'>{info['binary_mask']}</span>")
                output.append(f"反掩码二进制  : <span style='color:#888;'>{info['binary_wildcard']}</span>")

            self.wildcard_result.setHtml("<br>".join(output))
        except Exception as e:
            self.wildcard_result.setHtml(f"<span style='color:#e74c3c;'>❌ {e}</span>")

    def calculate_wildcard_batch(self):
        """批量计算反掩码"""
        try:
            text = self.wildcard_batch_input.toPlainText()
            if not text.strip():
                self.wildcard_result.setPlainText("❌ 请输入批量内容")
                return

            results = calculate_wildcard_batch(text)
            output = []
            output.append(f"{'─' * 70}")
            output.append(f"批量计算结果（共 {len(results)} 项）")
            output.append(f"{'─' * 70}")
            output.append("")

            for i, r in enumerate(results, 1):
                if r['success']:
                    output.append(f"[{i}] 输入: <span style='color:#888;'>{r['input']}</span>")
                    if r.get('network') and r['network'] != '-':
                        output.append(f"    网络: {r['network']}{r['prefix']}   掩码: {r['mask']}   反掩码: {r['wildcard']}")
                    else:
                        output.append(f"    掩码: {r['mask']}   反掩码: {r['wildcard']}   前缀: {r['prefix']}")
                    if r.get('cisco_acl'):
                        output.append(f"    ACL: {r['cisco_acl']}")
                    output.append("")
                else:
                    output.append(f"[{i}] 输入: <span style='color:#888;'>{r['input']}</span>")
                    output.append(f"    <span style='color:#e74c3c;'>❌ 错误: {r['error']}</span>")
                    output.append("")

            self.wildcard_result.setHtml("<br>".join(output))
        except Exception as e:
            self.wildcard_result.setHtml(f"<span style='color:#e74c3c;'>❌ {e}</span>")

    def calculate_wildcard(self):
        """兼容旧接口"""
        self.calculate_wildcard_single()

    def cleanup(self):
        pass

    def stop_all(self):
        self.cleanup()

    def stop_update_timer(self):
        self.cleanup()