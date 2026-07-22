import time
import subprocess
import re
from collections import deque
from datetime import timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QFont

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class TrafficChart(QWidget):
    """自定义流量曲线图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rx_data = deque([0.0] * 120, maxlen=120)
        self.tx_data = deque([0.0] * 120, maxlen=120)
        self.max_value = 100.0
        self.setMinimumSize(400, 250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def add_data(self, rx_kb: float, tx_kb: float):
        self.rx_data.append(rx_kb)
        self.tx_data.append(tx_kb)
        self.max_value = max(1.0, max(max(self.rx_data), max(self.tx_data)) * 1.1)
        self.update()

    def clear_data(self):
        self.rx_data = deque([0.0] * 120, maxlen=120)
        self.tx_data = deque([0.0] * 120, maxlen=120)
        self.max_value = 100.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        margin_left = 50
        margin_right = 15
        margin_top = 20
        margin_bottom = 40

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        # 背景
        painter.fillRect(self.rect(), QColor("#0f1419"))

        # 网格线
        grid_pen = QPen(QColor("#1e293b"))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        for i in range(5):
            y = margin_top + chart_h * i / 4
            painter.drawLine(int(margin_left), int(y), int(margin_left + chart_w), int(y))

        for i in range(7):
            x = margin_left + chart_w * i / 6
            painter.drawLine(int(x), int(margin_top), int(x), int(margin_top + chart_h))

        # 边框
        border_pen = QPen(QColor("#334155"))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.drawRect(int(margin_left), int(margin_top), int(chart_w), int(chart_h))

        # Y轴标签
        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("Consolas", 8))
        for i in range(5):
            value = self.max_value * (4 - i) / 4
            y = margin_top + chart_h * i / 4
            label = self._format_speed(value)
            painter.drawText(2, int(y - 6), margin_left - 6, 12, Qt.AlignRight | Qt.AlignVCenter, label)

        # X轴标签
        for i in range(7):
            x = margin_left + chart_w * i / 6
            seconds = int(120 * i / 6)
            label = f"-{120 - seconds}s"
            painter.drawText(int(x - 25), int(margin_top + chart_h + 4), 50, 14, Qt.AlignCenter, label)

        # 绘制曲线
        self._draw_line(painter, self.rx_data, QColor("#3b82f6"), margin_left, margin_top, chart_w, chart_h)
        self._draw_line(painter, self.tx_data, QColor("#22c55e"), margin_left, margin_top, chart_w, chart_h)

        # 图例
        legend_y = h - 18
        painter.setPen(QPen(QColor("#3b82f6"), 2))
        painter.drawLine(int(margin_left + 10), legend_y, int(margin_left + 30), legend_y)
        painter.setPen(QColor("#e2e8f0"))
        painter.drawText(int(margin_left + 35), legend_y - 6, 100, 12, Qt.AlignLeft | Qt.AlignVCenter, "↓ 下载(RX)")

        painter.setPen(QPen(QColor("#22c55e"), 2))
        painter.drawLine(int(margin_left + 130), legend_y, int(margin_left + 150), legend_y)
        painter.setPen(QColor("#e2e8f0"))
        painter.drawText(int(margin_left + 155), legend_y - 6, 100, 12, Qt.AlignLeft | Qt.AlignVCenter, "↑ 上传(TX)")

    def _draw_line(self, painter, data, color, margin_left, margin_top, chart_w, chart_h):
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)

        data_list = list(data)
        if len(data_list) < 2:
            return

        step = chart_w / (len(data_list) - 1)
        points = []
        for i, value in enumerate(data_list):
            x = margin_left + i * step
            y = margin_top + chart_h - (value / self.max_value) * chart_h
            points.append((x, y))

        for i in range(len(points) - 1):
            painter.drawLine(int(points[i][0]), int(points[i][1]), int(points[i + 1][0]), int(points[i + 1][1]))

    @staticmethod
    def _format_speed(kb: float) -> str:
        if kb >= 1024:
            return f"{kb / 1024:.1f}M"
        return f"{kb:.0f}K"


class TrafficMonitorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_monitoring = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.collect_data)

        self.selected_interface = None
        self.last_stats = None
        self.last_time = 0.0
        self.start_time = 0.0
        self.total_rx = 0.0
        self.total_tx = 0.0
        self.sample_count = 0
        self.peak_rx = 0.0
        self.peak_tx = 0.0
        self.sum_rx = 0.0
        self.sum_tx = 0.0

        self.init_ui()
        self.refresh_interfaces()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # 标题栏
        title_label = QLabel("📊 实时流量监控  Network Interface Realtime Traffic")
        title_label.setStyleSheet("color: #333; font-size: 14px; font-weight: bold; margin-bottom: 5px;")
        main_layout.addWidget(title_label)

        # 顶部控制栏
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)

        control_layout.addWidget(self._styled_label("网卡:"))
        self.interface_combo = QComboBox()
        self.interface_combo.setMinimumWidth(200)
        self.interface_combo.setStyleSheet(self._combo_style())
        control_layout.addWidget(self.interface_combo)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setStyleSheet(self._secondary_btn_style())
        self.refresh_btn.clicked.connect(self.refresh_interfaces)
        control_layout.addWidget(self.refresh_btn)

        control_layout.addSpacing(15)
        control_layout.addWidget(self._styled_label("采样间隔:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItem("0.5秒", 500)
        self.interval_combo.addItem("1秒", 1000)
        self.interval_combo.addItem("2秒", 2000)
        self.interval_combo.addItem("5秒", 5000)
        self.interval_combo.setCurrentIndex(1)
        self.interval_combo.setStyleSheet(self._combo_style())
        control_layout.addWidget(self.interval_combo)

        self.start_btn = QPushButton("▶ 开始监控")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet(self._primary_btn_style("#3b82f6", "#2563eb"))
        self.start_btn.clicked.connect(self.start_monitor)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._primary_btn_style("#ef4444", "#dc2626"))
        self.stop_btn.clicked.connect(self.stop_monitor)
        control_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🧹 清空")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(self._secondary_btn_style())
        self.clear_btn.clicked.connect(self.clear_data)
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # 主体内容：左侧图表 + 右侧统计
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # 左侧图表
        chart_frame = QFrame()
        chart_frame.setStyleSheet("QFrame { background: #0f1419; border: 1px solid #334155; border-radius: 4px; }")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(5, 5, 5, 5)

        chart_title = QLabel("实时速率曲线 (KB/s)")
        chart_title.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold; background: transparent;")
        chart_layout.addWidget(chart_title)

        self.chart = TrafficChart()
        chart_layout.addWidget(self.chart, 1)
        content_layout.addWidget(chart_frame, 3)

        # 右侧统计面板
        stats_frame = QFrame()
        stats_frame.setStyleSheet("QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 4px; }")
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 15, 15, 15)
        stats_layout.setSpacing(12)

        stats_title = QLabel("📈 统计信息")
        stats_title.setStyleSheet("color: #333; font-size: 13px; font-weight: bold; background: transparent;")
        stats_layout.addWidget(stats_title)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)

        self.curr_rx_label = self._stat_value_label("-", "#3b82f6")
        self.curr_tx_label = self._stat_value_label("-", "#22c55e")
        self.peak_rx_label = self._stat_value_label("-", "#3b82f6")
        self.peak_tx_label = self._stat_value_label("-", "#22c55e")
        self.avg_rx_label = self._stat_value_label("-", "#3b82f6")
        self.avg_tx_label = self._stat_value_label("-", "#22c55e")
        self.total_rx_label = self._stat_value_label("-", "#64748b")
        self.total_tx_label = self._stat_value_label("-", "#64748b")
        self.duration_label = self._stat_value_label("00:00", "#64748b")

        row = 0
        grid.addWidget(self._styled_label("当前下载速率:"), row, 0)
        grid.addWidget(self.curr_rx_label, row, 1)
        row += 1
        grid.addWidget(self._styled_label("当前上传速率:"), row, 0)
        grid.addWidget(self.curr_tx_label, row, 1)
        row += 1

        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: #e0e0e0;")
        grid.addWidget(line1, row, 0, 1, 2)
        row += 1

        grid.addWidget(self._styled_label("峰值下载速率:"), row, 0)
        grid.addWidget(self.peak_rx_label, row, 1)
        row += 1
        grid.addWidget(self._styled_label("峰值上传速率:"), row, 0)
        grid.addWidget(self.peak_tx_label, row, 1)
        row += 1

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #e0e0e0;")
        grid.addWidget(line2, row, 0, 1, 2)
        row += 1

        grid.addWidget(self._styled_label("平均下载速率:"), row, 0)
        grid.addWidget(self.avg_rx_label, row, 1)
        row += 1
        grid.addWidget(self._styled_label("平均上传速率:"), row, 0)
        grid.addWidget(self.avg_tx_label, row, 1)
        row += 1

        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setStyleSheet("color: #e0e0e0;")
        grid.addWidget(line3, row, 0, 1, 2)
        row += 1

        grid.addWidget(self._styled_label("累计接收:"), row, 0)
        grid.addWidget(self.total_rx_label, row, 1)
        row += 1
        grid.addWidget(self._styled_label("累计发送:"), row, 0)
        grid.addWidget(self.total_tx_label, row, 1)
        row += 1

        line4 = QFrame()
        line4.setFrameShape(QFrame.HLine)
        line4.setStyleSheet("color: #e0e0e0;")
        grid.addWidget(line4, row, 0, 1, 2)
        row += 1

        grid.addWidget(self._styled_label("监控时长:"), row, 0)
        grid.addWidget(self.duration_label, row, 1)

        stats_layout.addLayout(grid)
        stats_layout.addStretch()
        content_layout.addWidget(stats_frame, 1)

        main_layout.addLayout(content_layout, 1)

        # 底部状态栏
        self.status_label = QLabel("就绪 — 选择网卡后点击「开始监控」")
        self.status_label.setStyleSheet("color: #64748b; font-size: 12px; padding-top: 5px;")
        main_layout.addWidget(self.status_label)

    def refresh_interfaces(self):
        self.interface_combo.clear()
        interfaces = self._get_interfaces()
        if interfaces:
            for name in interfaces:
                self.interface_combo.addItem(name)
            self.status_label.setText(f"就绪 — 已刷新网卡列表，共 {len(interfaces)} 个网卡")
        else:
            self.interface_combo.addItem("无可用网卡")
            self.status_label.setText("警告 — 未检测到可用网卡，请检查网络连接")

    def start_monitor(self):
        if self.is_monitoring:
            return

        iface = self.interface_combo.currentText()
        if not iface or iface == "无可用网卡":
            self.status_label.setText("错误 — 请先选择有效的网卡")
            return

        self.selected_interface = iface
        self.is_monitoring = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.interface_combo.setEnabled(False)
        self.interval_combo.setEnabled(False)

        self.last_stats = None
        self.last_time = 0.0
        self.start_time = time.time()
        self.total_rx = 0.0
        self.total_tx = 0.0
        self.sample_count = 0
        self.peak_rx = 0.0
        self.peak_tx = 0.0
        self.sum_rx = 0.0
        self.sum_tx = 0.0

        interval_ms = self.interval_combo.currentData()
        self.timer.start(interval_ms)
        self.status_label.setText(f"监控中 — 网卡: {iface} | 采样间隔: {interval_ms / 1000:.1f}秒")

        # 立即采集一次
        self.collect_data()

    def stop_monitor(self):
        if not self.is_monitoring:
            return
        self.is_monitoring = False
        self.timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.interface_combo.setEnabled(True)
        self.interval_combo.setEnabled(True)
        self.status_label.setText("已停止 — 点击「开始监控」继续")

    def clear_data(self):
        self.chart.clear_data()
        self.curr_rx_label.setText("- KB/s")
        self.curr_tx_label.setText("- KB/s")
        self.peak_rx_label.setText("- KB/s")
        self.peak_tx_label.setText("- KB/s")
        self.avg_rx_label.setText("- KB/s")
        self.avg_tx_label.setText("- KB/s")
        self.total_rx_label.setText("- MB")
        self.total_tx_label.setText("- MB")
        self.duration_label.setText("00:00")
        self.total_rx = 0.0
        self.total_tx = 0.0
        self.sample_count = 0
        self.peak_rx = 0.0
        self.peak_tx = 0.0
        self.sum_rx = 0.0
        self.sum_tx = 0.0
        if not self.is_monitoring:
            self.status_label.setText("就绪 — 数据已清空，选择网卡后点击「开始监控」")

    def collect_data(self):
        iface = self.selected_interface
        if not iface:
            return

        current_time = time.time()
        current_stats = self._get_interface_stats(iface)

        if current_stats is None:
            self.status_label.setText(f"错误 — 无法获取网卡 {iface} 的统计数据")
            return

        if self.last_stats is not None and self.last_time > 0:
            elapsed = current_time - self.last_time
            if elapsed > 0:
                rx_speed = (current_stats["rx"] - self.last_stats["rx"]) / elapsed / 1024
                tx_speed = (current_stats["tx"] - self.last_stats["tx"]) / elapsed / 1024

                # 处理计数器回绕或异常
                if rx_speed < 0:
                    rx_speed = 0.0
                if tx_speed < 0:
                    tx_speed = 0.0

                self.chart.add_data(rx_speed, tx_speed)
                self._update_stats(rx_speed, tx_speed, current_stats)

        self.last_stats = current_stats
        self.last_time = current_time

    def _update_stats(self, rx_kb: float, tx_kb: float, current_stats: dict):
        self.sample_count += 1
        self.sum_rx += rx_kb
        self.sum_tx += tx_kb
        self.peak_rx = max(self.peak_rx, rx_kb)
        self.peak_tx = max(self.peak_tx, tx_kb)

        if self.last_stats:
            self.total_rx = current_stats["rx"] / (1024 * 1024)
            self.total_tx = current_stats["tx"] / (1024 * 1024)

        self.curr_rx_label.setText(f"{rx_kb:.1f} KB/s")
        self.curr_tx_label.setText(f"{tx_kb:.1f} KB/s")
        self.peak_rx_label.setText(f"{self.peak_rx:.1f} KB/s")
        self.peak_tx_label.setText(f"{self.peak_tx:.1f} KB/s")

        avg_rx = self.sum_rx / self.sample_count if self.sample_count > 0 else 0.0
        avg_tx = self.sum_tx / self.sample_count if self.sample_count > 0 else 0.0
        self.avg_rx_label.setText(f"{avg_rx:.1f} KB/s")
        self.avg_tx_label.setText(f"{avg_tx:.1f} KB/s")

        self.total_rx_label.setText(f"{self.total_rx:.1f} MB")
        self.total_tx_label.setText(f"{self.total_tx:.1f} MB")

        elapsed = int(time.time() - self.start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")

    def cleanup(self):
        self.stop_monitor()

    def hideEvent(self, event):
        self.stop_monitor()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_monitor()
        super().closeEvent(event)

    def _get_interfaces(self):
        if HAS_PSUTIL:
            try:
                counters = psutil.net_io_counters(pernic=True)
                return list(counters.keys())
            except Exception:
                pass

        # 备选: Windows wmic
        try:
            result = subprocess.run(
                ["wmic", "nic", "where", "NetEnabled=true", "get", "NetConnectionID"],
                capture_output=True, text=True, timeout=10
            )
            lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            if lines and lines[0].lower() == "netconnectionid":
                lines = lines[1:]
            return [line for line in lines if line]
        except Exception:
            pass

        # 备选: PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=10
            )
            lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            return lines
        except Exception:
            pass

        return []

    def _get_interface_stats(self, iface: str):
        if HAS_PSUTIL:
            try:
                counters = psutil.net_io_counters(pernic=True)
                if iface in counters:
                    c = counters[iface]
                    return {"rx": c.bytes_recv, "tx": c.bytes_sent}
            except Exception:
                pass

        # 备选: Windows wmic Performance counters
        try:
            # 尝试通过 wmic 获取 (注意: wmic 的网卡名称可能和 psutil 不同)
            result = subprocess.run(
                ["wmic", "path", "Win32_PerfRawData_Tcpip_NetworkInterface",
                 "where", f"Name='{iface}'", "get", "BytesReceivedPersec,BytesSentPersec"],
                capture_output=True, text=True, timeout=10
            )
            lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            if len(lines) >= 2 and "BytesReceivedPersec" in lines[0]:
                vals = lines[1].split()
                if len(vals) >= 2:
                    return {"rx": int(vals[0]), "tx": int(vals[1])}
        except Exception:
            pass

        # 备选: 通过 Get-NetAdapterStatistics 获取
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"$s = Get-NetAdapterStatistics -Name '{iface}' -ErrorAction SilentlyContinue; if ($s) {{ $s.ReceivedBytes.ToString() + ' ' + $s.SentBytes.ToString() }}"],
                capture_output=True, text=True, timeout=10
            )
            line = result.stdout.strip()
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    return {"rx": int(parts[0]), "tx": int(parts[1])}
        except Exception:
            pass

        return None

    def _styled_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #555; font-size: 12px; background: transparent;")
        return lbl

    def _stat_value_label(self, text, color):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold; background: transparent;")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lbl

    def _combo_style(self):
        return """
            QComboBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
                min-width: 100px;
            }
        """

    def _primary_btn_style(self, color, hover):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: #e0e0e0; color: #888; }}
        """

    def _secondary_btn_style(self):
        return """
            QPushButton {
                background-color: white;
                color: #555;
                border: 1px solid #ccc;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f5f5f5; }
            QPushButton:disabled { color: #aaa; }
        """
