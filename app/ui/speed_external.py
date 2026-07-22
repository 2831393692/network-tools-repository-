import socket
import ssl
import threading
import time
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QComboBox, QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QObject, Signal, QUrl
from PySide6.QtGui import QFont, QDesktopServices


SPEED_TEST_SERVERS = [
    {
        "name": "淘宝镜像(推荐)",
        "url": "https://registry.npmmirror.com/-/binary/node/latest-v20.x/node-v20.10.0-win-x64.zip",
        "size": 10 * 1024 * 1024,
    },
    {
        "name": "腾讯云镜像站",
        "url": "https://mirrors.cloud.tencent.com/debian-cd/current/amd64/iso-cd/debian-12.7.0-amd64-netinst.iso",
        "size": 10 * 1024 * 1024,
    },
    {
        "name": "AWS US-East(外网)",
        "url": "https://d2q67d9v9y9958.cloudfront.net/awscli-exe-windows-x86_64.zip",
        "size": 10 * 1024 * 1024,
    },
    {
        "name": "GitHub Release(外网)",
        "url": "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe",
        "size": 10 * 1024 * 1024,
    },
    {
        "name": "Cloudflare(外网)",
        "url": "https://github.com/cloudflare/cloudflared/releases/download/2024.10.0/cloudflared-windows-amd64.zip",
        "size": 10 * 1024 * 1024,
    },
    {
        "name": "Node.js Official(外网)",
        "url": "https://nodejs.org/dist/v20.18.0/node-v20.18.0-win-x64.zip",
        "size": 10 * 1024 * 1024,
    },
]


class SpeedTestWorker(QObject):
    status_signal = Signal(str)
    speed_signal = Signal(float)
    latency_signal = Signal(float)
    jitter_signal = Signal(float)
    progress_signal = Signal(int)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False

    def emit_status(self, text):
        self.status_signal.emit(text)

    def emit_speed(self, speed):
        self.speed_signal.emit(speed)

    def emit_latency(self, latency):
        self.latency_signal.emit(latency)

    def emit_jitter(self, jitter):
        self.jitter_signal.emit(jitter)

    def emit_progress(self, value):
        self.progress_signal.emit(value)

    def emit_finished(self):
        self.finished_signal.emit()


def parse_url(url):
    """解析URL，返回 (scheme, host, port, path)"""
    scheme = "http"
    if url.startswith("https://"):
        scheme = "https"
        url = url[8:]
    elif url.startswith("http://"):
        url = url[7:]

    if "/" in url:
        host_part, path = url.split("/", 1)
        path = "/" + path
    else:
        host_part = url
        path = "/"

    port = 443 if scheme == "https" else 80
    if ":" in host_part:
        host, port_str = host_part.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            pass
    else:
        host = host_part

    return scheme, host, port, path


def http_download(url, target_size, stop_flag, speed_callback, progress_callback, chunk_size=32768, max_redirects=5):
    """
    裸 socket HTTP/HTTPS 下载，支持重定向
    返回 (downloaded_bytes, elapsed_time)
    失败返回 (0, 0)
    """
    current_url = url
    redirects = 0

    while redirects < max_redirects:
        if stop_flag():
            return 0, 0

        scheme, host, port, path = parse_url(current_url)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect((host, port))
        except Exception:
            sock.close()
            return 0, 0

        if scheme == "https":
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                sock = ctx.wrap_socket(sock, server_hostname=host)
            except Exception:
                sock.close()
                return 0, 0

        range_end = target_size - 1
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
            f"Accept: */*\r\n"
            f"Accept-Language: zh-CN,zh;q=0.9\r\n"
            f"Range: bytes=0-{range_end}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )

        try:
            sock.sendall(request.encode("ascii"))
        except Exception:
            sock.close()
            return 0, 0

        header = b""
        while b"\r\n\r\n" not in header and len(header) < 16384:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                header += chunk
            except socket.timeout:
                break
            except Exception:
                sock.close()
                return 0, 0

        header_end = header.find(b"\r\n\r\n")
        if header_end == -1:
            sock.close()
            return 0, 0

        header_text = header[:header_end].decode("utf-8", errors="ignore")
        status_line = header_text.split("\r\n")[0] if "\r\n" in header_text else header_text

        status_code = 0
        parts = status_line.split(" ")
        if len(parts) >= 2:
            try:
                status_code = int(parts[1])
            except ValueError:
                pass

        if status_code in (301, 302, 303, 307, 308):
            location = None
            for line in header_text.split("\r\n"):
                if line.lower().startswith("location:"):
                    location = line.split(":", 1)[1].strip()
                    break

            if location:
                sock.close()
                if location.startswith("http://") or location.startswith("https://"):
                    current_url = location
                elif location.startswith("/"):
                    current_url = f"{scheme}://{host}:{port}{location}" if port != (443 if scheme == "https" else 80) else f"{scheme}://{host}{location}"
                else:
                    base_path = path.rsplit("/", 1)[0] + "/"
                    current_url = f"{scheme}://{host}{base_path}{location}"
                redirects += 1
                continue
            else:
                sock.close()
                return 0, 0

        if status_code not in (200, 206):
            sock.close()
            return 0, 0

        body_start = header_end + 4
        body = header[body_start:]
        downloaded = len(body)
        start_time = time.time()

        while downloaded < target_size and not stop_flag():
            try:
                sock.settimeout(5)
                chunk = sock.recv(chunk_size)
                if not chunk:
                    break
                downloaded += len(chunk)

                now = time.time()
                elapsed = now - start_time
                if elapsed > 0:
                    speed_mbps = (downloaded * 8) / (1024 * 1024 * elapsed)
                    speed_callback(speed_mbps)
                    progress = int(min(downloaded / target_size * 100, 100))
                    progress_callback(progress)

            except socket.timeout:
                break
            except Exception:
                break

        sock.close()
        elapsed = time.time() - start_time
        return downloaded, elapsed

    return 0, 0


class SpeedExternalPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self.thread = None
        self.worker = SpeedTestWorker()
        self._stop_flag = False

        self.worker.status_signal.connect(self.append_log)
        self.worker.speed_signal.connect(self.update_speed)
        self.worker.latency_signal.connect(self.update_latency)
        self.worker.jitter_signal.connect(self.update_jitter)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_test_finished)

        self.current_speed = 0
        self.current_latency = 0
        self.current_jitter = 0

        self.init_ui()

    def stop_update_timer(self):
        self.is_running = False
        self.worker.is_running = False
        self._stop_flag = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)

    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)

    def append_log(self, text):
        if hasattr(self, 'result_text'):
            self.result_text.append(text)

    def update_speed(self, speed):
        self.current_speed = speed
        if hasattr(self, 'speed_label'):
            self.speed_label.setText(f"{speed:.1f} Mbps")

    def update_latency(self, latency):
        self.current_latency = latency
        if hasattr(self, 'latency_label'):
            self.latency_label.setText(f"{latency:.1f} ms")

    def update_jitter(self, jitter):
        self.current_jitter = jitter
        if hasattr(self, 'jitter_label'):
            self.jitter_label.setText(f"{jitter:.1f} ms")

    def update_progress(self, value):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)

    def on_test_finished(self):
        self.is_running = False
        if hasattr(self, 'start_btn'):
            self.start_btn.setEnabled(True)
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setEnabled(False)
        self.generate_summary()

    def generate_summary(self):
        quality = "较差"
        quality_icon = "⚠"
        if self.current_latency < 50 and self.current_jitter < 20:
            quality = "优秀"
            quality_icon = "✓"
        elif self.current_latency < 100 and self.current_jitter < 50:
            quality = "良好"
            quality_icon = "✓"
        elif self.current_latency < 200 and self.current_jitter < 100:
            quality = "一般"
            quality_icon = "⚠"

        level = "低速宽带"
        if self.current_speed >= 100:
            level = "高速宽带(100Mbps+)"
        elif self.current_speed >= 50:
            level = "中高速宽带(50-100Mbps)"
        elif self.current_speed >= 10:
            level = "中等宽带(10-50Mbps)"

        self.append_log("=" * 60)
        self.append_log(f"测试结果总结:")
        self.append_log(f"网络质量: {quality_icon} {quality}({'' if self.current_latency < 100 else '高延迟'}或{'' if self.current_jitter < 100 else '高抖动'})")
        self.append_log(f"网络等级: {level}")
        self.append_log(f"速度等级: {level}")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self._build_config_area(layout)
        self._build_metrics_area(layout)
        self._build_progress_area(layout)
        self._build_links_area(layout)
        self._build_result_area(layout)

    def _build_config_area(self, parent_layout):
        title = QLabel("⚙ 测试配置")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        grid = QGridLayout(frame)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(12)

        grid.addWidget(self._styled_label("测试服务器:"), 0, 0)
        self.server_combo = QComboBox()
        self.server_combo.addItems([s["name"] for s in SPEED_TEST_SERVERS])
        self.server_combo.setStyleSheet(self._combo_style())
        grid.addWidget(self.server_combo, 0, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.start_btn = QPushButton("开始测试")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet(self._primary_btn_style("#5b9bd5", "#4a8ac4"))
        self.start_btn.clicked.connect(self.start_test)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._secondary_btn_style())
        self.stop_btn.clicked.connect(self.stop_test)
        btn_layout.addWidget(self.stop_btn)

        grid.addLayout(btn_layout, 0, 2, 1, 2)

        parent_layout.addWidget(frame)

    def _build_metrics_area(self, parent_layout):
        title = QLabel("📊 实时速度指标")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        grid = QGridLayout(frame)
        grid.setContentsMargins(20, 15, 20, 15)
        grid.setSpacing(40)

        speed_label = QLabel("下载速度:")
        speed_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(speed_label, 0, 0)
        self.speed_label = QLabel("0.0 Mbps")
        self.speed_label.setStyleSheet("color: #00b050; font-size: 24px; font-weight: bold; font-family: Consolas;")
        grid.addWidget(self.speed_label, 0, 1)

        latency_label = QLabel("网络延迟:")
        latency_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(latency_label, 0, 2)
        self.latency_label = QLabel("0.0 ms")
        self.latency_label.setStyleSheet("color: #ed7d31; font-size: 24px; font-weight: bold; font-family: Consolas;")
        grid.addWidget(self.latency_label, 0, 3)

        jitter_label = QLabel("网络抖动:")
        jitter_label.setStyleSheet("color: #555; font-size: 12px;")
        grid.addWidget(jitter_label, 0, 4)
        self.jitter_label = QLabel("0.0 ms")
        self.jitter_label.setStyleSheet("color: #ed7d31; font-size: 24px; font-weight: bold; font-family: Consolas;")
        grid.addWidget(self.jitter_label, 0, 5)

        parent_layout.addWidget(frame)

    def _build_progress_area(self, parent_layout):
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: #e0e0e0;
                text-align: center;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background: #5b9bd5;
                border-radius: 4px;
            }
        """)
        parent_layout.addWidget(self.progress_bar)

        tip_label = QLabel("⚠ 提示: 不同运营商网络环境可能存在差异,测试结果仅供参考")
        tip_label.setStyleSheet("color: #ed7d31; font-size: 11px;")
        parent_layout.addWidget(tip_label)

        more_label = QLabel("💡 更多测速站点 (点击跳转浏览器):")
        more_label.setStyleSheet("color: #555; font-size: 11px;")
        parent_layout.addWidget(more_label)

    def _build_links_area(self, parent_layout):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; }
        """)
        link_layout = QHBoxLayout(frame)
        link_layout.setContentsMargins(15, 10, 15, 10)
        link_layout.setSpacing(15)

        links = [
            ("中国科学技术大学测速", "#2e7d32", "https://test.ustc.edu.cn/"),
            ("Speedtest.cn 测速", "#1976d2", "https://www.speedtest.cn/"),
            ("Speedtest.net 国际版", "#7b1fa2", "https://www.speedtest.net/"),
        ]
        for name, color, url in links:
            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: none;
                    padding: 8px 20px;
                    border-radius: 3px;
                    font-size: 12px;
                }}
                QPushButton:hover {{ opacity: 0.9; }}
            """)
            btn.clicked.connect(lambda checked, u=url: QDesktopServices.openUrl(QUrl(u)))
            link_layout.addWidget(btn)

        link_layout.addStretch()
        parent_layout.addWidget(frame)

    def _build_result_area(self, parent_layout):
        title = QLabel("📋 测试结果详情")
        title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        parent_layout.addWidget(title)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, "Microsoft YaHei";
                font-size: 11px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                color: #333;
                padding: 8px;
            }
        """)
        parent_layout.addWidget(self.result_text, 1)

    def start_test(self):
        if self.is_running:
            return
        self.is_running = True
        self.worker.is_running = True
        self._stop_flag = False
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.result_text.clear()
        self.progress_bar.setValue(0)
        self.current_speed = 0
        self.current_latency = 0
        self.current_jitter = 0

        selected_idx = self.server_combo.currentIndex()
        self.selected_server = SPEED_TEST_SERVERS[selected_idx]

        self.thread = threading.Thread(target=self.run_test)
        self.thread.start()

    def stop_test(self):
        self._stop_flag = True
        self.is_running = False
        self.worker.is_running = False
        self.worker.emit_status("正在停止测试...")

    def run_test(self):
        server = self.selected_server
        server_name = server["name"]
        url = server["url"]
        target_size = server["size"]

        self.worker.emit_status(f"正在从 {server_name} 下载测试文件...")

        _, host, port, _ = parse_url(url)

        latencies = []
        for i in range(5):
            if self._stop_flag:
                self.worker.emit_finished()
                return
            latency = self.tcp_ping(host, port)
            if latency > 0:
                latencies.append(latency)
            self.worker.emit_latency(latency)
            time.sleep(0.3)

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        jitter = max(latencies) - min(latencies) if len(latencies) > 1 else 0
        self.worker.emit_latency(avg_latency)
        self.worker.emit_jitter(jitter)

        self.worker.emit_status(f"网络延迟: {avg_latency:.1f} ms")
        self.worker.emit_status(f"网络抖动: {jitter:.1f} ms")
        self.worker.emit_status("")

        self.worker.emit_status(f"正在从 {server_name} 下载测试文件...")

        success = False
        servers_to_try = [server]
        for s in SPEED_TEST_SERVERS:
            if s["name"] != server_name:
                servers_to_try.append(s)

        for srv in servers_to_try:
            if self._stop_flag:
                break

            if srv["name"] != server_name:
                self.worker.emit_status(f"尝试切换到 {srv['name']}...")

            url = srv["url"]
            target_size = srv["size"]

            def speed_cb(spd):
                self.worker.emit_speed(spd)

            def prog_cb(p):
                self.worker.emit_progress(p)

            downloaded, elapsed = http_download(
                url, target_size,
                lambda: self._stop_flag,
                speed_cb, prog_cb
            )

            if downloaded > 0 and elapsed > 0:
                avg_speed = (downloaded * 8) / (1024 * 1024 * elapsed)
                self.worker.emit_speed(avg_speed)
                self.worker.emit_status(f"{srv['name']}下载完成: {avg_speed:.1f} Mbps")
                self.worker.emit_status(f"下载数据量: {downloaded / 1024 / 1024:.1f} MB, 耗时: {elapsed:.1f} 秒")
                success = True
                break
            else:
                self.worker.emit_status(f"{srv['name']} 下载失败，尝试下一个节点...")

        if not success and not self._stop_flag:
            self.worker.emit_status("所有节点均下载失败，请检查网络连接")
            self.worker.emit_speed(0)

        self.worker.emit_progress(100)
        self.worker.emit_finished()

    def tcp_ping(self, host, port):
        try:
            start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            elapsed = (time.time() - start) * 1000
            sock.close()
            return elapsed
        except Exception:
            return 0

    def _styled_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #555; font-size: 12px;")
        return lbl

    def _combo_style(self):
        return """
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
                min-width: 150px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """

    def _primary_btn_style(self, color, hover):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 8px 20px;
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
                padding: 8px 20px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f5f5f5; }
            QPushButton:disabled { color: #aaa; }
        """