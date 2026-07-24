import subprocess
import threading
import re
import socket
import psutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSpinBox, QProgressBar
)
from PySide6.QtCore import Qt, QObject, Signal


class TracerouteWorker(QObject):
    result_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = False

    def emit_result(self, text):
        self.result_signal.emit(text)

    def emit_progress(self, value):
        self.progress_signal.emit(value)

    def emit_finished(self):
        self.finished_signal.emit()


class TraceroutePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.is_running = False
        self.thread = None
        self.worker = TracerouteWorker()
        self.tracert_process = None

        self.worker.result_signal.connect(self.append_result)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_finished)

        self.init_ui()

    def stop_update_timer(self):
        self.is_running = False
        self.worker.is_running = False
        if self.tracert_process and self.tracert_process.poll() is None:
            try:
                self.tracert_process.terminate()
            except:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def hideEvent(self, event):
        self.stop_update_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_update_timer()
        super().closeEvent(event)

    def create_title(self, text, color="#3498db"):
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 12px; padding: 4px 0;"
        )
        return label

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # ===== 路由追踪参数区 =====
        layout.addWidget(self.create_title("⚙ 路由追踪参数"))

        config_frame = QFrame()
        config_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        config_layout = QGridLayout(config_frame)
        config_layout.setContentsMargins(15, 15, 15, 15)
        config_layout.setSpacing(10)

        # 目标主机（占满整行）
        target_label = QLabel("🎯 目标主机:")
        target_label.setStyleSheet("color: #555; font-size: 12px;")
        config_layout.addWidget(target_label, 0, 0)

        self.target_input = QLineEdit("223.5.5.5")
        self.target_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
        """)
        config_layout.addWidget(self.target_input, 0, 1, 1, 5)

        # 最大跳数
        hops_label = QLabel("🌐 最大跳数:")
        hops_label.setStyleSheet("color: #555; font-size: 12px;")
        config_layout.addWidget(hops_label, 1, 0)

        self.max_hops_spin = QSpinBox()
        self.max_hops_spin.setRange(1, 60)
        self.max_hops_spin.setValue(30)
        self.max_hops_spin.setMinimumWidth(80)
        self.max_hops_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
                min-height: 24px;
                padding-right: 24px;
            }
        """)
        config_layout.addWidget(self.max_hops_spin, 1, 1)

        # 操作按钮
        self.start_btn = QPushButton("🔍 开始追踪")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bcd4;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00acc1;
            }
            QPushButton:disabled {
                background-color: #b2ebf2;
                color: #888;
            }
        """)
        self.start_btn.clicked.connect(self.start_traceroute)
        config_layout.addWidget(self.start_btn, 1, 2)

        self.stop_btn = QPushButton("⏹ 停止追踪")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #555;
                border: 1px solid #ccc;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d6d6d6;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #aaa;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_traceroute)
        config_layout.addWidget(self.stop_btn, 1, 3)

        self.diagnose_btn = QPushButton("🔧 网络诊断")
        self.diagnose_btn.setCursor(Qt.PointingHandCursor)
        self.diagnose_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:disabled {
                background-color: #ffe0b2;
                color: #888;
            }
        """)
        self.diagnose_btn.clicked.connect(self.start_diagnose)
        config_layout.addWidget(self.diagnose_btn, 1, 4)

        config_layout.setColumnStretch(5, 1)
        layout.addWidget(config_frame)

        # ===== 路由追踪结果区 =====
        layout.addWidget(self.create_title("🌐 路由追踪结果"))

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, "Microsoft YaHei";
                font-size: 11px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                padding: 8px;
            }
        """)
        layout.addWidget(self.result_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #00bcd4;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def start_traceroute(self):
        if self.is_running:
            return

        target = self.target_input.text().strip()
        if not target:
            self.append_result("[错误] 请输入目标主机地址")
            return

        self.is_running = True
        self.worker.is_running = True
        self.start_btn.setEnabled(False)
        self.diagnose_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.result_text.clear()
        self.progress_bar.setValue(0)

        self.thread = threading.Thread(target=self.run_traceroute, args=(target,))
        self.thread.start()

    def stop_traceroute(self):
        if not self.is_running:
            return

        self.is_running = False
        self.worker.is_running = False
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("⏹ 停止中...")

        if self.tracert_process and self.tracert_process.poll() is None:
            try:
                self.tracert_process.terminate()
            except Exception:
                pass

    def on_finished(self):
        self.is_running = False
        self.worker.is_running = False
        self.tracert_process = None
        self.start_btn.setEnabled(True)
        self.diagnose_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("⏹ 停止追踪")
        self.progress_bar.setValue(100)

    def append_result(self, text):
        if hasattr(self, 'result_text'):
            self.result_text.append(text)
            scrollbar = self.result_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def update_progress(self, value):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)

    def run_traceroute(self, target):
        """
        后台线程：执行 tracert，收集所有跳信息后批量查询地理位置，
        最后统一输出格式化结果（与 UI 设计稿对齐）。
        """
        max_hops = self.max_hops_spin.value()
        timeout_ms = 2000

        # ---------- 头部信息 ----------
        self.worker.emit_result(f"开始追踪到 {target} 的路由，最大跳数: {max_hops}")
        self.worker.emit_result("=" * 80)

        try:
            target_ip = socket.gethostbyname(target)
        except Exception:
            target_ip = target

        is_public = not self._is_private_ip(target_ip)

        self.worker.emit_result(f"目标IP: {target_ip}")
        self.worker.emit_result(
            f"{'📍 目标是公网地址' if is_public else '📍 目标是内网地址'}"
        )

        local_ip = self.get_local_ip()
        self.worker.emit_result(f"本机IP: {local_ip}")
        self.worker.emit_result("")

        # 尝试反向解析目标域名
        try:
            target_host = socket.gethostbyaddr(target_ip)[0]
        except Exception:
            target_host = target

        self.worker.emit_result(f"通过最多 {max_hops} 个跃点跟踪")
        self.worker.emit_result(f"到 {target_host} [{target_ip}] 的路由:")
        self.worker.emit_result("")

        # ---------- 执行 tracert，收集原始数据 ----------
        cmd = f"tracert -h {max_hops} -w {timeout_ms} {target}"
        hops = []          # [{num, times, ip, timeout}, ...]
        hop_count = 0

        try:
            self.tracert_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            for line in iter(self.tracert_process.stdout.readline, ''):
                if not self.is_running:
                    try:
                        self.tracert_process.terminate()
                    except Exception:
                        pass
                    break

                line = line.strip()
                if not line:
                    continue

                hop_match = re.match(r'^\s*(\d+)\s+', line)
                if hop_match:
                    num = int(hop_match.group(1))
                    hop_count = max(hop_count, num)

                    time_matches = re.findall(r'(\d+)\s*ms', line)
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    ip = ip_match.group(1) if ip_match else None

                    # 包含 * 且没有任何延迟值 → 超时
                    is_timeout = '*' in line and not time_matches

                    hops.append({
                        'num': num,
                        'times': time_matches,
                        'ip': ip,
                        'timeout': is_timeout
                    })

                    progress = min(int((num / max_hops) * 100), 99)
                    self.worker.emit_progress(progress)

            self.tracert_process.wait()

        except Exception as e:
            self.worker.emit_result(f"路由追踪失败: {str(e)}")
            self.worker.emit_finished()
            return

        # ---------- tracert 完成后批量查询地理位置 ----------
        geo_cache = {}  # ip -> (location, isp)
        if self.is_running and hops:
            public_ips = []
            seen = set()
            for hop in hops:
                ip = hop['ip']
                if ip and not self._is_private_ip(ip) and ip not in seen:
                    seen.add(ip)
                    public_ips.append(ip)

            if public_ips:
                self.worker.emit_result("  正在查询 IP 地理位置...")
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = {
                        executor.submit(self._query_ip_geo, ip): ip
                        for ip in public_ips
                    }
                    for future in as_completed(futures):
                        ip = futures[future]
                        location, isp = future.result()
                        if location:
                            geo_cache[ip] = (location, isp)

                self.worker.emit_result("")

        # ---------- 格式化输出最终结果 ----------
        if self.is_running and hops:
            last_geo_str = None

            for hop in hops:
                num = hop['num']
                times = hop['times']
                ip = hop['ip']
                is_timeout = hop['timeout']

                # 地理位置：只在新地区变化时显示，避免重复
                if ip and ip in geo_cache:
                    location, isp = geo_cache[ip]
                    geo_str = f"  ├─ 📍 {location} | 🏢 {isp}"
                    if geo_str != last_geo_str:
                        self.worker.emit_result(geo_str)
                        last_geo_str = geo_str

                # 格式化跳数行（固定宽度对齐）
                if is_timeout or not times:
                    self.worker.emit_result(
                        f"{num:<3}  {'*':>5}  {'*':>5}  {'*':>5}  请求超时。"
                    )
                else:
                    # 确保3个时间值（不足补 *）
                    t_vals = times[:3]
                    while len(t_vals) < 3:
                        t_vals.append('*')

                    time_strs = []
                    for t in t_vals:
                        if t == '*':
                            time_strs.append(f"{'*':>5}")
                        else:
                            time_strs.append(f"{t}ms".rjust(5))

                    ip_str = ip if ip else '*'
                    self.worker.emit_result(
                        f"{num:<3}  {time_strs[0]}  {time_strs[1]}  {time_strs[2]}  {ip_str}"
                    )

            # 完成统计
            self.worker.emit_result("")
            self.worker.emit_result("追踪完成。")
            self.worker.emit_result("=" * 80)
            self.worker.emit_result(f"✅ 路由追踪完成，共 {hop_count} 跳")
            self.worker.emit_progress(100)

        self.worker.emit_finished()

    def _is_private_ip(self, ip):
        """
        判断给定 IP 是否为私有/内网地址（RFC1918 + 127.x.x.x）。
        私有地址不查询在线地理位置服务。
        """
        return (
            ip.startswith('10.') or
            ip.startswith('172.16.') or ip.startswith('172.17.') or
            ip.startswith('172.18.') or ip.startswith('172.19.') or
            ip.startswith('172.20.') or ip.startswith('172.21.') or
            ip.startswith('172.22.') or ip.startswith('172.23.') or
            ip.startswith('172.24.') or ip.startswith('172.25.') or
            ip.startswith('172.26.') or ip.startswith('172.27.') or
            ip.startswith('172.28.') or ip.startswith('172.29.') or
            ip.startswith('172.30.') or ip.startswith('172.31.') or
            ip.startswith('192.168.') or
            ip.startswith('127.')
        )

    def _query_ip_geo(self, ip):
        """
        通过 ip-api.com 查询公网 IP 的地理位置与 ISP 信息。

        参数:
            ip: 字符串，IPv4 地址

        返回:
            (location, isp) 元组；查询失败时返回 (None, None)

        注意：
            ip-api.com 免费版限制 45 次/分钟，并发不宜过高。
            内网 IP 不会走到此方法（由 _is_private_ip 过滤）。
        """
        import requests
        try:
            url = (
                f"http://ip-api.com/json/{ip}"
                f"?fields=status,message,country,regionName,city,isp,org"
                f"&lang=zh-CN"
            )
            resp = requests.get(url, timeout=3)
            if resp.status_code == 429:
                return None, None
            data = resp.json()
            if data.get('status') == 'success':
                city = data.get('city', '')
                region = data.get('regionName', '')
                country = data.get('country', '')
                isp = data.get('isp', '') or data.get('org', '')
                location = f"{country} {region} {city}".strip()
                return location, isp
        except Exception:
            pass
        return None, None

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "未知"

    def start_diagnose(self):
        if self.is_running:
            return

        self.is_running = True
        self.worker.is_running = True
        self.start_btn.setEnabled(False)
        self.diagnose_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.result_text.clear()
        self.progress_bar.setValue(0)

        self.thread = threading.Thread(target=self.run_diagnose)
        self.thread.start()

    def run_diagnose(self):
        self.worker.emit_result("🔧 网络环境诊断报告")
        self.worker.emit_result("=" * 80)
        self.worker.emit_progress(10)

        self.worker.emit_result("")
        self.worker.emit_result("📡 网络接口信息:")
        self.worker.emit_result("-" * 80)

        hostname = socket.gethostname()
        local_ip = self.get_local_ip()
        is_nat = not (
            local_ip.startswith('10.') or
            local_ip.startswith('172.16.') or
            local_ip.startswith('172.17.') or
            local_ip.startswith('172.18.') or
            local_ip.startswith('172.19.') or
            local_ip.startswith('172.20.') or
            local_ip.startswith('172.21.') or
            local_ip.startswith('172.22.') or
            local_ip.startswith('172.23.') or
            local_ip.startswith('172.24.') or
            local_ip.startswith('172.25.') or
            local_ip.startswith('172.26.') or
            local_ip.startswith('172.27.') or
            local_ip.startswith('172.28.') or
            local_ip.startswith('172.29.') or
            local_ip.startswith('172.30.') or
            local_ip.startswith('172.31.') or
            local_ip.startswith('192.168.')
        )

        self.worker.emit_result(f"主机名: {hostname}")
        self.worker.emit_result(f"本机IP: {local_ip}")
        self.worker.emit_result(f"网络类型: {'公网' if is_nat else '私有网络(NAT环境)'}")
        self.worker.emit_progress(30)

        self.worker.emit_result("")
        self.worker.emit_result("🔗 连通性测试:")
        self.worker.emit_result("-" * 80)

        targets = [
            ("本地回环", "127.0.0.1", 1),
            ("Google DNS", "8.8.8.8", 2),
            ("180DNS", "180.76.76.76", 2),
            ("百度DNS", "180.101.50.188", 2),
            ("腾讯DNS", "119.29.29.29", 2),
        ]

        for name, host, timeout in targets:
            if not self.is_running:
                break
            try:
                result = subprocess.run(
                    f"ping -n 1 -w {timeout * 1000} {host}",
                    capture_output=True, text=True, timeout=timeout + 2, creationflags=subprocess.CREATE_NO_WINDOW
                )
                match = re.search(r'(?:时间|time)\s*[<=]?\s*(\d+)\s*ms', result.stdout, re.IGNORECASE)
                if match:
                    self.worker.emit_result(f"  ✅ {name} ({host}): {match.group(1)}ms")
                else:
                    self.worker.emit_result(f"  ❌ {name} ({host}): 连接失败")
            except:
                self.worker.emit_result(f"  ❌ {name} ({host}): 连接失败")
            self.worker.emit_progress(min(self.progress_bar.value() + 5, 50))

        self.worker.emit_result("")
        self.worker.emit_result("🛤️ 路由测试:")
        self.worker.emit_result("-" * 80)

        route_targets = ["8.8.8.8", "www.baidu.com"]
        for target in route_targets:
            if not self.is_running:
                break
            try:
                result = subprocess.run(
                    f"tracert -h 5 -w 2000 {target}",
                    capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW
                )
                lines = result.stdout.strip().split('\n')
                hop_lines = [l for l in lines if re.match(r'^\s*\d+\s+', l)]
                if hop_lines:
                    self.worker.emit_result(f"  ✅ {target}: 测试成功")
                else:
                    self.worker.emit_result(f"  ❌ {target}: 测试失败")
            except:
                self.worker.emit_result(f"  ❌ {target}: 测试失败")
        self.worker.emit_progress(70)

        self.worker.emit_result("")
        self.worker.emit_result("📊 环境分析:")
        self.worker.emit_result("-" * 80)

        cpu_count = psutil.cpu_count()
        mem_info = psutil.virtual_memory()
        mem_percent = mem_info.percent

        self.worker.emit_result(f"  🖥️ CPU核心数: {cpu_count}")
        self.worker.emit_result(f"  📦 内存使用: {mem_percent:.1f}%")
        self.worker.emit_result(f"  📶 网络类型: {'物理机或未识别的虚拟化环境'}")
        self.worker.emit_result(f"  🔒 建议检查防火墙和安全软件设置")

        self.worker.emit_progress(90)

        self.worker.emit_result("")
        self.worker.emit_result("📝 诊断总结:")
        self.worker.emit_result("-" * 80)
        self.worker.emit_result("")
        self.worker.emit_result("  如果多个公网IP都只有1跳，通常是网络环境特殊造成的")
        self.worker.emit_result("  这在云服务器、企业网络或特殊ISP环境中比较常见")
        self.worker.emit_result("")
        self.worker.emit_result("=" * 80)
        self.worker.emit_result("✅ 网络诊断完成")
        self.worker.emit_progress(100)

        self.worker.emit_finished()
