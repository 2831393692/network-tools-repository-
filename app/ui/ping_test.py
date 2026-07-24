import subprocess
import threading
import time
import re
import socket
from PySide6.QtCore import Signal
import ipaddress
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSpinBox, QTabWidget, QComboBox, QTableWidget,
    QTableWidgetItem, QPlainTextEdit, QFileDialog,
    QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor


class PingWorker(QObject):
    log_signal = Signal(str)
    stats_signal = Signal(dict)
    finished_signal = Signal()
    
    def __init__(self):
        super().__init__()
        self.is_running = False
    
    def emit_log(self, text):
        self.log_signal.emit(text)
    
    def emit_stats(self, stats):
        self.stats_signal.emit(stats)
    
    def emit_finished(self):
        self.finished_signal.emit()


class PingTestPage(QWidget):
    subnet_cell_update = Signal(int, bool)
    subnet_info_update = Signal(str)
    batch_row_signal = Signal(int, str, str, int, int, int, str, str)
    batch_status_signal = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        
        self.worker = PingWorker()
        self.worker.log_signal.connect(self.append_log)
        self.worker.stats_signal.connect(self.update_stats)
        self.worker.finished_signal.connect(self.on_finished)
        
        self.subnet_cell_update.connect(self.update_subnet_cell)
        self.subnet_info_update.connect(self.update_subnet_info_label)
        self.batch_row_signal.connect(self.add_batch_row)
        self.batch_status_signal.connect(self.update_batch_status_label)
        
        self.thread = None
        self.stats = {'sent': 0, 'received': 0, 'lost': 0, 'loss_rate': 0}
        self.init_ui()
    
    def stop_update_timer(self):
        self.worker.is_running = False
        try:
            self.worker.log_signal.disconnect(self.append_log)
            self.worker.stats_signal.disconnect(self.update_stats)
            self.worker.finished_signal.disconnect(self.on_finished)
        except:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
    
    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)
    
    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f5f5f5;
                color: #555;
                padding: 8px 20px;
                border: 1px solid #e0e0e0;
                border-bottom: none;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background-color: #00bcd4;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #4dd0e1;
                color: white;
            }
        """)
        
        self.tabs.addTab(self.create_single_tab(), "💡  单个 Ping")
        self.tabs.addTab(self.create_continuous_tab(), "🔁  持续Ping")
        self.tabs.addTab(self.create_batch_tab(), "📋  批量Ping")
        self.tabs.addTab(self.create_subnet_tab(), "🌐  网段Ping")
        self.tabs.addTab(self.create_tcp_tab(), "💡  TCP Ping")
        
        layout.addWidget(self.tabs)
    
    def create_title(self, text, color="#3498db"):
        label = QLabel(text)
        label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px; padding: 4px 0;")
        return label
    
    def create_status_label(self):
        label = QLabel("就绪 | 已发送: 0 | 接收: 0 | 丢失: 0 | 丢包率: 0%")
        label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-size: 11px;
                padding: 4px;
                background-color: #ecf0f1;
                border-radius: 3px;
                font-family: "Microsoft YaHei";
            }
        """)
        return label
    
    def create_single_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(self.create_title("⚙ Ping 参数配置"))
        
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        grid = QGridLayout(config_frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(10)
        
        target_label = QLabel("🎯 目标主机:")
        target_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(target_label, 0, 0)
        
        self.single_target = QComboBox()
        self.single_target.setEditable(True)
        self.single_target.addItems(["223.5.5.5", "www.baidu.com", "127.0.0.1", "8.8.8.8"])
        self.single_target.setCurrentText("223.5.5.5")
        self.single_target.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.single_target, 0, 1, 1, 2)
        
        count_label = QLabel("🔢 测试次数:")
        count_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(count_label, 0, 3)
        
        self.single_count = QSpinBox()
        self.single_count.setRange(1, 10000)
        self.single_count.setValue(4)
        grid.addWidget(self.single_count, 0, 4)
        
        size_label = QLabel("📦 数据包大小:")
        size_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(size_label, 1, 0)
        
        self.single_size = QSpinBox()
        self.single_size.setRange(1, 65500)
        self.single_size.setValue(32)
        grid.addWidget(self.single_size, 1, 1)
        
        byte_label = QLabel("字节")
        byte_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(byte_label, 1, 2)
        
        quick_layout = QHBoxLayout()
        quick_layout.addStretch()
        quick_layout.addWidget(QLabel("快速选择:"))
        for size in [32, 1024, 4096, 8192]:
            btn = QPushButton(f"{size}B" if size < 1024 else f"{size//1024}KB")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 5px 12px;
                    font-size: 11px;
                    border-radius: 3px;
                }
                QPushButton:hover { background-color: #f5f5f5; }
            """)
            btn.clicked.connect(lambda checked, s=size: self.single_size.setValue(s))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        grid.addLayout(quick_layout, 1, 3, 1, 2)
        
        layout.addWidget(config_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.single_start_btn = QPushButton("🚀 开始Ping")
        self.single_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.single_start_btn.setCursor(Qt.PointingHandCursor)
        self.single_start_btn.clicked.connect(self.start_single_ping)
        btn_layout.addWidget(self.single_start_btn)
        
        self.single_stop_btn = QPushButton("⏹ 停止")
        self.single_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        self.single_stop_btn.setEnabled(False)
        self.single_stop_btn.setCursor(Qt.PointingHandCursor)
        self.single_stop_btn.clicked.connect(self.stop_ping)
        btn_layout.addWidget(self.single_stop_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        result_title = QLabel("📊 Ping测试结果")
        result_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(result_title)
        
        self.single_result = QPlainTextEdit()
        self.single_result.setReadOnly(True)
        self.single_result.setStyleSheet("""
            QPlainTextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.single_result, 1)
        
        self.single_status = self.create_status_label()
        layout.addWidget(self.single_status)
        
        return widget
    
    def create_continuous_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(self.create_title("⚙ 持续Ping配置"))
        
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        grid = QGridLayout(config_frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(10)
        
        target_label = QLabel("🎯 目标主机:")
        target_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(target_label, 0, 0)
        
        self.cont_target = QComboBox()
        self.cont_target.setEditable(True)
        self.cont_target.addItems(["223.5.5.5", "www.baidu.com", "8.8.8.8"])
        self.cont_target.setCurrentText("223.5.5.5")
        self.cont_target.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.cont_target, 0, 1, 1, 2)
        
        interval_label = QLabel("⏱ 间隔时间:")
        interval_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(interval_label, 0, 3)
        
        self.cont_interval = QSpinBox()
        self.cont_interval.setRange(1, 60)
        self.cont_interval.setValue(1)
        self.cont_interval
        grid.addWidget(self.cont_interval, 0, 4)
        
        sec_label = QLabel("秒")
        sec_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(sec_label, 0, 5)
        
        size_label = QLabel("📦 数据包大小:")
        size_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(size_label, 1, 0)
        
        self.cont_size = QSpinBox()
        self.cont_size.setRange(1, 65500)
        self.cont_size.setValue(32)
        self.cont_size
        grid.addWidget(self.cont_size, 1, 1)
        
        layout.addWidget(config_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cont_start_btn = QPushButton("🚀 开始持续Ping")
        self.cont_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.cont_start_btn.setCursor(Qt.PointingHandCursor)
        self.cont_start_btn.clicked.connect(self.start_continuous_ping)
        btn_layout.addWidget(self.cont_start_btn)
        
        self.cont_stop_btn = QPushButton("⏹ 停止")
        self.cont_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        self.cont_stop_btn.setEnabled(False)
        self.cont_stop_btn.setCursor(Qt.PointingHandCursor)
        self.cont_stop_btn.clicked.connect(self.stop_ping)
        btn_layout.addWidget(self.cont_stop_btn)
        
        self.cont_export_btn = QPushButton("📄 导出结果")
        self.cont_export_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        self.cont_export_btn.setCursor(Qt.PointingHandCursor)
        self.cont_export_btn.clicked.connect(lambda: self.export_results(self.cont_result, "持续Ping结果"))
        btn_layout.addWidget(self.cont_export_btn)
        
        self.cont_clear_btn = QPushButton("🗑 清空结果")
        self.cont_clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        self.cont_clear_btn.setCursor(Qt.PointingHandCursor)
        self.cont_clear_btn.clicked.connect(lambda: self.cont_result.clear())
        btn_layout.addWidget(self.cont_clear_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        result_title = QLabel("📊 持续Ping结果")
        result_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(result_title)
        
        self.cont_result = QPlainTextEdit()
        self.cont_result.setReadOnly(True)
        self.cont_result.setStyleSheet("""
            QPlainTextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.cont_result, 1)
        
        self.cont_status = self.create_status_label()
        layout.addWidget(self.cont_status)
        
        return widget
    
    def create_batch_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(self.create_title("📋 主机列表（每一行一个IP/域名）:"))
        
        content = QHBoxLayout()
        content.setSpacing(10)
        
        self.batch_list = QPlainTextEdit()
        self.batch_list.setPlainText("223.5.5.5\n8.8.8.8\n114.114.114.114\nbaidu.com")
        self.batch_list.setStyleSheet("""
            QPlainTextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 12px;
                padding: 8px;
            }
        """)
        content.addWidget(self.batch_list, 3)
        
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)
        
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("⏱ 超时(ms):"))
        self.batch_timeout = QSpinBox()
        self.batch_timeout.setRange(100, 10000)
        self.batch_timeout.setValue(1500)
        self.batch_timeout.setSingleStep(100)
        self.batch_timeout
        timeout_layout.addWidget(self.batch_timeout)
        right_layout.addLayout(timeout_layout)
        
        concurrent_layout = QHBoxLayout()
        concurrent_layout.addWidget(QLabel("⚡ 并发:"))
        self.batch_concurrent = QSpinBox()
        self.batch_concurrent.setRange(1, 500)
        self.batch_concurrent.setValue(100)
        self.batch_concurrent
        concurrent_layout.addWidget(self.batch_concurrent)
        right_layout.addLayout(concurrent_layout)
        
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("🔧 模式:"))
        self.batch_mode = QComboBox()
        self.batch_mode.addItems(["快速扫描", "完整检测"])
        self.batch_mode
        mode_layout.addWidget(self.batch_mode)
        right_layout.addLayout(mode_layout)
        
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("⏰ 间隔(s):"))
        self.batch_interval = QSpinBox()
        self.batch_interval.setRange(0, 60)
        self.batch_interval.setValue(5)
        self.batch_interval
        interval_layout.addWidget(self.batch_interval)
        right_layout.addLayout(interval_layout)
        
        batch_start_btn = QPushButton("🚀 开始")
        batch_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        batch_start_btn.setCursor(Qt.PointingHandCursor)
        batch_start_btn.clicked.connect(self.start_batch_ping)
        right_layout.addWidget(batch_start_btn)
        
        batch_stop_btn = QPushButton("⏹ 停止")
        batch_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        batch_stop_btn.setEnabled(False)
        batch_stop_btn.setCursor(Qt.PointingHandCursor)
        batch_stop_btn.clicked.connect(self.stop_ping)
        self.batch_stop_btn = batch_stop_btn
        right_layout.addWidget(batch_stop_btn)
        
        batch_export_btn = QPushButton("📄 导出")
        batch_export_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        batch_export_btn.setCursor(Qt.PointingHandCursor)
        batch_export_btn.clicked.connect(lambda: self.export_table(self.batch_table, "批量Ping结果"))
        right_layout.addWidget(batch_export_btn)
        
        batch_clear_btn = QPushButton("🗑 清空")
        batch_clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        batch_clear_btn.setCursor(Qt.PointingHandCursor)
        batch_clear_btn.clicked.connect(self.clear_batch_table)
        right_layout.addWidget(batch_clear_btn)
        
        right_layout.addStretch()
        content.addLayout(right_layout, 1)
        
        layout.addLayout(content, 3)
        
        result_title = QLabel("📊 实时Ping结果")
        result_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(result_title)
        
        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(8)
        self.batch_table.setHorizontalHeaderLabels(["#", "主机/IP", "状态", "延迟(ms)", "最小(ms)", "最大(ms)", "丢包率", "测试时间"])
        self.batch_table.horizontalHeader().setStretchLastSection(True)
        self.batch_table.setColumnWidth(0, 50)
        self.batch_table.setColumnWidth(1, 200)
        self.batch_table.setColumnWidth(2, 100)
        self.batch_table.setColumnWidth(3, 100)
        self.batch_table.setColumnWidth(4, 100)
        self.batch_table.setColumnWidth(5, 100)
        self.batch_table.setColumnWidth(6, 100)
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.setStyleSheet("""
            QTableWidget {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                gridline-color: #e0e0e0;
                font-family: "Microsoft YaHei";
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.batch_table, 2)
        
        self.batch_status = self.create_status_label()
        layout.addWidget(self.batch_status)
        
        return widget
    
    def create_subnet_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(self.create_title("⚙ 网段Ping参数"))
        
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        grid = QGridLayout(config_frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(10)
        
        iface_label = QLabel("🔌 选择网卡:")
        iface_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(iface_label, 0, 0)
        
        self.subnet_iface = QComboBox()
        self.subnet_iface.addItem("自动选择")
        self.refresh_subnet_iface()
        self.subnet_iface
        grid.addWidget(self.subnet_iface, 0, 1)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 1px solid #ccc;
                padding: 4px 8px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #f5f5f5; }
        """)
        refresh_btn.clicked.connect(self.refresh_subnet_iface)
        grid.addWidget(refresh_btn, 0, 2)
        
        subnet_label = QLabel("🌐 网段:")
        subnet_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(subnet_label, 1, 0)
        
        self.subnet_range = QComboBox()
        self.subnet_range.setEditable(True)
        self.subnet_range.addItems(["192.168.1.0/24", "192.168.0.0/24", "10.0.0.0/24", "172.16.0.0/24"])
        self.subnet_range.setCurrentText("192.168.1.0/24")
        self.subnet_range
        grid.addWidget(self.subnet_range, 1, 1)
        
        hint_label = QLabel("支持 /24~/32, 如 192.168.1.0/24, 192.168.1.192/26")
        hint_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(hint_label, 1, 2, 1, 2)
        
        timeout_label = QLabel("⏱ 超时:")
        timeout_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(timeout_label, 2, 0)
        
        self.subnet_timeout = QSpinBox()
        self.subnet_timeout.setRange(1, 60)
        self.subnet_timeout.setValue(5)
        self.subnet_timeout
        grid.addWidget(self.subnet_timeout, 2, 1)
        
        sec_label = QLabel("秒")
        sec_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(sec_label, 2, 2)
        
        size_label = QLabel("📦 包大小:")
        size_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(size_label, 3, 0)
        
        self.subnet_size = QSpinBox()
        self.subnet_size.setRange(1, 65500)
        self.subnet_size.setValue(32)
        self.subnet_size
        grid.addWidget(self.subnet_size, 3, 1)
        
        byte_label = QLabel("字节")
        byte_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(byte_label, 3, 2)
        
        thread_label = QLabel("⚡ 线程:")
        thread_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(thread_label, 4, 0)
        
        self.subnet_threads = QSpinBox()
        self.subnet_threads.setRange(1, 500)
        self.subnet_threads.setValue(50)
        self.subnet_threads
        grid.addWidget(self.subnet_threads, 4, 1)
        
        layout.addWidget(config_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        subnet_start_btn = QPushButton("🚀 开始扫描")
        subnet_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        subnet_start_btn.setCursor(Qt.PointingHandCursor)
        subnet_start_btn.clicked.connect(self.start_subnet_ping)
        btn_layout.addWidget(subnet_start_btn)
        
        subnet_stop_btn = QPushButton("⏹ 停止")
        subnet_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        subnet_stop_btn.setEnabled(False)
        subnet_stop_btn.setCursor(Qt.PointingHandCursor)
        subnet_stop_btn.clicked.connect(self.stop_ping)
        self.subnet_stop_btn = subnet_stop_btn
        btn_layout.addWidget(subnet_stop_btn)
        
        subnet_export_btn = QPushButton("📄 导出")
        subnet_export_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        subnet_export_btn.setCursor(Qt.PointingHandCursor)
        subnet_export_btn.clicked.connect(self.export_subnet_results)
        btn_layout.addWidget(subnet_export_btn)
        
        btn_layout.addStretch()
        
        legend_layout = QHBoxLayout()
        legend_layout.addStretch()
        legend_layout.addWidget(QLabel("⚪ 未测试"))
        legend_layout.addWidget(QLabel("🟢 在线"))
        legend_layout.addWidget(QLabel("🔴 离线"))
        legend_layout.addWidget(QLabel("🟡 测试中"))
        legend_layout.addStretch()
        
        grid_layout = QVBoxLayout()
        grid_layout.addLayout(btn_layout)
        grid_layout.addLayout(legend_layout)
        layout.addLayout(grid_layout)
        
        info_label = QLabel("就绪 | 总计: 0 | 已扫: 0 | 在线: 0 | 离线: 0 | 在线率: 0%")
        info_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-size: 11px;
                padding: 4px;
                background-color: #ecf0f1;
                border-radius: 3px;
                font-family: "Microsoft YaHei";
            }
        """)
        self.subnet_info = info_label
        layout.addWidget(info_label)
        
        result_title = QLabel("📊 IP地址状态网格 (1-255)")
        result_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(result_title)
        
        self.subnet_grid_layout = QGridLayout()
        self.subnet_grid_layout.setSpacing(2)
        
        grid_widget = QWidget()
        grid_widget.setLayout(self.subnet_grid_layout)
        grid_widget.setStyleSheet("background-color: white;")
        
        scroll = QWidget()
        scroll_layout = QVBoxLayout(scroll)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(grid_widget)
        layout.addWidget(scroll, 1)
        
        self.init_subnet_grid()
        
        return widget
    
    def update_subnet_cell(self, last_num, success):
        if last_num in self.subnet_cells:
            cell = self.subnet_cells[last_num]
            if success:
                cell.setStyleSheet("""
                    QLabel {
                        background-color: #27ae60;
                        border: 1px solid #229954;
                        border-radius: 3px;
                        font-size: 10px;
                        font-weight: bold;
                        color: white;
                    }
                """)
            else:
                cell.setStyleSheet("""
                    QLabel {
                        background-color: #c0392b;
                        border: 1px solid #a93226;
                        border-radius: 3px;
                        font-size: 10px;
                        font-weight: bold;
                        color: white;
                    }
                """)
    
    def update_subnet_info_label(self, text):
        if hasattr(self, 'subnet_info') and self.subnet_info:
            self.subnet_info.setText(text)
    
    def init_subnet_grid(self):
        for i in reversed(range(self.subnet_grid_layout.count())):
            item = self.subnet_grid_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
        
        self.subnet_cells = {}
        cols = 29
        for i in range(1, 256):
            row = (i - 1) // cols
            col = (i - 1) % cols
            
            cell = QLabel(str(i))
            cell.setFixedSize(45, 32)
            cell.setAlignment(Qt.AlignCenter)
            cell.setStyleSheet("""
                QLabel {
                    background-color: #ecf0f1;
                    border: 1px solid #bdc3c7;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                    color: #7f8c8d;
                }
            """)
            self.subnet_grid_layout.addWidget(cell, row, col)
            self.subnet_cells[i] = cell
    
    def update_batch_status_label(self, text):
        if hasattr(self, 'batch_status') and self.batch_status:
            self.batch_status.setText(text)
    
    def refresh_subnet_iface(self):
        current = self.subnet_iface.currentText()
        self.subnet_iface.clear()
        self.subnet_iface.addItem("自动选择")
        try:
            import psutil
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()
            for name, stat in stats.items():
                if stat.isup:
                    ip = ""
                    if name in addrs:
                        for addr in addrs[name]:
                            if addr.family == socket.AF_INET:
                                ip = addr.address
                                break
                    display = f"{name} ({ip})" if ip else name
                    self.subnet_iface.addItem(display)
        except:
            pass
        if current:
            idx = self.subnet_iface.findText(current)
            if idx >= 0:
                self.subnet_iface.setCurrentIndex(idx)
    
    def create_tcp_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(self.create_title("⚙ TCP Ping参数配置"))
        
        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        grid = QGridLayout(config_frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(10)
        
        target_label = QLabel("🎯 目标主机:")
        target_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(target_label, 0, 0)
        
        self.tcp_target = QComboBox()
        self.tcp_target.setEditable(True)
        self.tcp_target.addItems(["www.baidu.com", "192.168.1.1", "127.0.0.1"])
        self.tcp_target.setCurrentText("www.baidu.com")
        self.tcp_target.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        grid.addWidget(self.tcp_target, 0, 1, 1, 3)
        
        port_label = QLabel("🔌 目标端口:")
        port_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(port_label, 0, 4)
        
        self.tcp_port = QSpinBox()
        self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(80)
        self.tcp_port
        grid.addWidget(self.tcp_port, 0, 5)
        
        count_label = QLabel("🔢 测试次数:")
        count_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(count_label, 1, 0)
        
        self.tcp_count = QSpinBox()
        self.tcp_count.setRange(1, 10000)
        self.tcp_count.setValue(10)
        self.tcp_count
        grid.addWidget(self.tcp_count, 1, 1)
        
        timeout_label = QLabel("⏱ 超时时间:")
        timeout_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(timeout_label, 1, 2)
        
        self.tcp_timeout = QSpinBox()
        self.tcp_timeout.setRange(1, 30)
        self.tcp_timeout.setValue(3)
        self.tcp_timeout
        grid.addWidget(self.tcp_timeout, 1, 3)
        
        sec_label = QLabel("秒")
        sec_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(sec_label, 1, 4)
        
        quick_layout = QHBoxLayout()
        quick_layout.addStretch()
        quick_layout.addWidget(QLabel("快速端口:"))
        for label, port in [("HTTP:80", 80), ("HTTPS:443", 443), ("SSH:22", 22), ("RDP:3389", 3389), ("MySQL:3306", 3306), ("Redis:6379", 6379)]:
            btn = QPushButton(label)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 5px 12px;
                    font-size: 11px;
                    border-radius: 3px;
                }
                QPushButton:hover { background-color: #f5f5f5; }
            """)
            btn.clicked.connect(lambda checked, p=port: self.tcp_port.setValue(p))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        
        quick_outer = QHBoxLayout()
        quick_outer.addLayout(quick_layout)
        grid.addLayout(quick_outer, 2, 0, 1, 6)
        
        layout.addWidget(config_frame)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.tcp_start_btn = QPushButton("🚀 开始TCP Ping")
        self.tcp_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.tcp_start_btn.setCursor(Qt.PointingHandCursor)
        self.tcp_start_btn.clicked.connect(self.start_tcp_ping)
        btn_layout.addWidget(self.tcp_start_btn)
        
        self.tcp_stop_btn = QPushButton("⏹ 停止")
        self.tcp_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        self.tcp_stop_btn.setEnabled(False)
        self.tcp_stop_btn.setCursor(Qt.PointingHandCursor)
        self.tcp_stop_btn.clicked.connect(self.stop_ping)
        btn_layout.addWidget(self.tcp_stop_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        result_title = QLabel("📊 TCP Ping测试结果")
        result_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(result_title)
        
        self.tcp_result = QPlainTextEdit()
        self.tcp_result.setReadOnly(True)
        self.tcp_result.setStyleSheet("""
            QPlainTextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.tcp_result, 1)
        
        self.tcp_status = self.create_status_label()
        layout.addWidget(self.tcp_status)
        
        return widget
    
    def append_log(self, text):
        current_tab = self.tabs.currentIndex()
        if current_tab == 0:
            self.single_result.appendPlainText(text)
        elif current_tab == 1:
            self.cont_result.appendPlainText(text)
        elif current_tab == 4:
            self.tcp_result.appendPlainText(text)
    
    def update_stats(self, stats):
        text = f"就绪 | 已发送: {stats['sent']} | 成功: {stats['received']} | 失败: {stats['lost']} | 成功率: {stats.get('loss_rate', 0)}%"
        current_tab = self.tabs.currentIndex()
        if current_tab == 0:
            self.single_status.setText(text)
        elif current_tab == 1:
            self.cont_status.setText(text)
        elif current_tab == 4:
            self.tcp_status.setText(text)
    
    def on_finished(self):
        self.single_start_btn.setEnabled(True)
        self.single_stop_btn.setEnabled(False)
        self.cont_start_btn.setEnabled(True)
        self.cont_stop_btn.setEnabled(False)
        self.tcp_start_btn.setEnabled(True)
        self.tcp_stop_btn.setEnabled(False)
        if hasattr(self, 'batch_stop_btn'):
            self.batch_stop_btn.setEnabled(False)
        if hasattr(self, 'subnet_stop_btn'):
            self.subnet_stop_btn.setEnabled(True)
        self.worker.is_running = False
    
    @staticmethod
    def _parse_ping_output(output):
        """
        解析 ping 命令的输出，兼容中英文 Windows 系统。

        参数:
            output: subprocess.run 获取的 stdout 字符串

        返回:
            (success, latency_ms, ttl, reason)
            - success: bool，是否 ping 通
            - latency_ms: int，延迟（毫秒）；失败时为 0
            - ttl: int，TTL值；失败时为 0
            - reason: str，失败原因（成功时为空串）
        """
        if not output:
            return False, 0, 0, "无输出"

        latency = 0
        ttl = 0

        latency_match = re.search(r"(?:时间|time)\s*[<=]?\s*(\d+)\s*ms", output, re.IGNORECASE)
        ttl_match = re.search(r"(?:TTL|ttl)\s*=\s*(\d+)", output, re.IGNORECASE)

        if latency_match:
            latency = int(latency_match.group(1))
            if ttl_match:
                ttl = int(ttl_match.group(1))
            return True, latency, ttl, ""

        failure_markers = [
            "请求超时",
            "Request timed out",
            "无法访问目标主机",
            "Destination host unreachable",
            "传输失败",
            "transmit failed",
            "一般故障",
            "General failure",
            "Ping 请求找不到主机",
            "Ping request could not find host",
            "100% 丢失",
            "100% loss",
        ]
        for marker in failure_markers:
            if marker in output:
                return False, 0, 0, marker

        return False, 0, 0, "未知"

    def start_single_ping(self):
        if self.worker.is_running:
            return

        target = self.single_target.currentText().strip()
        if not target:
            QMessageBox.warning(self, "提示", "请输入目标主机")
            return

        count = self.single_count.value()
        size = self.single_size.value()
        
        self.worker.is_running = True
        self.single_start_btn.setEnabled(False)
        self.single_stop_btn.setEnabled(True)
        self.single_result.clear()
        self.stats = {'sent': 0, 'received': 0, 'lost': 0, 'loss_rate': 0}
        
        self.thread = threading.Thread(target=self.run_single_ping, args=(target, count, size))
        self.thread.start()
    
    def run_single_ping(self, target, count, size):
        self.worker.emit_log(f"正在 Ping {target} ({count}次, {size}字节):")
        self.worker.emit_log("")

        sent = 0
        received = 0
        lost = 0
        latencies = []

        for i in range(count):
            if not self.worker.is_running:
                break
            sent += 1
            cmd = f"ping -n 1 -w 2000 -l {size} {target}"
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                success, latency, ttl, reason = self._parse_ping_output(result.stdout)
                if success:
                    received += 1
                    latencies.append(latency)
                    self.worker.emit_log(f"来自 {target} 的回复: 字节={size} 时间={latency}ms TTL={ttl}")
                else:
                    lost += 1
                    if "timed out" in reason or "超时" in reason:
                        self.worker.emit_log("请求超时")
                    else:
                        self.worker.emit_log("无法访问目标主机")
            except subprocess.TimeoutExpired:
                lost += 1
                self.worker.emit_log("请求超时")
            except Exception as e:
                lost += 1
                self.worker.emit_log(f"错误: {e}")

            loss_rate = int((lost / sent) * 100) if sent > 0 else 0
            self.worker.emit_stats({
                'sent': sent, 'received': received, 'lost': lost, 'loss_rate': 100 - loss_rate
            })

            time.sleep(0.2)

        self.worker.emit_log("")
        self.worker.emit_log(f"{target} 的 Ping 统计信息:")
        self.worker.emit_log(f"    数据包: 已发送 = {sent}, 已接收 = {received}, 丢失 = {lost} ({(lost/sent*100 if sent else 0):.1f}% 丢失)")
        if latencies:
            self.worker.emit_log(f"    往返行程的估计时间(以毫秒为单位):")
            self.worker.emit_log(f"    最短 = {min(latencies)}ms, 最长 = {max(latencies)}ms, 平均 = {sum(latencies)//len(latencies)}ms")
        self.worker.emit_finished()
    
    def start_continuous_ping(self):
        if self.worker.is_running:
            return
        
        target = self.cont_target.currentText().strip()
        if not target:
            QMessageBox.warning(self, "提示", "请输入目标主机")
            return
        
        interval = self.cont_interval.value()
        size = self.cont_size.value()
        
        self.worker.is_running = True
        self.cont_start_btn.setEnabled(False)
        self.cont_stop_btn.setEnabled(True)
        self.cont_result.clear()
        self.stats = {'sent': 0, 'received': 0, 'lost': 0, 'loss_rate': 0}
        
        self.thread = threading.Thread(target=self.run_continuous_ping, args=(target, interval, size))
        self.thread.start()
    
    def run_continuous_ping(self, target, interval, size):
        self.worker.emit_log(f"正在持续 Ping {target} (间隔{interval}秒, {size}字节):")
        self.worker.emit_log("按 停止 按钮结束")
        self.worker.emit_log("")

        sent = 0
        received = 0
        lost = 0

        while self.worker.is_running:
            sent += 1
            self.worker.emit_log(f"[{datetime.now().strftime('%H:%M:%S')}] 发送数据包 #{sent}...")
            cmd = f"ping -n 1 -w 2000 -l {size} {target}"
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                success, latency, ttl, reason = self._parse_ping_output(result.stdout)
                if success:
                    received += 1
                    self.worker.emit_log(f"  来自 {target} 的回复: 字节={size} 时间={latency}ms TTL={ttl}")
                else:
                    lost += 1
                    if "timed out" in reason or "超时" in reason:
                        self.worker.emit_log("  请求超时")
                    else:
                        self.worker.emit_log("  无法访问目标主机")
            except subprocess.TimeoutExpired:
                lost += 1
                self.worker.emit_log("  请求超时")
            except Exception:
                lost += 1
                self.worker.emit_log("  请求超时")

            loss_rate = int((lost / sent) * 100) if sent > 0 else 0
            self.worker.emit_stats({
                'sent': sent, 'received': received, 'lost': lost, 'loss_rate': 100 - loss_rate
            })

            for _ in range(interval * 10):
                if not self.worker.is_running:
                    break
                time.sleep(0.1)

        self.worker.emit_log("")
        self.worker.emit_log(f"持续Ping结束: 已发送 {sent}, 接收 {received}, 丢失 {lost}")
        self.worker.emit_finished()
    
    def start_batch_ping(self):
        if self.worker.is_running:
            return
        
        targets = [t.strip() for t in self.batch_list.toPlainText().split('\n') if t.strip()]
        if not targets:
            QMessageBox.warning(self, "提示", "请输入要测试的主机列表")
            return
        
        timeout = self.batch_timeout.value()
        concurrent = self.batch_concurrent.value()
        interval = self.batch_interval.value()
        mode = self.batch_mode.currentText()
        
        self.worker.is_running = True
        self.batch_stop_btn.setEnabled(True)
        self.batch_table.setRowCount(0)
        self.stats = {'sent': 0, 'received': 0, 'lost': 0, 'loss_rate': 0}
        self.batch_status.setText(f"就绪 | 总: 0 | 在线: 0 | 离线: 0 | 成功率: 0% | 平均延迟: -")
        
        self.thread = threading.Thread(target=self.run_batch_ping, args=(targets, timeout, concurrent, interval, mode))
        self.thread.start()
    
    def run_batch_ping(self, targets, timeout, concurrent, interval, mode):
        total = len(targets)
        completed = 0
        online = 0
        offline = 0
        total_latency = 0
        latency_count = 0
        avg_lat = 0
        
        self.batch_status_signal.emit(f"就绪 | 总: {total} | 在线: 0 | 离线: 0 | 成功率: 0% | 平均延迟: -")
        
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = {}
            for idx, target in enumerate(targets):
                if not self.worker.is_running:
                    break
                fut = executor.submit(self.ping_one_host, target, timeout)
                futures[fut] = (idx + 1, target)
            
            for future in as_completed(futures):
                if not self.worker.is_running:
                    break
                
                idx, target = futures[future]
                completed += 1
                
                try:
                    success, latency, ttl = future.result()
                    status = "在线" if success else "离线"
                    if success:
                        online += 1
                        total_latency += latency
                        latency_count += 1
                        avg_lat = total_latency / latency_count
                        loss_rate = 0
                    else:
                        offline += 1
                        avg_lat = total_latency / latency_count if latency_count > 0 else 0
                        loss_rate = 100
                    
                    self.batch_row_signal.emit(idx, target, status, latency, latency, latency, f"{loss_rate}%", datetime.now().strftime('%H:%M:%S'))
                except Exception as e:
                    offline += 1
                    self.batch_row_signal.emit(idx, target, "错误", 0, 0, 0, "100%", datetime.now().strftime('%H:%M:%S'))
                
                success_rate = (online / completed * 100) if completed > 0 else 0
                self.batch_status_signal.emit(
                    f"就绪 | 总: {total} | 在线: {online} | 离线: {offline} | 成功率: {success_rate:.1f}% | 平均延迟: {avg_lat:.1f}ms"
                )
                
                if interval > 0:
                    time.sleep(interval / concurrent)
        
        self.worker.emit_finished()
    
    def ping_one_host(self, host, timeout_ms):
        try:
            timeout_s = timeout_ms / 1000
            cmd = f"ping -n 1 -w {timeout_ms} {host}"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 2, creationflags=subprocess.CREATE_NO_WINDOW)
            success, latency, ttl, _ = self._parse_ping_output(result.stdout)
            if success:
                return True, latency, ttl
        except:
            pass
        return False, 0, 0
    
    def add_batch_row(self, idx, host, status, latency, min_lat, max_lat, loss_rate, time_str):
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        self.batch_table.setItem(row, 0, QTableWidgetItem(str(idx)))
        self.batch_table.setItem(row, 1, QTableWidgetItem(host))
        self.batch_table.setItem(row, 2, QTableWidgetItem(status))
        self.batch_table.setItem(row, 3, QTableWidgetItem(f"{latency}"))
        self.batch_table.setItem(row, 4, QTableWidgetItem(f"{min_lat}"))
        self.batch_table.setItem(row, 5, QTableWidgetItem(f"{max_lat}"))
        self.batch_table.setItem(row, 6, QTableWidgetItem(loss_rate))
        self.batch_table.setItem(row, 7, QTableWidgetItem(time_str))
        
        if status == "在线":
            self.batch_table.item(row, 2).setForeground(QColor("#27ae60"))
        else:
            self.batch_table.item(row, 2).setForeground(QColor("#e74c3c"))
    
    def clear_batch_table(self):
        self.batch_table.setRowCount(0)
        self.batch_status.setText("就绪 | 总: 0 | 在线: 0 | 离线: 0 | 成功率: 0% | 平均延迟: -")
    
    def start_subnet_ping(self):
        if self.worker.is_running:
            return
        
        subnet = self.subnet_range.currentText().strip()
        if not subnet:
            QMessageBox.warning(self, "提示", "请输入网段")
            return
        
        try:
            network = ipaddress.IPv4Network(subnet, strict=False)
            hosts = [str(ip) for ip in network.hosts()]
        except Exception as e:
            QMessageBox.warning(self, "提示", f"网段格式错误: {e}")
            return
        
        timeout = self.subnet_timeout.value()
        size = self.subnet_size.value()
        threads = self.subnet_threads.value()
        
        self.worker.is_running = True
        self.subnet_stop_btn.setEnabled(True)
        self.init_subnet_grid()
        self.subnet_info.setText(f"就绪 | 总计: {len(hosts)} | 已扫: 0 | 在线: 0 | 离线: 0 | 在线率: 0%")
        
        self.thread = threading.Thread(target=self.run_subnet_ping, args=(hosts, timeout, size, threads))
        self.thread.start()
    
    def run_subnet_ping(self, hosts, timeout, size, threads):
        total = len(hosts)
        completed = 0
        online = 0
        offline = 0

        def scan_host(host):
            try:
                last_num = int(host.split('.')[-1])
            except:
                return None, None, None

            try:
                cmd = f"ping -n 1 -w {timeout * 1000} -l {size} {host}"
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2, creationflags=subprocess.CREATE_NO_WINDOW)
                # 使用统一的解析函数，兼容中英文 Windows 系统
                success, _, _, _ = self._parse_ping_output(result.stdout)
                return host, last_num, success
            except:
                return host, last_num, False

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(scan_host, h) for h in hosts]

            for future in as_completed(futures):
                if not self.worker.is_running:
                    break

                host, last_num, success = future.result()
                completed += 1

                if last_num:
                    self.subnet_cell_update.emit(last_num, success)
                    if success:
                        online += 1
                    else:
                        offline += 1

                online_rate = (online / completed * 100) if completed > 0 else 0
                self.subnet_info_update.emit(
                    f"就绪 | 总计: {total} | 已扫: {completed} | 在线: {online} | 离线: {offline} | 在线率: {online_rate:.1f}%"
                )

        self.worker.emit_finished()
    
    def export_subnet_results(self):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "导出网段Ping结果", f"subnet_ping_{timestamp}.txt", "文本文件 (*.txt)"
            )
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"网段Ping扫描结果\n")
                    f.write(f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"网段: {self.subnet_range.currentText()}\n")
                    f.write(f"总计: {len(self.subnet_cells)} | 已扫: 已完成\n\n")
                    
                    online_hosts = []
                    for num, cell in self.subnet_cells.items():
                        style = cell.styleSheet()
                        if "#27ae60" in style:
                            online_hosts.append(num)
                    
                    f.write(f"在线主机 ({len(online_hosts)}个):\n")
                    base = '.'.join(self.subnet_range.currentText().split('/')[0].split('.')[:3])
                    for n in online_hosts:
                        f.write(f"  {base}.{n}\n")
                
                QMessageBox.information(self, "成功", f"结果已导出到: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
    
    def start_tcp_ping(self):
        if self.worker.is_running:
            return
        
        target = self.tcp_target.currentText().strip()
        port = self.tcp_port.value()
        count = self.tcp_count.value()
        timeout = self.tcp_timeout.value()
        
        if not target:
            QMessageBox.warning(self, "提示", "请输入目标主机")
            return
        
        self.worker.is_running = True
        self.tcp_start_btn.setEnabled(False)
        self.tcp_stop_btn.setEnabled(True)
        self.tcp_result.clear()
        self.stats = {'sent': 0, 'received': 0, 'lost': 0, 'loss_rate': 0}
        
        self.thread = threading.Thread(target=self.run_tcp_ping, args=(target, port, count, timeout))
        self.thread.start()
    
    def run_tcp_ping(self, target, port, count, timeout):
        self.worker.emit_log(f"正在 TCP Ping {target}:{port} ({count}次, 超时{timeout}秒):")
        self.worker.emit_log("")
        
        sent = 0
        received = 0
        lost = 0
        total_latency = 0
        
        for i in range(count):
            if not self.worker.is_running:
                break
            
            sent += 1
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                start = time.time()
                result = s.connect_ex((target, port))
                elapsed = (time.time() - start) * 1000
                s.close()
                
                if result == 0:
                    received += 1
                    total_latency += elapsed
                    self.worker.emit_log(f"[{datetime.now().strftime('%H:%M:%S')}] TCP #{sent}: 连接成功 {target}:{port} 延迟={elapsed:.1f}ms")
                else:
                    lost += 1
                    self.worker.emit_log(f"[{datetime.now().strftime('%H:%M:%S')}] TCP #{sent}: 连接失败 (错误码={result})")
            except socket.timeout:
                lost += 1
                self.worker.emit_log(f"[{datetime.now().strftime('%H:%M:%S')}] TCP #{sent}: 连接超时")
            except Exception as e:
                lost += 1
                self.worker.emit_log(f"[{datetime.now().strftime('%H:%M:%S')}] TCP #{sent}: 错误 - {e}")
            
            loss_rate = int((lost / sent) * 100) if sent > 0 else 0
            self.worker.emit_stats({
                'sent': sent, 'received': received, 'lost': lost, 'loss_rate': 100 - loss_rate
            })
            
            time.sleep(0.2)
        
        self.worker.emit_log("")
        if received > 0:
            avg = total_latency / received
            self.worker.emit_log(f"{target}:{port} 的 TCP Ping 统计:")
            self.worker.emit_log(f"    数据包: 已发送 = {sent}, 已接收 = {received}, 丢失 = {lost}")
            self.worker.emit_log(f"    平均延迟 = {avg:.1f}ms")
        else:
            self.worker.emit_log(f"{target}:{port} 不可达")
        
        self.worker.emit_finished()
    
    def stop_ping(self):
        if self.worker.is_running:
            self.worker.is_running = False
            if self.thread:
                self.thread.join(timeout=2)
            self.append_log("\n⏹ 用户停止了测试")
            self.on_finished()
    
    def export_results(self, text_widget, default_name):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, f"导出{default_name}", f"{default_name}_{timestamp}.txt", "文本文件 (*.txt)"
            )
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(text_widget.toPlainText())
                QMessageBox.information(self, "成功", f"结果已导出到: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
    
    def export_table(self, table_widget, default_name):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, f"导出{default_name}", f"{default_name}_{timestamp}.csv", "CSV文件 (*.csv)"
            )
            if filename:
                with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
                    headers = []
                    for col in range(table_widget.columnCount()):
                        headers.append(table_widget.horizontalHeaderItem(col).text())
                    f.write(','.join(headers) + '\n')
                    
                    for row in range(table_widget.rowCount()):
                        row_data = []
                        for col in range(table_widget.columnCount()):
                            item = table_widget.item(row, col)
                            row_data.append(item.text() if item else '')
                        f.write(','.join(row_data) + '\n')
                QMessageBox.information(self, "成功", f"结果已导出到: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
