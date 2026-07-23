"""路由表页面 - 查看/添加/删除系统路由"""
import subprocess
import platform
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt

from app.core.logger import Logger

logger = Logger("RouteTable")


def get_route_table():
    """获取系统路由表"""
    routes = []
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['route', 'print'], capture_output=True, text=True, errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
            lines = (result.stdout or '').split('\n')

            ipv4_section = False
            header_skipped = False

            for line in lines:
                line = line.strip()
                if 'IPv4 路由表' in line or 'IPv4 Route Table' in line:
                    ipv4_section = True
                    header_skipped = False
                    continue
                if 'IPv6 路由表' in line or 'IPv6 Route Table' in line:
                    break
                if not ipv4_section:
                    continue
                if not line or line.startswith('===') or line.startswith('---'):
                    continue
                # 跳过表头
                if '网络目标' in line or 'Network Destination' in line:
                    header_skipped = True
                    continue
                if not header_skipped:
                    continue

                parts = re.split(r'\s+', line)
                if len(parts) >= 5:
                    routes.append({
                        'destination': parts[0],
                        'mask': parts[1],
                        'gateway': parts[2],
                        'interface': parts[3],
                        'metric': parts[4],
                    })
        else:
            # Linux/Mac
            result = subprocess.run(['ip', 'route'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in (result.stdout or '').split('\n'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if 'via' in parts and 'dev' in parts:
                    destination = parts[0]
                    gateway = parts[parts.index('via') + 1]
                    interface = parts[parts.index('dev') + 1]
                    metric = parts[parts.index('metric') + 1] if 'metric' in parts else '0'
                    mask = '255.255.255.0'
                    routes.append({
                        'destination': destination,
                        'mask': mask,
                        'gateway': gateway,
                        'interface': interface,
                        'metric': metric,
                    })
    except Exception as e:
        logger.error(f"获取路由表失败: {e}")
    return routes


def add_route_network(dest, mask, gateway):
    """添加路由"""
    try:
        if platform.system() == 'Windows':
            cmd = ['route', 'add', dest, 'mask', mask, gateway]
        else:
            cmd = ['sudo', 'ip', 'route', 'add', f"{dest}/{mask}", 'via', gateway]
        result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, "路由添加成功"
        else:
            return False, result.stderr or "未知错误"
    except Exception as e:
        return False, str(e)


def delete_route_network(dest, mask, gateway):
    """删除路由"""
    try:
        if platform.system() == 'Windows':
            cmd = ['route', 'delete', dest, 'mask', mask, gateway]
        else:
            cmd = ['sudo', 'ip', 'route', 'del', f"{dest}/{mask}", 'via', gateway]
        result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore', creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, "路由删除成功"
        else:
            return False, result.stderr or "未知错误"
    except Exception as e:
        return False, str(e)


class RouteTablePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # 路由操作区
        op_frame = QFrame()
        op_frame.setStyleSheet("""
            QFrame { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        op_layout = QVBoxLayout(op_frame)
        op_layout.setContentsMargins(15, 12, 15, 12)
        op_layout.setSpacing(10)

        title = QLabel("⚙ 路由操作")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        op_layout.addWidget(title)

        # 查看路由表按钮
        self.view_btn = QPushButton("🔍 查看路由表")
        self.view_btn.setStyleSheet("background-color: #00bcd4; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        self.view_btn.clicked.connect(self.load_route_table)
        op_layout.addWidget(self.view_btn)

        # 添加/删除路由输入区
        form_layout = QHBoxLayout()
        form_layout.setSpacing(10)

        form_layout.addWidget(QLabel("目标网络:"))
        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText("192.168.10.0")
        form_layout.addWidget(self.dest_input)

        form_layout.addWidget(QLabel("掩码:"))
        self.mask_input = QLineEdit()
        self.mask_input.setPlaceholderText("255.255.255.0")
        form_layout.addWidget(self.mask_input)

        form_layout.addWidget(QLabel("网关:"))
        self.gateway_input = QLineEdit()
        self.gateway_input.setPlaceholderText("192.168.1.1")
        form_layout.addWidget(self.gateway_input)

        self.add_btn = QPushButton("➕ 添加路由")
        self.add_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        self.add_btn.clicked.connect(self.add_route)
        form_layout.addWidget(self.add_btn)

        self.del_btn = QPushButton("➖ 删除路由")
        self.del_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; padding: 8px 16px; border-radius: 3px;")
        self.del_btn.clicked.connect(self.delete_route)
        form_layout.addWidget(self.del_btn)

        op_layout.addLayout(form_layout)
        main_layout.addWidget(op_frame)

        # 路由表显示区
        table_frame = QFrame()
        table_frame.setStyleSheet("""
            QFrame { background-color: white; border: 1px solid #e0e0e0; border-radius: 5px; }
        """)
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(15, 12, 15, 12)
        table_layout.setSpacing(10)

        table_title = QLabel("📋 路由表")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00bcd4;")
        table_layout.addWidget(table_title)

        self.route_table = QTableWidget()
        self.route_table.setColumnCount(5)
        self.route_table.setHorizontalHeaderLabels(["网络目标", "网络掩码", "网关", "接口", "跃点数"])
        self.route_table.setAlternatingRowColors(True)
        self.route_table.setStyleSheet("""
            QTableWidget { font-size: 12px; }
            QHeaderView::section { background-color: #f0f0f0; padding: 6px; font-weight: bold; }
            QTableWidget::item { padding: 4px; }
        """)
        header = self.route_table.horizontalHeader()
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        # 点击表格填充输入框
        self.route_table.itemClicked.connect(self.on_table_item_clicked)

        table_layout.addWidget(self.route_table)
        main_layout.addWidget(table_frame, 1)

    def load_route_table(self):
        """加载并显示路由表"""
        routes = get_route_table()
        self.route_table.setRowCount(len(routes))

        for i, route in enumerate(routes):
            self.route_table.setItem(i, 0, QTableWidgetItem(route['destination']))
            self.route_table.setItem(i, 1, QTableWidgetItem(route['mask']))
            self.route_table.setItem(i, 2, QTableWidgetItem(route['gateway']))
            self.route_table.setItem(i, 3, QTableWidgetItem(route['interface']))
            self.route_table.setItem(i, 4, QTableWidgetItem(route['metric']))

        logger.info(f"路由表加载完成: 共 {len(routes)} 条")

    def on_table_item_clicked(self, item):
        """点击路由表行填充输入框"""
        row = item.row()
        self.dest_input.setText(self.route_table.item(row, 0).text())
        self.mask_input.setText(self.route_table.item(row, 1).text())
        self.gateway_input.setText(self.route_table.item(row, 2).text())

    def add_route(self):
        """添加路由"""
        dest = self.dest_input.text().strip()
        mask = self.mask_input.text().strip()
        gateway = self.gateway_input.text().strip()

        if not all([dest, mask, gateway]):
            QMessageBox.warning(self, "提示", "请填写完整的路由信息")
            return

        success, msg = add_route_network(dest, mask, gateway)
        if success:
            QMessageBox.information(self, "成功", msg)
            self.load_route_table()
        else:
            QMessageBox.critical(self, "失败", f"添加路由失败:\n{msg}\n\n提示: 修改路由表通常需要管理员权限")

    def delete_route(self):
        """删除路由"""
        dest = self.dest_input.text().strip()
        mask = self.mask_input.text().strip()
        gateway = self.gateway_input.text().strip()

        if not all([dest, mask, gateway]):
            QMessageBox.warning(self, "提示", "请填写完整的路由信息")
            return

        reply = QMessageBox.question(self, "确认", f"确定要删除路由 {dest}/{mask} via {gateway} 吗？")
        if reply != QMessageBox.Yes:
            return

        success, msg = delete_route_network(dest, mask, gateway)
        if success:
            QMessageBox.information(self, "成功", msg)
            self.load_route_table()
        else:
            QMessageBox.critical(self, "失败", f"删除路由失败:\n{msg}\n\n提示: 修改路由表通常需要管理员权限")

    def cleanup(self):
        pass

    def stop_all(self):
        self.cleanup()

    def stop_update_timer(self):
        self.cleanup()
