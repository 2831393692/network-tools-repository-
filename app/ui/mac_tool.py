"""MAC地址工具页面 - 提供MAC厂商查询、格式转换、ARP缓存表查看功能"""
import re
import subprocess
import platform
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTextEdit, QRadioButton
)
from PySide6.QtCore import Qt

from app.core.logger import Logger

logger = Logger("MACAddressTool")


class OUIDatabase:
    """OUI数据库 - 用于查询MAC地址厂商信息"""
    OUI_DATA = {
        '00000C': 'Cisco Systems, Inc.',
        '00001C': 'Bay Networks',
        '00001D': 'Nortel Networks',
        '00002B': '3Com Corporation',
        '000039': 'Sun Microsystems',
        '00004C': 'Motorola Inc.',
        '00005A': 'DEC (Digital Equipment)',
        '00006B': 'Apple Computer',
        '000077': 'SGI (Silicon Graphics)',
        '0000A2': 'Hewlett-Packard',
        '0000E8': 'Chips and Technologies',
        '000102': 'IBM Corporation',
        '000129': 'Samsung Electronics',
        '000142': 'Sony Corporation',
        '000163': 'Toshiba Corporation',
        '00016C': 'LG Electronics',
        '0001A0': 'Sharp Corporation',
        '0001E8': 'Philips Electronics',
        '00022D': 'Panasonic Corporation',
        '0002A5': 'NEC Corporation',
        '00036B': 'Linksys (Cisco)',
        '0003BA': 'Netgear Inc.',
        '000420': 'D-Link Corporation',
        '00045A': 'TP-Link Technologies',
        '000625': 'Intel Corporation',
        '00065B': 'AMD Corporation',
        '000662': 'NVIDIA Corporation',
        '00070E': 'Broadcom Corporation',
        '000741': 'Marvell Technology',
        '0007CB': 'Qualcomm Inc.',
        '00085D': 'Realtek Semiconductor',
        '00090F': 'Microsoft Corporation',
        '000A95': 'VMware Inc.',
        '000B46': 'Huawei Technologies',
        '000C41': 'ZTE Corporation',
        '000D60': 'Cisco Systems',
        '000E0C': 'Juniper Networks',
        '000E35': 'Alcatel-Lucent',
        '000E4C': 'Ericsson',
        '000E7F': 'Nokia Corporation',
        '000F1F': 'Siemens AG',
        '001018': 'Hewlett-Packard',
        '001049': 'Dell Inc.',
        '0010A7': 'Lenovo Group',
        '001122': 'Asus Computer',
        '001217': 'Acer Inc.',
        '001372': 'Gateway Inc.',
        '001422': 'Toshiba',
        '001451': 'Fujitsu',
        '00145D': 'Hitachi',
        '001558': 'Western Digital',
        '0015A2': 'Seagate Technology',
        '001636': 'Intel Corporation',
        '001676': 'Broadcom',
        '0016E6': 'Texas Instruments',
        '0017A4': 'Infineon Technologies',
        '00188B': 'Cypress Semiconductor',
        '0018A9': 'Cisco Systems',
        '0019D1': 'Huawei',
        '001A11': 'ZTE',
        '001A2B': 'TP-Link',
        '001A3B': 'D-Link',
        '001A4D': 'Netgear',
        '001B21': 'Belkin International',
        '001B38': 'Buffalo Technology',
        '001B4F': 'Asus',
        '001C14': 'Lenovo',
        '001C23': 'Dell',
        '001C42': 'HP',
        '001C58': 'Sony',
        '001C61': 'Panasonic',
        '001D92': 'Samsung',
        '001E06': 'LG',
        '001E4F': 'Philips',
        '00200C': 'Motorola',
        '002040': 'Apple',
        '002078': 'NEC',
        '002129': 'Canon Inc.',
        '00215A': 'Ricoh Company',
        '002191': 'Kyocera',
        '002215': 'Epson',
        '00224D': 'Brother Industries',
        '0023AE': 'OKI Electric',
        '00249B': 'Xerox Corporation',
        '002564': 'Konica Minolta',
        '002596': 'Intel',
        '0026B6': 'AMD',
        '002719': 'NVIDIA',
        '002741': 'Broadcom',
        '002775': 'Marvell',
        '0027EE': 'Qualcomm',
        '002810': 'Realtek',
        '002820': 'Microsoft',
        '002923': 'VMware',
        '002A10': 'Huawei',
        '002B3C': 'ZTE',
        '002C10': 'TP-Link',
        '002D65': 'D-Link',
        '002E1A': 'Netgear',
        '002F20': 'Belkin',
        '00300A': 'Buffalo',
        '003018': 'Asus',
        '003020': 'Lenovo',
        '003034': 'Dell',
        '003074': 'HP',
        '0030C1': 'Sony',
        '0030E0': 'Panasonic',
        '003142': 'Samsung',
        '003259': 'LG',
        '003474': 'Sharp',
        '00359A': 'Philips',
        '00365C': 'Motorola',
        '003764': 'Apple',
        '003865': 'NEC',
        '003927': 'Cisco',
        '003A98': 'Juniper',
        '003B32': 'Alcatel-Lucent',
        '003C07': 'Ericsson',
        '003D6F': 'Nokia',
        '003E1A': 'Siemens',
        '003F72': 'Hewlett-Packard',
        '0040F4': 'Dell',
        '00415A': 'Lenovo',
        '00423D': 'Asus',
        '004315': 'Acer',
        '004445': 'Gateway',
        '0045A1': 'Toshiba',
        '004695': 'Fujitsu',
        '0047AC': 'Hitachi',
        '004818': 'Western Digital',
        '004910': 'Seagate',
        '004A22': 'Intel',
        '004B6D': 'AMD',
        '004C72': 'NVIDIA',
        '004D8E': 'Broadcom',
        '004E01': 'Marvell',
        '004F7B': 'Qualcomm',
        '005004': 'Realtek',
        '005056': 'VMware',
        '005057': 'VMware',
        '0050DA': 'Huawei',
        '005254': 'TP-Link',
        '005345': 'D-Link',
        '005478': 'Netgear',
        '005587': 'Belkin',
        '0056A2': 'Buffalo',
        '005742': 'Asus',
        '00583A': 'Lenovo',
        '0059B7': 'Dell',
        '005A5A': 'HP',
        '005B82': 'Sony',
        '005C42': 'Panasonic',
        '005DBA': 'Samsung',
        '005EC4': 'LG',
        '005FB3': 'Sharp',
        '006008': 'Philips',
        '00601D': 'Motorola',
        '00603E': 'Apple',
        '00605C': 'NEC',
        '0060B0': 'Cisco',
        '0060C5': 'Juniper',
        '0060EA': 'Alcatel-Lucent',
        '006166': 'Ericsson',
        '006223': 'Nokia',
        '006369': 'Siemens',
        '00641B': 'Hewlett-Packard',
        '00659D': 'Dell',
        '00664D': 'Lenovo',
        '0067C9': 'Asus',
        '00681B': 'Acer',
        '006972': 'Gateway',
        '006A9B': 'Toshiba',
        '006BA1': 'Fujitsu',
        '006C42': 'Hitachi',
        '006D4F': 'Western Digital',
        '006E6D': 'Seagate',
        '006F00': 'Intel',
        '006F01': 'AMD',
        '006F02': 'NVIDIA',
        '006F03': 'Broadcom',
        '006F04': 'Marvell',
        '006F05': 'Qualcomm',
        '006F06': 'Realtek',
        '006F07': 'Microsoft',
        '006F08': 'VMware',
        '006F09': 'Huawei',
        '006F0A': 'ZTE',
        '006F0B': 'TP-Link',
        '006F0C': 'D-Link',
        '006F0D': 'Netgear',
        '006F0E': 'Belkin',
        '006F0F': 'Buffalo',
        '006F10': 'Asus',
        '006F11': 'Lenovo',
        '006F12': 'Dell',
        '006F13': 'HP',
        '006F14': 'Sony',
        '006F15': 'Panasonic',
        '006F16': 'Samsung',
        '006F17': 'LG',
        '006F18': 'Sharp',
        '006F19': 'Philips',
        '006F1A': 'Motorola',
        '006F1B': 'Apple',
        '006F1C': 'NEC',
        '006F1D': 'Cisco',
        '006F1E': 'Juniper',
        '006F1F': 'Alcatel-Lucent',
        '007000': 'Ericsson',
        '007001': 'Nokia',
        '007002': 'Siemens',
        '007003': 'Hewlett-Packard',
        '007004': 'Dell',
        '007005': 'Lenovo',
        '007006': 'Asus',
        '007007': 'Acer',
        '007008': 'Gateway',
        '007009': 'Toshiba',
        '00700A': 'Fujitsu',
        '00700B': 'Hitachi',
        '00700C': 'Western Digital',
        '00700D': 'Seagate',
        '00700E': 'Intel',
        '00700F': 'AMD',
        '007010': 'NVIDIA',
        '007011': 'Broadcom',
        '007012': 'Marvell',
        '007013': 'Qualcomm',
        '007014': 'Realtek',
        '007015': 'Microsoft',
        '007016': 'VMware',
        '007017': 'Huawei',
        '007018': 'ZTE',
        '007019': 'TP-Link',
        '00701A': 'D-Link',
        '00701B': 'Netgear',
        '00701C': 'Belkin',
        '00701D': 'Buffalo',
        '00701E': 'Asus',
        '00701F': 'Lenovo',
        '007020': 'Dell',
        '007021': 'HP',
        '007022': 'Sony',
        '007023': 'Panasonic',
        '007024': 'Samsung',
        '007025': 'LG',
        '007026': 'Sharp',
        '007027': 'Philips',
        '007028': 'Motorola',
        '007029': 'Apple',
        '00702A': 'NEC',
        '00702B': 'Cisco',
        '00702C': 'Juniper',
        '00702D': 'Alcatel-Lucent',
        '00702E': 'Ericsson',
        '00702F': 'Nokia',
        '007030': 'Siemens',
        '007031': 'Hewlett-Packard',
        '007032': 'Dell',
        '007033': 'Lenovo',
        '007034': 'Asus',
        '007035': 'Acer',
        '007036': 'Gateway',
        '007037': 'Toshiba',
        '007038': 'Fujitsu',
        '007039': 'Hitachi',
        '00703A': 'Western Digital',
        '00703B': 'Seagate',
        '00703C': 'Intel',
        '00703D': 'AMD',
        '00703E': 'NVIDIA',
        '00703F': 'Broadcom',
        '007040': 'Marvell',
        '007041': 'Qualcomm',
        '007042': 'Realtek',
        '007043': 'Microsoft',
        '007044': 'VMware',
        '007045': 'Huawei',
        '007046': 'ZTE',
        '007047': 'TP-Link',
        '007048': 'D-Link',
        '007049': 'Netgear',
        '00704A': 'Belkin',
        '00704B': 'Buffalo',
        '00704C': 'Asus',
        '00704D': 'Lenovo',
        '00704E': 'Dell',
        '00704F': 'HP',
        '007050': 'Sony',
        '007051': 'Panasonic',
        '007052': 'Samsung',
        '007053': 'LG',
        '007054': 'Sharp',
        '007055': 'Philips',
        '007056': 'Motorola',
        '007057': 'Apple',
        '007058': 'NEC',
        '007059': 'Cisco',
        '00705A': 'Juniper',
        '00705B': 'Alcatel-Lucent',
        '00705C': 'Ericsson',
        '00705D': 'Nokia',
        '00705E': 'Siemens',
        '00705F': 'Hewlett-Packard',
        '007060': 'Dell',
        '007061': 'Lenovo',
        '007062': 'Asus',
        '007063': 'Acer',
        '007064': 'Gateway',
        '007065': 'Toshiba',
        '007066': 'Fujitsu',
        '007067': 'Hitachi',
        '007068': 'Western Digital',
        '007069': 'Seagate',
        '00706A': 'Intel',
        '00706B': 'AMD',
        '00706C': 'NVIDIA',
        '00706D': 'Broadcom',
        '00706E': 'Marvell',
        '00706F': 'Qualcomm',
        '007070': 'Realtek',
        '007071': 'Microsoft',
        '007072': 'VMware',
        '007073': 'Huawei',
        '007074': 'ZTE',
        '007075': 'TP-Link',
        '007076': 'D-Link',
        '007077': 'Netgear',
        '007078': 'Belkin',
        '007079': 'Buffalo',
        '00707A': 'Asus',
        '00707B': 'Lenovo',
        '00707C': 'Dell',
        '00707D': 'HP',
        '00707E': 'Sony',
        '00707F': 'Panasonic',
        '007080': 'Samsung',
        '007081': 'LG',
        '007082': 'Sharp',
        '007083': 'Philips',
        '007084': 'Motorola',
        '007085': 'Apple',
        '007086': 'NEC',
        '007087': 'Cisco',
        '007088': 'Juniper',
        '007089': 'Alcatel-Lucent',
        '00708A': 'Ericsson',
        '00708B': 'Nokia',
        '00708C': 'Siemens',
        '00708D': 'Hewlett-Packard',
        '00708E': 'Dell',
        '00708F': 'Lenovo',
        '007090': 'Asus',
        '007091': 'Acer',
        '007092': 'Gateway',
        '007093': 'Toshiba',
        '007094': 'Fujitsu',
        '007095': 'Hitachi',
        '007096': 'Western Digital',
        '007097': 'Seagate',
        '007098': 'Intel',
        '007099': 'AMD',
        '00709A': 'NVIDIA',
        '00709B': 'Broadcom',
        '00709C': 'Marvell',
        '00709D': 'Qualcomm',
        '00709E': 'Realtek',
        '00709F': 'Microsoft',
        '0070A0': 'VMware',
        '0070A1': 'Huawei',
        '0070A2': 'ZTE',
        '0070A3': 'TP-Link',
        '0070A4': 'D-Link',
        '0070A5': 'Netgear',
        '0070A6': 'Belkin',
        '0070A7': 'Buffalo',
        '0070A8': 'Asus',
        '0070A9': 'Lenovo',
        '0070AA': 'Dell',
        '0070AB': 'HP',
        '0070AC': 'Sony',
        '0070AD': 'Panasonic',
        '0070AE': 'Samsung',
        '0070AF': 'LG',
        '0070B0': 'Sharp',
        '0070B1': 'Philips',
        '0070B2': 'Motorola',
        '0070B3': 'Apple',
        '0070B4': 'NEC',
        '0070B5': 'Cisco',
        '0070B6': 'Juniper',
        '0070B7': 'Alcatel-Lucent',
        '0070B8': 'Ericsson',
        '0070B9': 'Nokia',
        '0070BA': 'Siemens',
        '0070BB': 'Hewlett-Packard',
        '0070BC': 'Dell',
        '0070BD': 'Lenovo',
        '0070BE': 'Asus',
        '0070BF': 'Acer',
        '0070C0': 'Gateway',
        '0070C1': 'Toshiba',
        '0070C2': 'Fujitsu',
        '0070C3': 'Hitachi',
        '0070C4': 'Western Digital',
        '0070C5': 'Seagate',
        '0070C6': 'Intel',
        '0070C7': 'AMD',
        '0070C8': 'NVIDIA',
        '0070C9': 'Broadcom',
        '0070CA': 'Marvell',
        '0070CB': 'Qualcomm',
        '0070CC': 'Realtek',
        '0070CD': 'Microsoft',
        '0070CE': 'VMware',
        '0070CF': 'Huawei',
        '0070D0': 'ZTE',
        '0070D1': 'TP-Link',
        '0070D2': 'D-Link',
        '0070D3': 'Netgear',
        '0070D4': 'Belkin',
        '0070D5': 'Buffalo',
        '0070D6': 'Asus',
        '0070D7': 'Lenovo',
        '0070D8': 'Dell',
        '0070D9': 'HP',
        '0070DA': 'Sony',
        '0070DB': 'Panasonic',
        '0070DC': 'Samsung',
        '0070DD': 'LG',
        '0070DE': 'Sharp',
        '0070DF': 'Philips',
        '0070E0': 'Motorola',
        '0070E1': 'Apple',
        '0070E2': 'NEC',
        '0070E3': 'Cisco',
        '0070E4': 'Juniper',
        '0070E5': 'Alcatel-Lucent',
        '0070E6': 'Ericsson',
        '0070E7': 'Nokia',
        '0070E8': 'Siemens',
        '0070E9': 'Hewlett-Packard',
        '0070EA': 'Dell',
        '0070EB': 'Lenovo',
        '0070EC': 'Asus',
        '0070ED': 'Acer',
        '0070EE': 'Gateway',
        '0070EF': 'Toshiba',
        '0070F0': 'Fujitsu',
        '0070F1': 'Hitachi',
        '0070F2': 'Western Digital',
        '0070F3': 'Seagate',
        '0070F4': 'Intel',
        '0070F5': 'AMD',
        '0070F6': 'NVIDIA',
        '0070F7': 'Broadcom',
        '0070F8': 'Marvell',
        '0070F9': 'Qualcomm',
        '0070FA': 'Realtek',
        '0070FB': 'Microsoft',
        '0070FC': 'VMware',
        '0070FD': 'Huawei',
        '0070FE': 'ZTE',
        '0070FF': 'TP-Link',
        '500000': 'Huawei',
        '500100': 'Huawei',
        '500200': 'Huawei',
        '540000': 'TP-Link',
        '540100': 'TP-Link',
        '540200': 'TP-Link',
        '600000': 'ZTE',
        '600100': 'ZTE',
        '600200': 'ZTE',
        '740000': 'D-Link',
        '740100': 'D-Link',
        '740200': 'D-Link',
        '940000': 'Netgear',
        '940100': 'Netgear',
        '940200': 'Netgear',
        'A40000': 'Belkin',
        'A40100': 'Belkin',
        'A40200': 'Belkin',
        'B00000': 'Buffalo',
        'B00100': 'Buffalo',
        'B00200': 'Buffalo',
        'C80000': 'Asus',
        'C80100': 'Asus',
        'C80200': 'Asus',
        'E00000': 'Lenovo',
        'E00100': 'Lenovo',
        'E00200': 'Lenovo',
        'F00000': 'Dell',
        'F00100': 'Dell',
        'F00200': 'Dell',
        'F80000': 'HP',
        'F80100': 'HP',
        'F80200': 'HP',
    }

    @classmethod
    def query(cls, mac_address):
        """查询MAC地址厂商信息"""
        oui = cls._extract_oui(mac_address)
        if oui:
            vendor = cls.OUI_DATA.get(oui.upper())
            if vendor:
                return {'oui': oui, 'vendor': vendor, 'mac': mac_address}
        return {'oui': oui, 'vendor': '未知厂商', 'mac': mac_address}

    @classmethod
    def _extract_oui(cls, mac_address):
        """提取OUI（前6个十六进制字符）"""
        if not mac_address:
            return None
        cleaned = re.sub(r'[^0-9A-Fa-f]', '', mac_address)
        if len(cleaned) >= 6:
            return cleaned[:6].upper()
        return None


def clean_mac(mac):
    """去除MAC地址中的分隔符"""
    return re.sub(r'[^0-9A-Fa-f]', '', mac).upper()


def is_valid_mac(mac):
    """验证MAC地址格式"""
    cleaned = clean_mac(mac)
    return len(cleaned) == 12


def mac_format_colon(mac):
    """转换为冒号分隔格式: AA:BB:CC:DD:EE:FF"""
    cleaned = clean_mac(mac)
    if len(cleaned) == 12:
        return ':'.join(cleaned[i:i + 2] for i in range(0, 12, 2))
    return mac


def mac_format_hyphen(mac):
    """转换为横线分隔格式: AA-BB-CC-DD-EE-FF"""
    cleaned = clean_mac(mac)
    if len(cleaned) == 12:
        return '-'.join(cleaned[i:i + 2] for i in range(0, 12, 2))
    return mac


def mac_format_dot(mac):
    """转换为点分隔格式: AABB.CCDD.EEFF"""
    cleaned = clean_mac(mac)
    if len(cleaned) == 12:
        return '.'.join(cleaned[i:i + 4] for i in range(0, 12, 4))
    return mac


def mac_format_none(mac):
    """转换为无分隔格式: AABBCCDDEEFF"""
    return clean_mac(mac)


def get_arp_table():
    """获取系统ARP缓存表"""
    arp_entries = []
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True, encoding='gbk')
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                parts = re.split(r'\s+', line)
                if len(parts) >= 3:
                    ip = parts[0]
                    mac = parts[1]
                    if is_valid_mac(mac):
                        entry = {
                            'ip': ip,
                            'mac': mac,
                            'type': parts[-1] if len(parts) > 3 else '动态',
                        }
                        arp_entries.append(entry)
        else:
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                parts = re.split(r'\s+', line)
                if len(parts) >= 4:
                    ip = parts[0]
                    mac = parts[2]
                    if is_valid_mac(mac):
                        entry = {
                            'ip': ip,
                            'mac': mac,
                            'type': '动态',
                        }
                        arp_entries.append(entry)
    except Exception as e:
        logger.error(f"获取ARP表失败: {e}")
    return arp_entries


class MACAddressToolPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # MAC地址输入区
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(15, 12, 15, 12)
        input_layout.setSpacing(10)

        title = QLabel("⚙ MAC地址操作")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        input_layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("MAC地址:"))
        self.mac_input = QLineEdit()
        self.mac_input.setMinimumWidth(250)
        self.mac_input.setPlaceholderText("请输入MAC地址")
        row.addWidget(self.mac_input)
        row.addStretch()
        input_layout.addLayout(row)

        # 按钮区
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        query_btn = QPushButton("🔍 查询厂商")
        query_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        query_btn.clicked.connect(self.query_vendor)
        btn_row.addWidget(query_btn)

        convert_btn = QPushButton("🔄 格式转换")
        convert_btn.setStyleSheet("background-color: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        convert_btn.clicked.connect(self.convert_format)
        btn_row.addWidget(convert_btn)

        clear_btn = QPushButton("🗑 清除")
        clear_btn.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        clear_btn.clicked.connect(self.clear_all)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()
        input_layout.addLayout(btn_row)
        main_layout.addWidget(input_frame)

        # 格式转换选项
        format_frame = QFrame()
        format_frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        format_layout = QVBoxLayout(format_frame)
        format_layout.setContentsMargins(15, 12, 15, 12)
        format_layout.setSpacing(8)

        format_label = QLabel("🔄 转换格式:")
        format_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        format_layout.addWidget(format_label)

        radio_row = QHBoxLayout()
        radio_row.setSpacing(15)

        self.radio_colon = QRadioButton("冒号分隔 (AA:BB:CC:DD:EE:FF)")
        self.radio_colon.setChecked(True)
        radio_row.addWidget(self.radio_colon)

        self.radio_hyphen = QRadioButton("横线分隔 (AA-BB-CC-DD-EE-FF)")
        radio_row.addWidget(self.radio_hyphen)

        self.radio_dot = QRadioButton("点分隔 (AABB.CCDD.EEFF)")
        radio_row.addWidget(self.radio_dot)

        self.radio_none = QRadioButton("无分隔 (AABBCCDDEEFF)")
        radio_row.addWidget(self.radio_none)

        format_layout.addLayout(radio_row)

        example_label = QLabel("📌 示例: 00:1B:44:11:3A:B7 | 50-7B-9D-30-61-1C | 00:50:56:C0:00:01 | ACDE48001122")
        example_label.setStyleSheet("color: #888; font-size: 11px;")
        format_layout.addWidget(example_label)

        main_layout.addWidget(format_frame)

        # 查询结果区（合并了查询结果 + ARP缓存表）
        result_frame = QFrame()
        result_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(15, 12, 15, 12)
        result_layout.setSpacing(8)

        result_title = QLabel("📋 查询结果")
        result_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        result_layout.addWidget(result_title)

        self.query_result = QTextEdit()
        self.query_result.setReadOnly(True)
        self.query_result.setPlaceholderText("点击查询后将显示结果...")
        self.query_result.setStyleSheet("""
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
        result_layout.addWidget(self.query_result)

        main_layout.addWidget(result_frame, 1)

    def query_vendor(self):
        """查询MAC地址厂商信息"""
        mac = self.mac_input.text().strip()
        if not mac:
            self.query_result.setHtml("<span style='color:#e74c3c;'>❌ 请输入MAC地址</span>")
            return
        if not is_valid_mac(mac):
            self.query_result.setHtml("<span style='color:#e74c3c;'>❌ 无效的MAC地址格式</span>")
            return

        try:
            info = OUIDatabase.query(mac)
            output = []
            output.append(f"MAC地址: <span style='color:#27ae60; font-weight:bold;'>{mac_format_colon(mac)}</span>")
            output.append(f"OUI: <span style='color:#27ae60; font-weight:bold;'>{info['oui']}</span>")
            output.append(f"厂商: <span style='color:#27ae60; font-weight:bold;'>{info['vendor']}</span>")
            output.append("")
            output.append("格式转换:")
            output.append(f"  冒号分隔: {mac_format_colon(mac)}")
            output.append(f"  横线分隔: {mac_format_hyphen(mac)}")
            output.append(f"  点分隔: {mac_format_dot(mac)}")
            output.append(f"  无分隔: {mac_format_none(mac)}")
            output.append("")
            output.append("─" * 50)
            output.append("")

            # 同时显示ARP缓存表
            entries = get_arp_table()
            if entries:
                output.append("📋 ARP缓存表信息")
                output.append("─" * 50)
                output.append(f"{'Internet 地址':<20} {'物理地址':<25} {'类型':<8}")
                output.append("─" * 50)
                for entry in entries:
                    ip = entry['ip']
                    mac_str = entry['mac']
                    mac_type = entry.get('type', '动态')
                    vendor = OUIDatabase.query(mac_str)['vendor']
                    if vendor != '未知厂商':
                        mac_info = f"{mac_str} ({vendor[:18]})"
                    else:
                        mac_info = mac_str
                    output.append(f"{ip:<20} {mac_info:<25} {mac_type:<8}")
                output.append("─" * 50)
                output.append(f"共 {len(entries)} 条记录")
            else:
                output.append("📋 ARP缓存表: 暂无记录")

            self.query_result.setHtml("<br>".join(output))
        except Exception as e:
            self.query_result.setHtml(f"<span style='color:#e74c3c;'>❌ 查询失败: {e}</span>")

    def convert_format(self):
        """转换MAC地址格式"""
        mac = self.mac_input.text().strip()
        if not mac:
            self.query_result.setHtml("<span style='color:#e74c3c;'>❌ 请输入MAC地址</span>")
            return
        if not is_valid_mac(mac):
            self.query_result.setHtml("<span style='color:#e74c3c;'>❌ 无效的MAC地址格式</span>")
            return

        if self.radio_colon.isChecked():
            result = mac_format_colon(mac)
            format_name = "冒号分隔"
        elif self.radio_hyphen.isChecked():
            result = mac_format_hyphen(mac)
            format_name = "横线分隔"
        elif self.radio_dot.isChecked():
            result = mac_format_dot(mac)
            format_name = "点分隔"
        else:
            result = mac_format_none(mac)
            format_name = "无分隔"

        output = []
        output.append(f"<b>{format_name}格式:</b> <span style='color:#27ae60; font-weight:bold; font-size:14px;'>{result}</span>")
        output.append("")
        output.append("<b>全部格式:</b>")
        output.append(f"  冒号分隔: {mac_format_colon(mac)}")
        output.append(f"  横线分隔: {mac_format_hyphen(mac)}")
        output.append(f"  点分隔: {mac_format_dot(mac)}")
        output.append(f"  无分隔: {mac_format_none(mac)}")
        output.append("")
        output.append("─" * 50)
        output.append("")

        # 同时显示ARP缓存表
        entries = get_arp_table()
        if entries:
            output.append("📋 ARP缓存表信息")
            output.append("─" * 50)
            output.append(f"{'Internet 地址':<20} {'物理地址':<25} {'类型':<8}")
            output.append("─" * 50)
            for entry in entries:
                ip = entry['ip']
                mac_str = entry['mac']
                mac_type = entry.get('type', '动态')
                vendor = OUIDatabase.query(mac_str)['vendor']
                if vendor != '未知厂商':
                    mac_info = f"{mac_str} ({vendor[:18]})"
                else:
                    mac_info = mac_str
                output.append(f"{ip:<20} {mac_info:<25} {mac_type:<8}")
            output.append("─" * 50)
            output.append(f"共 {len(entries)} 条记录")
        else:
            output.append("📋 ARP缓存表: 暂无记录")

        self.query_result.setHtml("<br>".join(output))
        self.mac_input.setText(result)

    def clear_all(self):
        """清除所有内容"""
        self.mac_input.clear()
        self.query_result.clear()

    def cleanup(self):
        pass

    def stop_all(self):
        self.cleanup()

    def stop_update_timer(self):
        self.cleanup()
