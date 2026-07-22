import subprocess
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QComboBox, QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class ToolsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title_label = QLabel("实用工具")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)
        
        tabs = QComboBox()
        tabs.addItems(["子网计算", "IP信息检测", "MAC地址工具", "路由表查看"])
        tabs.currentIndexChanged.connect(self.switch_tab)
        layout.addWidget(tabs)
        
        self.tab_container = QWidget()
        self.tab_layout = QVBoxLayout(self.tab_container)
        layout.addWidget(self.tab_container)
        
        self.create_subnet_calculator()
    
    def switch_tab(self, index):
        for i in reversed(range(self.tab_layout.count())):
            self.tab_layout.itemAt(i).widget().deleteLater()
        
        if index == 0:
            self.create_subnet_calculator()
        elif index == 1:
            self.create_ip_info()
        elif index == 2:
            self.create_mac_tools()
        elif index == 3:
            self.create_route_table()
    
    def create_subnet_calculator(self):
        group = QGroupBox("子网计算器")
        layout = QVBoxLayout(group)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("IP地址/CIDR:"))
        self.subnet_input = QLineEdit("192.168.1.100/24")
        input_layout.addWidget(self.subnet_input)
        calc_btn = QPushButton("计算")
        calc_btn.clicked.connect(self.calculate_subnet)
        input_layout.addWidget(calc_btn)
        layout.addLayout(input_layout)
        
        self.subnet_result = QTextEdit()
        self.subnet_result.setReadOnly(True)
        self.subnet_result.setMaximumHeight(200)
        layout.addWidget(self.subnet_result)
        
        self.tab_layout.addWidget(group)
        self.calculate_subnet()
    
    def calculate_subnet(self):
        try:
            import ipaddress
            network = ipaddress.IPv4Network(self.subnet_input.text(), strict=False)
            
            result = []
            result.append(f"网络地址: {network.network_address}")
            result.append(f"广播地址: {network.broadcast_address}")
            result.append(f"子网掩码: {network.netmask}")
            result.append(f"前缀长度: {network.prefixlen}")
            result.append(f"可用主机数: {network.num_addresses - 2}")
            result.append(f"第一个可用IP: {network[1]}")
            result.append(f"最后一个可用IP: {network[-2]}")
            result.append(f"IP范围: {network.network_address} - {network.broadcast_address}")
            result.append(f"Wildcard掩码: {network.hostmask}")
            
            self.subnet_result.setPlainText('\n'.join(result))
        except Exception as e:
            self.subnet_result.setPlainText(f"错误: {str(e)}")
    
    def create_ip_info(self):
        group = QGroupBox("IP信息检测")
        layout = QVBoxLayout(group)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("IP地址/域名:"))
        self.ip_input = QLineEdit("www.baidu.com")
        input_layout.addWidget(self.ip_input)
        query_btn = QPushButton("查询")
        query_btn.clicked.connect(self.query_ip_info)
        input_layout.addWidget(query_btn)
        layout.addLayout(input_layout)
        
        self.ip_result = QTextEdit()
        self.ip_result.setReadOnly(True)
        self.ip_result.setMaximumHeight(200)
        layout.addWidget(self.ip_result)
        
        self.tab_layout.addWidget(group)
    
    def query_ip_info(self):
        target = self.ip_input.text().strip()
        
        import socket
        try:
            ip_address = socket.gethostbyname(target)
            
            result = []
            result.append(f"目标: {target}")
            result.append(f"IP地址: {ip_address}")
            
            try:
                hostname = socket.gethostbyaddr(ip_address)[0]
                result.append(f"反向解析: {hostname}")
            except:
                result.append(f"反向解析: 无")
            
            try:
                import requests
                response = requests.get(f"http://ip-api.com/json/{ip_address}")
                data = response.json()
                if data.get('status') == 'success':
                    result.append(f"国家: {data.get('country', '未知')}")
                    result.append(f"地区: {data.get('regionName', '未知')}")
                    result.append(f"城市: {data.get('city', '未知')}")
                    result.append(f"ISP: {data.get('isp', '未知')}")
                    result.append(f"AS: {data.get('as', '未知')}")
            except:
                result.append("地理信息查询失败")
            
            self.ip_result.setPlainText('\n'.join(result))
        except Exception as e:
            self.ip_result.setPlainText(f"错误: {str(e)}")
    
    def create_mac_tools(self):
        group = QGroupBox("MAC地址工具")
        layout = QVBoxLayout(group)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("MAC地址:"))
        self.mac_input = QLineEdit("00-11-22-33-44-55")
        input_layout.addWidget(self.mac_input)
        query_btn = QPushButton("查询厂商")
        query_btn.clicked.connect(self.query_mac_vendor)
        input_layout.addWidget(query_btn)
        layout.addLayout(input_layout)
        
        format_layout = QHBoxLayout()
        format_btn = QPushButton("格式化")
        format_btn.clicked.connect(self.format_mac)
        format_layout.addWidget(format_btn)
        
        generate_btn = QPushButton("生成随机MAC")
        generate_btn.clicked.connect(self.generate_random_mac)
        format_layout.addWidget(generate_btn)
        
        layout.addLayout(format_layout)
        
        self.mac_result = QTextEdit()
        self.mac_result.setReadOnly(True)
        self.mac_result.setMaximumHeight(150)
        layout.addWidget(self.mac_result)
        
        self.tab_layout.addWidget(group)
    
    def query_mac_vendor(self):
        mac = self.mac_input.text().strip()
        mac_clean = re.sub(r'[^0-9A-Fa-f]', '', mac).upper()
        
        if len(mac_clean) < 6:
            self.mac_result.setPlainText("无效的MAC地址")
            return
        
        oui = mac_clean[:6]
        
        try:
            import requests
            response = requests.get(f"https://api.maclookup.app/v2/macs/{oui}")
            data = response.json()
            
            if data.get('company'):
                result = []
                result.append(f"MAC地址: {mac}")
                result.append(f"厂商: {data.get('company', '未知')}")
                result.append(f"地址: {data.get('address', '未知')}")
                result.append(f"国家: {data.get('country', '未知')}")
                self.mac_result.setPlainText('\n'.join(result))
            else:
                self.mac_result.setPlainText("未找到厂商信息")
        except Exception as e:
            self.mac_result.setPlainText(f"查询失败: {str(e)}")
    
    def format_mac(self):
        mac = self.mac_input.text().strip()
        mac_clean = re.sub(r'[^0-9A-Fa-f]', '', mac).upper()
        
        if len(mac_clean) != 12:
            self.mac_result.setPlainText("无效的MAC地址")
            return
        
        formats = []
        formats.append(f"带冒号: {':'.join(mac_clean[i:i+2] for i in range(0, 12, 2))}")
        formats.append(f"带短横线: {'-'.join(mac_clean[i:i+2] for i in range(0, 12, 2))}")
        formats.append(f"无分隔符: {mac_clean}")
        formats.append(f"小写: {mac_clean.lower()}")
        
        self.mac_result.setPlainText('\n'.join(formats))
    
    def generate_random_mac(self):
        import random
        mac = [0x00, 0x11, random.randint(0x00, 0xff),
               random.randint(0x00, 0xff),
               random.randint(0x00, 0xff),
               random.randint(0x00, 0xff)]
        
        mac_str = ':'.join(f"{byte:02x}" for byte in mac)
        self.mac_input.setText(mac_str)
        self.mac_result.setPlainText(f"生成的MAC地址: {mac_str}")
    
    def create_route_table(self):
        group = QGroupBox("路由表")
        layout = QVBoxLayout(group)
        
        refresh_btn = QPushButton("刷新路由表")
        refresh_btn.clicked.connect(self.refresh_routes)
        layout.addWidget(refresh_btn)
        
        self.route_table = QTableWidget()
        self.route_table.setColumnCount(4)
        self.route_table.setHorizontalHeaderLabels(["网络目标", "网络掩码", "网关", "接口"])
        self.route_table.setColumnWidth(0, 180)
        self.route_table.setColumnWidth(1, 180)
        self.route_table.setColumnWidth(2, 150)
        self.route_table.setColumnWidth(3, 150)
        layout.addWidget(self.route_table)
        
        self.tab_layout.addWidget(group)
        self.refresh_routes()
    
    def refresh_routes(self):
        try:
            result = subprocess.run(
                ["route", "print"],
                capture_output=True,
                text=True,
                encoding="gbk"
            )
            
            lines = result.stdout.split('\n')
            routes = []
            
            for line in lines:
                line = line.strip()
                if line and re.match(r'^\d', line):
                    parts = re.split(r'\s+', line)
                    if len(parts) >= 4:
                        routes.append({
                            'destination': parts[0],
                            'mask': parts[1],
                            'gateway': parts[2],
                            'interface': parts[3]
                        })
            
            self.route_table.setRowCount(len(routes))
            for i, route in enumerate(routes):
                self.route_table.setItem(i, 0, QTableWidgetItem(route['destination']))
                self.route_table.setItem(i, 1, QTableWidgetItem(route['mask']))
                self.route_table.setItem(i, 2, QTableWidgetItem(route['gateway']))
                self.route_table.setItem(i, 3, QTableWidgetItem(route['interface']))
                
                if route['gateway'] == '0.0.0.0':
                    self.route_table.item(i, 2).setForeground(Qt.red)
        except Exception as e:
            self.route_table.setRowCount(1)
            self.route_table.setItem(0, 0, QTableWidgetItem(f"获取路由表失败: {str(e)}"))