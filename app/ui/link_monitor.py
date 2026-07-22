import subprocess
import platform
import time
import re
import json
import urllib.request
import math
from datetime import datetime
from collections import defaultdict, deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QTableWidget, QTableWidgetItem, QCheckBox, QFileDialog,
    QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont


class LinkMonitorWorker(QThread):
    update_signal = Signal(str, dict)
    log_signal = Signal(str, str)
    alert_signal = Signal(str, str)

    def __init__(self, targets, interval, timeout, thresholds, webhooks):
        super().__init__()
        self.targets = targets
        self.interval = interval
        self.timeout = timeout
        self.thresholds = thresholds
        self.webhooks = webhooks
        self.is_running = True
        self.history = defaultdict(lambda: deque(maxlen=100))

    def run(self):
        while self.is_running:
            for target in self.targets:
                if not self.is_running:
                    break
                self.ping_target(target)
            for _ in range(self.interval):
                if not self.is_running:
                    break
                time.sleep(1)

    def ping_target(self, target):
        system = platform.system()
        try:
            if system == "Windows":
                cmd = ["ping", "-n", "1", "-w", str(self.timeout), target]
                timeout_sec = self.timeout / 1000 + 2
            else:
                timeout_sec = max(1, self.timeout // 1000)
                cmd = ["ping", "-c", "1", "-W", str(timeout_sec), target]
                timeout_sec += 2

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_sec
            )
            stdout = result.stdout
            success, latency = self._parse_ping_output(stdout)
        except Exception:
            success = False
            latency = None

        self.history[target].append((success, latency))
        stats = self._calc_stats(target)
        stats["latency"] = latency if latency is not None else "-"
        stats["success"] = success
        stats["time"] = datetime.now().strftime("%H:%M:%S")

        self.update_signal.emit(target, stats)

        status = self._check_thresholds(stats)
        if status:
            msg = (
                f"目标 [{target}] 异常: {status} | "
                f"延迟: {stats['avg_latency']}ms | "
                f"丢包: {stats['loss_rate']}% | "
                f"抖动: {stats['jitter']}ms"
            )
            self.log_signal.emit(msg, "alert")
            self.alert_signal.emit(target, status)
            self._send_webhook(target, status, stats)
        else:
            if not success:
                msg = f"目标 [{target}] 无响应 | 丢包: {stats['loss_rate']}%"
                self.log_signal.emit(msg, "warning")

    def _parse_ping_output(self, output):
        if not output:
            return False, None
        latency_match = re.search(
            r"(?:时间|time)\s*[<=]?\s*(\d+(?:\.\d+)?)\s*ms",
            output, re.IGNORECASE
        )
        if latency_match:
            latency = float(latency_match.group(1))
            return True, latency

        failure_markers = [
            "请求超时", "Request timed out", "无法访问目标主机",
            "Destination host unreachable", "传输失败", "transmit failed",
            "一般故障", "General failure", "Ping 请求找不到主机",
            "Ping request could not find host", "100% 丢失", "100% loss",
        ]
        for marker in failure_markers:
            if marker in output:
                return False, None
        return False, None

    def _calc_stats(self, target):
        records = list(self.history[target])
        total = len(records)
        if total == 0:
            return {"avg_latency": "-", "loss_rate": 0, "jitter": "-"}

        success_count = sum(1 for s, _ in records if s)
        latencies = [lat for s, lat in records if s and lat is not None]

        loss_rate = round((total - success_count) / total * 100, 1)

        if latencies:
            avg_latency = round(sum(latencies) / len(latencies), 1)
            if len(latencies) > 1:
                mean = sum(latencies) / len(latencies)
                variance = sum((x - mean) ** 2 for x in latencies) / len(latencies)
                jitter = round(math.sqrt(variance), 1)
            else:
                jitter = 0.0
        else:
            avg_latency = "-"
            jitter = "-"

        return {
            "avg_latency": avg_latency,
            "loss_rate": loss_rate,
            "jitter": jitter,
        }

    def _check_thresholds(self, stats):
        alerts = []
        avg = stats.get("avg_latency")
        loss = stats.get("loss_rate")
        jitter = stats.get("jitter")

        if avg != "-" and isinstance(avg, (int, float)):
            if avg > self.thresholds["latency"]:
                alerts.append(f"延迟过高({avg}ms)")
        if isinstance(loss, (int, float)):
            if loss > self.thresholds["loss"]:
                alerts.append(f"丢包过高({loss}%)")
        if jitter != "-" and isinstance(jitter, (int, float)):
            if jitter > self.thresholds["jitter"]:
                alerts.append(f"抖动过高({jitter}ms)")

        return "; ".join(alerts) if alerts else ""

    def _send_webhook(self, target, status, stats):
        payload = {
            "msg_type": "text",
            "content": {
                "text": (
                    f"链路监控告警\n"
                    f"目标: {target}\n"
                    f"状态: {status}\n"
                    f"平均延迟: {stats.get('avg_latency', '-')}ms\n"
                    f"丢包率: {stats.get('loss_rate', '-')}%\n"
                    f"抖动: {stats.get('jitter', '-')}ms\n"
                    f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            }
        }
        for hook_type, url in self.webhooks.items():
            if not url:
                continue
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass

    def stop(self):
        self.is_running = False
        self.wait(2000)


class LinkMonitorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.worker = None
        self.target_rows = {}
        self.alert_count = 0
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("🌐 链路监控")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        left_frame = self._create_target_frame()
        top_layout.addWidget(left_frame, 1)

        right_frame = self._create_threshold_frame()
        top_layout.addWidget(right_frame, 1)

        layout.addLayout(top_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.start_btn = QPushButton("▶ 启动监控")
        self.start_btn.setStyleSheet("""
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
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_monitor)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止监控")
        self.stop_btn.setStyleSheet("""
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
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_monitor)
        btn_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("🧹 清空日志")
        self.clear_btn.setStyleSheet("""
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
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_logs)
        btn_layout.addWidget(self.clear_btn)

        self.export_html_btn = QPushButton("📄 导出HTML")
        self.export_html_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.export_html_btn.setCursor(Qt.PointingHandCursor)
        self.export_html_btn.clicked.connect(self.export_html)
        btn_layout.addWidget(self.export_html_btn)

        self.export_json_btn = QPushButton("📋 导出JSON")
        self.export_json_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 25px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #8e44ad; }
        """)
        self.export_json_btn.setCursor(Qt.PointingHandCursor)
        self.export_json_btn.clicked.connect(self.export_json)
        btn_layout.addWidget(self.export_json_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        table_title = QLabel("📊 实时链路状态")
        table_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(table_title)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["监控目标", "状态", "平均延迟", "丢包率", "抖动", "最近一次"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 120)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
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
        layout.addWidget(self.table, 1)

        log_title = QLabel("📝 告警与事件日志")
        log_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px; padding: 4px 0;")
        layout.addWidget(log_title)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 12px;
                color: #ffffff;
                padding: 8px;
            }
        """)
        layout.addWidget(self.log_edit, 1)

    def _create_target_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)

        title = QLabel("🎯 监控目标")
        title.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        self.target_edit = QTextEdit()
        self.target_edit.setPlainText("192.168.1.1\n223.5.5.5")
        self.target_edit.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-family: 'Consolas', 'Microsoft YaHei';
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.target_edit)

        hint = QLabel("示例：网关、DNS、业务IP（每行一个）")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        return frame

    def _create_threshold_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("⚙ 阈值与通知")
        title.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        fields = [
            ("采样间隔(秒):", "interval_edit", "5"),
            ("超时(ms):", "timeout_edit", "1000"),
            ("延迟阈值(ms):", "latency_edit", "80"),
            ("丢包阈值(%):", "loss_edit", "10"),
            ("抖动阈值(ms):", "jitter_edit", "30"),
        ]

        for i, (label, attr, default) in enumerate(fields):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #555; font-size: 12px;")
            grid.addWidget(lbl, i, 0)
            edit = QLineEdit(default)
            edit.setStyleSheet("""
                QLineEdit {
                    padding: 5px;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    background-color: white;
                    font-size: 12px;
                }
            """)
            setattr(self, attr, edit)
            grid.addWidget(edit, i, 1)

        layout.addLayout(grid)

        feishu_layout = QHBoxLayout()
        self.feishu_check = QCheckBox("飞书告警")
        self.feishu_check.setStyleSheet("color: #555; font-size: 12px;")
        feishu_layout.addWidget(self.feishu_check)
        self.feishu_url = QLineEdit()
        self.feishu_url.setPlaceholderText("飞书Webhook地址")
        self.feishu_url.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        feishu_layout.addWidget(self.feishu_url, 1)
        self.feishu_test_btn = QPushButton("测试")
        self.feishu_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.feishu_test_btn.setCursor(Qt.PointingHandCursor)
        self.feishu_test_btn.clicked.connect(lambda: self.test_webhook("feishu"))
        feishu_layout.addWidget(self.feishu_test_btn)
        layout.addLayout(feishu_layout)

        wx_layout = QHBoxLayout()
        self.wx_check = QCheckBox("企微告警")
        self.wx_check.setStyleSheet("color: #555; font-size: 12px;")
        wx_layout.addWidget(self.wx_check)
        self.wx_url = QLineEdit()
        self.wx_url.setPlaceholderText("企微Webhook地址")
        self.wx_url.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        wx_layout.addWidget(self.wx_url, 1)
        self.wx_test_btn = QPushButton("测试")
        self.wx_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.wx_test_btn.setCursor(Qt.PointingHandCursor)
        self.wx_test_btn.clicked.connect(lambda: self.test_webhook("wecom"))
        wx_layout.addWidget(self.wx_test_btn)
        layout.addLayout(wx_layout)

        return frame

    def start_monitor(self):
        targets = [
            t.strip() for t in self.target_edit.toPlainText().splitlines() if t.strip()
        ]
        if not targets:
            QMessageBox.warning(self, "提示", "请输入至少一个监控目标")
            return

        try:
            interval = int(self.interval_edit.text() or "5")
            timeout = int(self.timeout_edit.text() or "1000")
            latency_th = int(self.latency_edit.text() or "80")
            loss_th = int(self.loss_edit.text() or "10")
            jitter_th = int(self.jitter_edit.text() or "30")
        except ValueError:
            QMessageBox.warning(self, "提示", "阈值参数必须为整数")
            return

        thresholds = {
            "latency": latency_th,
            "loss": loss_th,
            "jitter": jitter_th,
        }

        webhooks = {}
        if self.feishu_check.isChecked():
            webhooks["feishu"] = self.feishu_url.text().strip()
        if self.wx_check.isChecked():
            webhooks["wecom"] = self.wx_url.text().strip()

        self.stop_monitor()
        self.table.setRowCount(0)
        self.target_rows.clear()
        self.alert_count = 0

        self.worker = LinkMonitorWorker(
            targets, interval, timeout, thresholds, webhooks
        )
        self.worker.update_signal.connect(self.on_update)
        self.worker.log_signal.connect(self.on_log)
        self.worker.alert_signal.connect(self.on_alert)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.append_log("✅ 监控已启动", "info")

    def stop_monitor(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            try:
                self.worker.update_signal.disconnect(self.on_update)
                self.worker.log_signal.disconnect(self.on_log)
                self.worker.alert_signal.disconnect(self.on_alert)
            except Exception:
                pass
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("⏹ 监控已停止", "info")

    def on_update(self, target, stats):
        if target not in self.target_rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.target_rows[target] = row
            self.table.setItem(row, 0, QTableWidgetItem(target))
            for col in range(1, 6):
                self.table.setItem(row, col, QTableWidgetItem("-"))
        else:
            row = self.target_rows[target]

        success = stats.get("success", False)
        status_text = "🟢 正常" if success else "🔴 异常"
        status_item = QTableWidgetItem(status_text)
        if success:
            status_item.setForeground(QColor("#27ae60"))
        else:
            status_item.setForeground(QColor("#e74c3c"))
        self.table.setItem(row, 1, status_item)

        avg = stats.get("avg_latency", "-")
        self.table.setItem(row, 2, QTableWidgetItem(str(avg)))

        loss = stats.get("loss_rate", "-")
        loss_item = QTableWidgetItem(f"{loss}%")
        if isinstance(loss, (int, float)) and loss > 0:
            loss_item.setForeground(QColor("#e74c3c"))
        self.table.setItem(row, 3, loss_item)

        jitter = stats.get("jitter", "-")
        self.table.setItem(row, 4, QTableWidgetItem(str(jitter)))

        self.table.setItem(row, 5, QTableWidgetItem(stats.get("time", "-")))

    def on_log(self, msg, level):
        color_map = {
            "alert": "#ff6b6b",
            "warning": "#f1c40f",
            "info": "#2ecc71",
        }
        color = color_map.get(level, "#ffffff")
        self.append_log(msg, color)

    def on_alert(self, target, status):
        self.alert_count += 1

    def append_log(self, msg, color="#ffffff"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        html = f'<span style="color: {color};">[{timestamp}] {msg}</span>'
        self.log_edit.append(html)

    def clear_logs(self):
        self.log_edit.clear()
        self.alert_count = 0

    def test_webhook(self, hook_type):
        url = ""
        if hook_type == "feishu":
            url = self.feishu_url.text().strip()
        else:
            url = self.wx_url.text().strip()

        if not url:
            QMessageBox.warning(self, "提示", "请输入Webhook地址")
            return

        payload = {
            "msg_type": "text",
            "content": {"text": "链路监控测试消息"},
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
            QMessageBox.information(self, "成功", "测试消息已发送")
        except Exception as e:
            QMessageBox.critical(self, "失败", f"发送失败: {e}")

    def export_html(self):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "导出HTML", f"link_monitor_{timestamp}.html", "HTML文件 (*.html)"
            )
            if not filename:
                return

            rows = []
            for target, row_idx in self.target_rows.items():
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row_idx, col)
                    row_data.append(item.text() if item else "")
                rows.append(row_data)

            logs = self.log_edit.toPlainText()

            html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>链路监控报告</title>
<style>
body {{ font-family: 'Microsoft YaHei', sans-serif; margin: 40px; background: #f5f5f5; }}
.container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
h1 {{ color: #2c3e50; border-bottom: 3px solid #00bcd4; padding-bottom: 10px; }}
table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
th {{ background-color: #34495e; color: white; }}
tr:nth-child(even) {{ background-color: #f9f9f9; }}
.logs {{ background: #1e1e1e; color: #fff; padding: 15px; border-radius: 4px; font-family: Consolas, monospace; white-space: pre-wrap; }}
</style>
</head>
<body>
<div class="container">
<h1>链路监控报告</h1>
<p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<table>
<tr><th>监控目标</th><th>状态</th><th>平均延迟</th><th>丢包率</th><th>抖动</th><th>最近一次</th></tr>
"""
            for row in rows:
                html += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>\n"
            html += f"""
</table>
<h2>日志</h2>
<div class="logs">{logs}</div>
</div>
</body>
</html>"""

            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)
            QMessageBox.information(self, "成功", f"已导出到: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def export_json(self):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "导出JSON", f"link_monitor_{timestamp}.json", "JSON文件 (*.json)"
            )
            if not filename:
                return

            data = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "targets": [],
                "logs": self.log_edit.toPlainText(),
            }

            for target, row_idx in self.target_rows.items():
                row_data = {}
                headers = ["target", "status", "avg_latency", "loss_rate", "jitter", "last_time"]
                for col, key in enumerate(headers):
                    item = self.table.item(row_idx, col)
                    row_data[key] = item.text() if item else ""
                data["targets"].append(row_data)

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已导出到: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def cleanup(self):
        self.stop_monitor()

    def hideEvent(self, event):
        self.cleanup()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
