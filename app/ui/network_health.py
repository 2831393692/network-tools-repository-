import subprocess
import threading
import socket
import time
import re
import psutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QSpinBox, QComboBox, QTabWidget, QProgressBar,
    QTableWidget, QTableWidgetItem, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QFont


class HealthCheckWorker(QObject):
    log_signal = Signal(str)
    status_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(dict)
    
    def __init__(self):
        super().__init__()
        self.is_running = False
    
    def emit_log(self, text):
        self.log_signal.emit(text)
    
    def emit_status(self, text):
        self.status_signal.emit(text)
    
    def emit_progress(self, value):
        self.progress_signal.emit(value)
    
    def emit_finished(self, results):
        self.finished_signal.emit(results)


class NetworkHealthPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.basic_thread = None
        self.basic_worker = HealthCheckWorker()
        self.basic_worker.log_signal.connect(self.append_basic_log)
        self.basic_worker.status_signal.connect(self.update_basic_status)
        self.basic_worker.progress_signal.connect(self.update_basic_progress)
        self.basic_worker.finished_signal.connect(self.on_basic_finished)
        
        self.loop_thread = None
        self.loop_worker = HealthCheckWorker()
        self.loop_worker.log_signal.connect(self.append_loop_log)
        self.loop_worker.status_signal.connect(self.update_loop_status)
        self.loop_worker.progress_signal.connect(self.update_loop_progress)
        self.loop_worker.finished_signal.connect(self.on_loop_finished)
        
        self.loop_monitor_thread = None
        self.loop_monitor_running = False
        
        self.init_ui()
    
    def stop_update_timer(self):
        self.basic_worker.is_running = False
        self.loop_worker.is_running = False
        self.loop_monitor_running = False
        
        try:
            self.basic_worker.log_signal.disconnect(self.append_basic_log)
            self.basic_worker.status_signal.disconnect(self.update_basic_status)
            self.basic_worker.progress_signal.disconnect(self.update_basic_progress)
            self.basic_worker.finished_signal.disconnect(self.on_basic_finished)
        except:
            pass
        
        try:
            self.loop_worker.log_signal.disconnect(self.append_loop_log)
            self.loop_worker.status_signal.disconnect(self.update_loop_status)
            self.loop_worker.progress_signal.disconnect(self.update_loop_progress)
            self.loop_worker.finished_signal.disconnect(self.on_loop_finished)
        except:
            pass
        
        if self.basic_thread and self.basic_thread.is_alive():
            self.basic_thread.join(timeout=1)
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=1)
        if self.loop_monitor_thread and self.loop_monitor_thread.is_alive():
            self.loop_monitor_thread.join(timeout=1)
    
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
        
        self.basic_tab = self.create_basic_tab()
        self.tabs.addTab(self.basic_tab, "🩺  基本健康检查")
        
        self.loop_tab = self.create_loop_tab()
        self.tabs.addTab(self.loop_tab, "🔗  单独环路检测")
        
        layout.addWidget(self.tabs)
    
    def create_basic_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        title = QLabel("🩺 网络健康检查")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.basic_start_btn = QPushButton("💬  开始健康检查")
        self.basic_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.basic_start_btn.setCursor(Qt.PointingHandCursor)
        self.basic_start_btn.clicked.connect(self.start_basic_check)
        button_layout.addWidget(self.basic_start_btn)
        
        self.basic_clear_btn = QPushButton("🗑  清空结果")
        self.basic_clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.basic_clear_btn.setCursor(Qt.PointingHandCursor)
        self.basic_clear_btn.clicked.connect(self.clear_basic_results)
        button_layout.addWidget(self.basic_clear_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        status_layout = QHBoxLayout()
        self.basic_status_label = QLabel("准备就绪，点击开始检查...")
        self.basic_status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 12px;
                padding: 8px;
                background-color: #ecf0f1;
                border-radius: 3px;
            }
        """)
        self.basic_status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.basic_status_label)
        layout.addLayout(status_layout)
        
        result_title = QLabel("📋 检测结果")
        result_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        result_title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(result_title)
        
        self.basic_result_frame = QFrame()
        self.basic_result_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        result_layout = QVBoxLayout(self.basic_result_frame)
        result_layout.setContentsMargins(20, 20, 20, 20)
        
        self.basic_banner = QLabel("⏳  网络健康检查工具")
        self.basic_banner.setAlignment(Qt.AlignCenter)
        self.basic_banner.setStyleSheet("""
            QLabel {
                color: white;
                background-color: #3498db;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
            }
        """)
        result_layout.addWidget(self.basic_banner)
        
        self.basic_result_text = QTextEdit()
        self.basic_result_text.setReadOnly(True)
        self.basic_result_text.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: none;
                font-family: "Microsoft YaHei";
                font-size: 13px;
                color: #2c3e50;
                padding: 10px;
            }
        """)
        self.set_basic_initial_content()
        result_layout.addWidget(self.basic_result_text)
        
        layout.addWidget(self.basic_result_frame, 1)
        
        return widget
    
    def set_basic_initial_content(self):
        html = """
        <div style="padding: 10px; line-height: 1.8;">
            <p>👋 欢迎使用网络健康检查功能！</p>
            <br>
            <p><b>本工具将自动检测以下项目：</b></p>
            <p>✓ 网卡状态检测</p>
            <p>✓ 网关连通性测试</p>
            <p>✓ DNS 解析速度测试</p>
            <p>✓ 外网连接测试</p>
            <p>✓ 网络延迟评估</p>
            <p>✓ 网络速度测试</p>
            <p>✓ 网络环路检测（基础）</p>
            <br>
            <p>检测完成后，系统将给出综合评分和优化建议。</p>
            <br>
            <p style="color: #7f8c8d;">点击上方"<b>开始健康检查</b>"按钮开始检测...</p>
        </div>
        """
        self.basic_result_text.setHtml(html)
    
    def create_loop_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        title = QLabel("🔗 网络环路检测")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title)
        
        select_layout = QHBoxLayout()
        select_layout.setSpacing(10)
        
        select_label = QLabel("🌐 选择网卡:")
        select_label.setStyleSheet("color: #555; font-size: 12px; font-weight: bold;")
        select_layout.addWidget(select_label)
        
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(300)
        self.iface_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        self.refresh_iface_list()
        select_layout.addWidget(self.iface_combo)
        
        select_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #555;
                border: 1px solid #ccc;
                padding: 6px 15px;
                font-size: 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_iface_list)
        select_layout.addWidget(refresh_btn)
        
        layout.addLayout(select_layout)
        
        hint = QLabel("💡 选择要检测的网卡，或选择'全部网卡'检测所有活动网卡")
        hint.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(hint)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.loop_start_btn = QPushButton("🔗 开始环路检测")
        self.loop_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.loop_start_btn.setCursor(Qt.PointingHandCursor)
        self.loop_start_btn.clicked.connect(self.start_loop_check)
        button_layout.addWidget(self.loop_start_btn)
        
        self.loop_clear_btn = QPushButton("🗑 清空结果")
        self.loop_clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.loop_clear_btn.setCursor(Qt.PointingHandCursor)
        self.loop_clear_btn.clicked.connect(self.clear_loop_results)
        button_layout.addWidget(self.loop_clear_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        status_layout = QHBoxLayout()
        self.loop_status_label = QLabel("准备就绪，点击开始环路检测...")
        self.loop_status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 12px;
                padding: 8px;
                background-color: #ecf0f1;
                border-radius: 3px;
            }
        """)
        self.loop_status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.loop_status_label)
        layout.addLayout(status_layout)
        
        result_title = QLabel("📋 环路检测结果")
        result_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        result_title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(result_title)
        
        self.loop_result_frame = QFrame()
        self.loop_result_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        result_layout = QVBoxLayout(self.loop_result_frame)
        result_layout.setContentsMargins(20, 20, 20, 20)
        
        self.loop_banner = QLabel("⏳  网络环路检测工具")
        self.loop_banner.setAlignment(Qt.AlignCenter)
        self.loop_banner.setStyleSheet("""
            QLabel {
                color: white;
                background-color: #3498db;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
            }
        """)
        result_layout.addWidget(self.loop_banner)
        
        self.loop_result_text = QTextEdit()
        self.loop_result_text.setReadOnly(True)
        self.loop_result_text.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: none;
                font-family: "Microsoft YaHei";
                font-size: 13px;
                color: #2c3e50;
                padding: 10px;
            }
        """)
        self.set_loop_initial_content()
        result_layout.addWidget(self.loop_result_text)
        
        layout.addWidget(self.loop_result_frame, 1)
        
        return widget
    
    def set_loop_initial_content(self):
        html = """
        <div style="padding: 10px; line-height: 1.8;">
            <p>👋 欢迎使用网络环路检测功能！</p>
            <br>
            <p><b>本工具使用以下方法检测网络环路：</b></p>
            <p>💡 <b>以太网帧检测（底层检测）</b></p>
            <p style="padding-left: 20px;">• 通过监控非单播流量变化进行底层检测</p>
            <p style="padding-left: 20px;">• 检测网络环路最准确的方法</p>
            <br>
            <hr style="border: 1px solid #e0e0e0;">
            <br>
            <p>💡 <b>什么是网络环路？</b></p>
            <p>网络环路是指网络中存在多条路径形成闭环，导致数据包在网络中无限循环，造成网络拥塞甚至瘫痪。</p>
            <br>
            <p><b>常见原因：</b></p>
            <p style="padding-left: 20px;">• 交换机端口错误连接</p>
            <p style="padding-left: 20px;">• 网线误接形成环路</p>
            <p style="padding-left: 20px;">• 未启用 STP 协议</p>
            <br>
            <p style="color: #7f8c8d;">点击上方"<b>开始环路检测</b>"按钮开始检测...</p>
        </div>
        """
        self.loop_result_text.setHtml(html)
    
    def refresh_iface_list(self):
        self.iface_combo.clear()
        self.iface_combo.addItem("全部网卡")
        
        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()
            for iface, stat in stats.items():
                if stat.isup:
                    ip = "无IP"
                    if iface in addrs:
                        for addr in addrs[iface]:
                            if addr.family == socket.AF_INET:
                                ip = addr.address
                                break
                    self.iface_combo.addItem(f"{iface} ({ip})")
        except Exception as e:
            self.iface_combo.addItem(f"获取网卡失败: {e}")
    
    def start_basic_check(self):
        if self.basic_worker.is_running:
            return
        
        self.basic_worker.is_running = True
        self.basic_start_btn.setEnabled(False)
        self.basic_status_label.setText("正在检测中...")
        self.basic_banner.setText("⏳  正在执行健康检查...")
        self.basic_banner.setStyleSheet("""
            QLabel {
                color: white;
                background-color: #f39c12;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
            }
        """)
        self.basic_result_text.clear()
        
        self.basic_thread = threading.Thread(target=self.run_basic_check, args=(self.basic_worker,))
        self.basic_thread.start()
    
    def clear_basic_results(self):
        self.basic_status_label.setText("准备就绪，点击开始检查...")
        self.set_basic_initial_content()
        self.basic_banner.setText("⏳  网络健康检查工具")
        self.basic_banner.setStyleSheet("""
            QLabel {
                color: white;
                background-color: #3498db;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
            }
        """)
    
    def append_basic_log(self, text):
        from PySide6.QtGui import QTextCursor
        self.basic_result_text.append(text)
        cursor = self.basic_result_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.basic_result_text.setTextCursor(cursor)
    
    def update_basic_status(self, text):
        self.basic_status_label.setText(text)
    
    def update_basic_progress(self, value):
        pass
    
    def on_basic_finished(self, results):
        self.basic_worker.is_running = False
        self.basic_start_btn.setEnabled(True)
        self.display_basic_results(results)
    
    def display_basic_results(self, results):
        score = results.get('score', 0)
        if score >= 80:
            color = "#2ecc71"
            level = "优秀"
        elif score >= 60:
            color = "#f39c12"
            level = "良好"
        else:
            color = "#e74c3c"
            level = "较差"
        
        self.basic_banner.setText(f"✅  健康检查完成 - 综合评分：{score}分 ({level})")
        self.basic_banner.setStyleSheet(f"""
            QLabel {{
                color: white;
                background-color: {color};
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
            }}
        """)
        
        html = "<div style='padding: 10px; line-height: 1.8;'>"
        html += "<h3>📊 详细检测结果</h3>"
        
        items = results.get('items', [])
        for item in items:
            icon = "✅" if item['status'] == 'ok' else "⚠️" if item['status'] == 'warning' else "❌"
            html += f"<p>{icon} <b>{item['name']}</b>: {item['message']}</p>"
        
        html += "<br><h3>💡 优化建议</h3>"
        suggestions = results.get('suggestions', [])
        if suggestions:
            for s in suggestions:
                html += f"<p>• {s}</p>"
        else:
            html += "<p>🎉 网络状态良好，无需特别优化！</p>"
        
        html += "</div>"
        self.basic_result_text.setHtml(html)
    
    def run_basic_check(self, worker):
        try:
            worker.emit_status("正在初始化检测...")
            worker.emit_log("🚀 开始网络健康检查\n")
            
            results = {'items': [], 'suggestions': [], 'score': 100}
            
            worker.emit_log("=" * 50)
            worker.emit_log("【1/7】网卡状态检测")
            worker.emit_log("=" * 50)
            item = self.check_nic_status()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            worker.emit_log("=" * 50)
            worker.emit_log("【2/7】网关连通性测试")
            worker.emit_log("=" * 50)
            item = self.check_gateway()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            worker.emit_log("=" * 50)
            worker.emit_log("【3/7】DNS解析速度测试")
            worker.emit_log("=" * 50)
            item = self.check_dns()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            worker.emit_log("=" * 50)
            worker.emit_log("【4/7】外网连接测试")
            worker.emit_log("=" * 50)
            item = self.check_internet()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            worker.emit_log("=" * 50)
            worker.emit_log("【5/7】网络延迟评估")
            worker.emit_log("=" * 50)
            item = self.check_latency()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            worker.emit_log("=" * 50)
            worker.emit_log("【6/7】网络速度测试")
            worker.emit_log("=" * 50)
            item = self.check_speed()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            worker.emit_log("=" * 50)
            worker.emit_log("【7/7】网络环路检测（基础）")
            worker.emit_log("=" * 50)
            item = self.check_loop_basic()
            results['items'].append(item)
            worker.emit_log(f"  {item['message']}\n")
            
            score = 100
            for item in results['items']:
                if item['status'] == 'warning':
                    score -= 5
                elif item['status'] == 'error':
                    score -= 15
            score = max(0, score)
            results['score'] = score
            
            results['suggestions'] = self.generate_suggestions(results['items'])
            
            worker.emit_status("检测完成")
            worker.emit_log("\n" + "=" * 50)
            worker.emit_log(f"📊 综合评分：{score}分")
            worker.emit_log("=" * 50)
            
            worker.emit_finished(results)
        
        except Exception as e:
            worker.emit_log(f"\n❌ 检测异常: {e}")
            worker.emit_finished({'items': [], 'suggestions': [], 'score': 0})
    
    def check_nic_status(self):
        try:
            stats = psutil.net_if_stats()
            active_count = sum(1 for s in stats.values() if s.isup)
            total_count = len(stats)
            if active_count == 0:
                return {'name': '网卡状态', 'status': 'error', 'message': f'没有活动网卡（{total_count}个网卡全部禁用）'}
            elif active_count < total_count:
                return {'name': '网卡状态', 'status': 'warning', 'message': f'部分网卡禁用（{active_count}/{total_count}个活动）'}
            else:
                return {'name': '网卡状态', 'status': 'ok', 'message': f'所有网卡正常工作（{active_count}个活动网卡）'}
        except Exception as e:
            return {'name': '网卡状态', 'status': 'error', 'message': f'检测失败: {e}'}
    
    def check_gateway(self):
        gateway = self.get_gateway()
        latency = self.ping_host(gateway)
        if latency is None:
            return {'name': '网关连通性', 'status': 'error', 'message': f'无法连通网关 {gateway}'}
        elif latency < 10:
            return {'name': '网关连通性', 'status': 'ok', 'message': f'网关 {gateway} 连通良好（{latency}ms）'}
        elif latency < 50:
            return {'name': '网关连通性', 'status': 'ok', 'message': f'网关 {gateway} 连通正常（{latency}ms）'}
        else:
            return {'name': '网关连通性', 'status': 'warning', 'message': f'网关 {gateway} 延迟较高（{latency}ms）'}
    
    def check_dns(self):
        servers = ['8.8.8.8', '223.5.5.5', '114.114.114.114']
        results = []
        for server in servers:
            latency = self.ping_host(server)
            if latency is not None:
                results.append((server, latency))
        
        if not results:
            return {'name': 'DNS解析', 'status': 'error', 'message': '所有DNS服务器不可达'}
        
        avg_latency = sum(r[1] for r in results) / len(results)
        if avg_latency < 30:
            return {'name': 'DNS解析', 'status': 'ok', 'message': f'DNS响应良好（平均{avg_latency:.1f}ms，{len(results)}/{len(servers)}可用）'}
        elif avg_latency < 80:
            return {'name': 'DNS解析', 'status': 'ok', 'message': f'DNS响应正常（平均{avg_latency:.1f}ms，{len(results)}/{len(servers)}可用）'}
        else:
            return {'name': 'DNS解析', 'status': 'warning', 'message': f'DNS响应较慢（平均{avg_latency:.1f}ms）'}
    
    def check_internet(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            start = time.time()
            s.connect(("www.baidu.com", 443))
            elapsed = (time.time() - start) * 1000
            s.close()
            if elapsed < 200:
                return {'name': '外网连接', 'status': 'ok', 'message': f'外网连接正常（{elapsed:.0f}ms）'}
            else:
                return {'name': '外网连接', 'status': 'warning', 'message': f'外网连接较慢（{elapsed:.0f}ms）'}
        except Exception as e:
            return {'name': '外网连接', 'status': 'error', 'message': f'无法连接外网: {e}'}
    
    def check_latency(self):
        targets = ['www.baidu.com', '8.8.8.8', '114.114.114.114']
        latencies = []
        for target in targets:
            latency = self.ping_host(target)
            if latency is not None:
                latencies.append(latency)
        
        if not latencies:
            return {'name': '网络延迟', 'status': 'error', 'message': '所有目标主机不可达'}
        
        avg = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        if avg < 50:
            return {'name': '网络延迟', 'status': 'ok', 'message': f'网络延迟低（平均{avg:.0f}ms，最大{max_latency}ms）'}
        elif avg < 150:
            return {'name': '网络延迟', 'status': 'ok', 'message': f'网络延迟正常（平均{avg:.0f}ms，最大{max_latency}ms）'}
        else:
            return {'name': '网络延迟', 'status': 'warning', 'message': f'网络延迟较高（平均{avg:.0f}ms，最大{max_latency}ms）'}
    
    def check_speed(self):
        try:
            start_sent = psutil.net_io_counters().bytes_sent
            start_recv = psutil.net_io_counters().bytes_recv
            time.sleep(2)
            end_sent = psutil.net_io_counters().bytes_sent
            end_recv = psutil.net_io_counters().bytes_recv
            
            upload_speed = (end_sent - start_sent) / 2 / 1024
            download_speed = (end_recv - start_recv) / 2 / 1024
            
            return {
                'name': '网络速度',
                'status': 'ok',
                'message': f'当前上行 {upload_speed:.1f} KB/s，下行 {download_speed:.1f} KB/s（实时监测）'
            }
        except Exception as e:
            return {'name': '网络速度', 'status': 'error', 'message': f'测速失败: {e}'}
    
    def check_loop_basic(self):
        try:
            stats1 = psutil.net_io_counters()
            time.sleep(2)
            stats2 = psutil.net_io_counters()
            
            sent_diff = stats2.packets_sent - stats1.packets_sent
            recv_diff = stats2.packets_recv - stats1.packets_recv
            
            if recv_diff > sent_diff * 3 and recv_diff > 1000:
                return {
                    'name': '网络环路',
                    'status': 'warning',
                    'message': f'检测到异常广播流量（接收{recv_diff}包/秒，发送{sent_diff}包/秒），建议使用单独环路检测进一步分析'
                }
            else:
                return {
                    'name': '网络环路',
                    'status': 'ok',
                    'message': f'流量正常（接收{recv_diff}包/秒，发送{sent_diff}包/秒）'
                }
        except Exception as e:
            return {'name': '网络环路', 'status': 'error', 'message': f'检测失败: {e}'}
    
    def generate_suggestions(self, items):
        suggestions = []
        for item in items:
            if item['status'] == 'warning':
                if '网关' in item['name']:
                    suggestions.append('检查路由器和网线连接是否正常')
                elif 'DNS' in item['name']:
                    suggestions.append('考虑更换更快的DNS服务器（如阿里DNS 223.5.5.5）')
                elif '延迟' in item['name']:
                    suggestions.append('检查网络环境，避免高峰时段使用')
                elif '环路' in item['name']:
                    suggestions.append('使用"单独环路检测"功能进行深度诊断')
            elif item['status'] == 'error':
                if '网卡' in item['name']:
                    suggestions.append('检查网卡驱动或重新启用网络适配器')
                elif '网关' in item['name']:
                    suggestions.append('检查路由器是否正常工作，重启路由器可能有效')
                elif '外网' in item['name']:
                    suggestions.append('检查网络连接和防火墙设置')
        return suggestions
    
    def get_gateway(self):
        try:
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True, text=True, encoding="gbk", timeout=5
            )
            for line in result.stdout.split('\n'):
                if '0.0.0.0' in line:
                    parts = re.split(r'\s+', line.strip())
                    if len(parts) >= 3 and parts[2] not in ['0.0.0.0', 'On-link']:
                        return parts[2]
        except:
            pass
        return "192.168.1.1"
    
    def ping_host(self, host):
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", host],
                capture_output=True, text=True, timeout=2
            )
            match = re.search(r"时间[=<](\d+)ms", result.stdout)
            if match:
                return int(match.group(1))
            match = re.search(r"time[<=](\d+)ms", result.stdout, re.IGNORECASE)
            if match:
                return int(match.group(1))
        except:
            pass
        return None
    
    def start_loop_check(self):
        if self.loop_worker.is_running:
            return
        
        iface_text = self.iface_combo.currentText()
        if iface_text == "全部网卡":
            iface_name = None
        else:
            iface_name = iface_text.split(" (")[0]
        
        self.loop_worker.is_running = True
        self.loop_start_btn.setEnabled(False)
        self.loop_status_label.setText("正在检测中...")
        self.loop_banner.setText("⏳  正在执行环路检测...")
        self.loop_banner.setStyleSheet("""
            QLabel {
                color: white;
                background-color: #f39c12;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
            }
        """)
        self.loop_result_text.clear()
        
        self.loop_thread = threading.Thread(target=self.run_loop_check, args=(self.loop_worker, iface_name))
        self.loop_thread.start()
    
    def clear_loop_results(self):
        self.loop_status_label.setText("准备就绪，点击开始环路检测...")
        self.set_loop_initial_content()
        self.loop_banner.setText("⏳  网络环路检测工具")
        self.loop_banner.setStyleSheet("""
            QLabel {
                color: white;
                background-color: #3498db;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
            }
        """)
    
    def append_loop_log(self, text):
        from PySide6.QtGui import QTextCursor
        self.loop_result_text.append(text)
        cursor = self.loop_result_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.loop_result_text.setTextCursor(cursor)
    
    def update_loop_status(self, text):
        self.loop_status_label.setText(text)
    
    def update_loop_progress(self, value):
        pass
    
    def on_loop_finished(self, results):
        self.loop_worker.is_running = False
        self.loop_start_btn.setEnabled(True)
        self.display_loop_results(results)
    
    def display_loop_results(self, results):
        has_loop = results.get('has_loop', False)
        if has_loop:
            color = "#e74c3c"
            status_text = "❌ 检测到网络环路！"
        else:
            color = "#2ecc71"
            status_text = "✅ 未检测到网络环路"
        
        self.loop_banner.setText(status_text)
        self.loop_banner.setStyleSheet(f"""
            QLabel {{
                color: white;
                background-color: {color};
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 4px;
            }}
        """)
        
        html = "<div style='padding: 10px; line-height: 1.8;'>"
        html += "<h3>📊 详细检测结果</h3>"
        
        ifaces_checked = results.get('ifaces', [])
        html += f"<p>🔍 检查的网卡: {', '.join(ifaces_checked) if ifaces_checked else '无'}</p>"
        html += f"<p>⏱ 检测时长: {results.get('duration', 0):.1f}秒</p>"
        html += f"<p>📡 采样次数: {results.get('samples', 0)}</p>"
        html += "<br>"
        
        for r in results.get('details', []):
            html += f"<p>• <b>{r['iface']}</b>: {r['message']}</p>"
        
        html += "<br><h3>💡 建议</h3>"
        if has_loop:
            html += "<p>⚠️ 检测到网络环路，建议采取以下措施：</p>"
            html += "<p style='padding-left: 20px;'>1. 检查交换机端口连接，避免形成环路</p>"
            html += "<p style='padding-left: 20px;'>2. 启用 STP（生成树协议）防止环路</p>"
            html += "<p style='padding-left: 20px;'>3. 检查网线连接，移除多余的连接</p>"
        else:
            html += "<p>🎉 网络状态良好，未发现环路问题</p>"
        
        html += "</div>"
        self.loop_result_text.setHtml(html)
    
    def run_loop_check(self, worker, iface_name):
        try:
            worker.emit_status("正在初始化环路检测...")
            worker.emit_log("🚀 开始网络环路检测\n")
            
            if iface_name:
                worker.emit_log(f"🔍 目标网卡: {iface_name}")
                ifaces_to_check = [iface_name]
            else:
                worker.emit_log("🔍 检测所有活动网卡")
                stats = psutil.net_if_stats()
                ifaces_to_check = [name for name, s in stats.items() if s.isup]
            
            worker.emit_log(f"📋 将检查 {len(ifaces_to_check)} 个网卡\n")
            
            start_time = time.time()
            details = []
            samples = 0
            has_loop = False
            
            worker.emit_log("=" * 50)
            worker.emit_log("【底层帧检测】")
            worker.emit_log("=" * 50)
            worker.emit_log("通过监控非单播流量变化检测网络环路")
            worker.emit_log("采样间隔: 1秒, 采样次数: 10\n")
            
            initial_stats = {}
            for iface in ifaces_to_check:
                try:
                    initial_stats[iface] = psutil.net_io_counters(pernic=True).get(iface)
                except:
                    pass
            
            worker.emit_log("开始采样...")
            for i in range(10):
                if not worker.is_running:
                    break
                time.sleep(1)
                samples += 1
                worker.emit_log(f"  📊 采样 {samples}/10 ...")
            
            worker.emit_log("\n分析采样数据...")
            for iface in ifaces_to_check:
                try:
                    final_stats = psutil.net_io_counters(pernic=True).get(iface)
                    if iface in initial_stats and final_stats:
                        init = initial_stats[iface]
                        final = final_stats
                        
                        if hasattr(init, 'dropin') and hasattr(final, 'dropin'):
                            dropin_diff = (final.dropin - init.dropin) if final.dropin > init.dropin else 0
                            dropin_diff += (final.errin - init.errin) if hasattr(final, 'errin') and hasattr(init, 'errin') else 0
                        else:
                            dropin_diff = 0
                        
                        if dropin_diff > samples * 100:
                            has_loop = True
                            details.append({
                                'iface': iface,
                                'message': f'⚠️ 检测到异常丢弃/错误流量 ({dropin_diff} 个)，可能存在网络环路'
                            })
                        else:
                            details.append({
                                'iface': iface,
                                'message': f'✅ 流量正常（丢弃/错误: {dropin_diff} 个）'
                            })
                    else:
                        details.append({
                            'iface': iface,
                            'message': f'⚠️ 无法获取网卡统计信息'
                        })
                except Exception as e:
                    details.append({
                        'iface': iface,
                        'message': f'❌ 检查失败: {e}'
                    })
            
            duration = time.time() - start_time
            
            worker.emit_log("\n" + "=" * 50)
            if has_loop:
                worker.emit_log("❌ 检测结果: 发现网络环路")
            else:
                worker.emit_log("✅ 检测结果: 未发现网络环路")
            worker.emit_log("=" * 50)
            
            worker.emit_status("检测完成")
            
            worker.emit_finished({
                'has_loop': has_loop,
                'ifaces': ifaces_to_check,
                'duration': duration,
                'samples': samples,
                'details': details
            })
        
        except Exception as e:
            worker.emit_log(f"\n❌ 检测异常: {e}")
            worker.emit_finished({'has_loop': False, 'ifaces': [], 'duration': 0, 'samples': 0, 'details': []})
