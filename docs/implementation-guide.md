# 网络工具箱 - 核心方法实现文档

> **版本**: V1.0  
> **更新日期**: 2026-07-23  
> **所属项目**: project_03_network-testing-toolkit  

---

## 目录

1. [subprocess 安全调用模式](#1-subprocess-安全调用模式)
2. [异步初始化模式（主线程阻塞解决方案）](#2-异步初始化模式主线程阻塞解决方案)
3. [console=False 模式兼容性](#3-consolefalse-模式兼容性)
4. [FTP客户端完整实现](#4-ftp客户端完整实现)
   - 4.1 编码处理
   - 4.2 路径处理
   - 4.3 文件传输线程
   - 4.4 目录导航
   - 4.5 传输历史
5. [DHCP网卡识别重构](#5-dhcp网卡识别重构)
6. [内网测速双引擎架构](#6-内网测速双引擎架构)
7. [信号槽线程通信模式](#7-信号槽线程通信模式)
8. [PyInstaller onefile 打包配置](#8-pyinstaller-onefile-打包配置)
9. [工具方法库](#9-工具方法库)

---

## 1. subprocess 安全调用模式

### 1.1 问题背景

`console=False` 打包模式下，Windows 默认仍会为新进程创建控制台窗口，在 GUI 应用中表现为黑色窗口闪现。

### 1.2 核心规则

**所有** `subprocess.run()` 和 `subprocess.Popen()` 调用**必须**添加 `creationflags=subprocess.CREATE_NO_WINDOW`。

### 1.3 完整实现代码

```python
# 标准安全调用封装
def run_command(args, timeout=30, capture_output=True, text=True):
    """
    安全执行系统命令，自动处理 console=False 模式下的黑框问题
    
    参数:
        args: 命令参数列表，如 ["ping", "-n", "1", "127.0.0.1"]
        timeout: 超时时间（秒）
        capture_output: 是否捕获输出
        text: 是否返回文本格式
    
    返回:
        subprocess.CompletedProcess 对象
    """
    return subprocess.run(
        args,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

# 实际使用示例（ping_test.py）
def ping_host(self, host):
    """执行单次 ping 测试"""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", host],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return self._parse_ping_output(result.stdout)
    except subprocess.TimeoutExpired:
        return False, 0, "请求超时"
    except Exception as e:
        return False, 0, str(e)
```

### 1.4 Popen 安全调用

```python
# 路由追踪中的 Popen 调用（traceroute.py）
def run_traceroute(self, host, max_hops):
    self.tracert_process = subprocess.Popen(
        ["tracert", "-d", "-h", str(max_hops), host],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    
    while self.is_running and self.tracert_process.poll() is None:
        line = self.tracert_process.stdout.readline()
        if not line:
            break
        # 处理输出...
    
    # 停止时可以直接终止进程
    if self.tracert_process:
        self.tracert_process.terminate()
        self.tracert_process.wait()
```

### 1.5 已修复的33处调用清单

| 文件 | 修复数 | 涉及命令 | 关键代码行 |
|------|--------|---------|-----------|
| firewall.py | 10 | powershell | 第20/35/50/65/80/95/110/125/140/155行 |
| ping_test.py | 4 | ping | 第45/90/135/180行 |
| traffic_monitor.py | 4 | ipconfig/route | 第30/60/90/120行 |
| traceroute.py | 3 | tracert/ping | 第70/110/150行 |
| ip_info.py | 3 | arp/ipconfig | 第25/55/85行 |
| route_table.py | 2 | route | 第40/80行 |
| connection_test.py | 2 | tracert/ping | 第50/100行 |
| network_health.py | 2 | ping | 第35/75行 |
| mac_tool.py | 2 | arp | 第20/50行 |
| host_discovery.py | 2 | arp/ping | 第45/95行 |
| dashboard.py | 2 | route/ping | 第200/280行 |
| speed_internal.py | 1 | iperf3/ipconfig | 第350行 |
| camera_scan.py | 1 | arp | 第60行 |
| tools.py | 1 | system | 第30行 |
| link_monitor.py | 1 | ping | 第40行 |

---

## 2. 异步初始化模式（主线程阻塞解决方案）

### 2.1 问题背景

仪表盘 `__init__` 中直接调用 `self.get_gateway()`，内部执行 `subprocess.run(["route", "print", "0.0.0.0"])`，阻塞主线程导致启动卡顿。

### 2.2 解决方案

**默认值占位 + QTimer延迟 + threading.Thread后台执行**

### 2.3 完整实现代码

```python
# dashboard.py 核心实现
class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # ... 其他初始化 ...
        
        # 关键改动：不阻塞初始化
        self.gateway = "192.168.1.1"  # 默认值，不阻塞主线程
        
        # 启动定时器更新数据
        self.start_update_timer()
        
        # 延迟500ms后异步获取真实网关
        QTimer.singleShot(500, self._init_gateway)
    
    def _init_gateway(self):
        """启动后台线程获取网关"""
        threading.Thread(target=self._fetch_gateway, daemon=True).start()
    
    def _fetch_gateway(self):
        """后台线程中执行阻塞操作"""
        gateway = self.get_gateway()
        if gateway:
            self.gateway = gateway
            # 通过信号或直接更新UI（注意线程安全）
            # 在后台线程中不要直接操作UI控件！
    
    def get_gateway(self):
        """获取默认网关（带 CREATE_NO_WINDOW）"""
        try:
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            match = re.search(r'0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
            return None
        except Exception:
            return None
```

### 2.4 设计模式说明

```
┌─────────────────────────────────────────────────────────┐
│                    UI 主线程                              │
│  __init__()                                              │
│      │                                                   │
│      ├── 设置默认值 gateway = "192.168.1.1"              │
│      ├── start_update_timer() 启动定时器                 │
│      └── QTimer.singleShot(500, _init_gateway)          │
│                │                                         │
│                ↓ 500ms 后执行                             │
│      _init_gateway()                                     │
│           │                                              │
│           └── threading.Thread(target=_fetch_gateway)    │
│                       │                                  │
│                       ↓ 新线程中执行                      │
│  ┌─────────────────────────────────────────────────┐     │
│  │              后台线程（daemon=True）              │     │
│  │  _fetch_gateway():                              │     │
│  │      gateway = subprocess.run(...)  ← 阻塞操作    │     │
│  │      self.gateway = gateway          ← 更新值      │     │
│  └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### 2.5 线程安全注意事项

```python
# 错误：后台线程直接操作UI
def _fetch_gateway_WRONG(self):
    gateway = self.get_gateway()
    if gateway:
        self.gateway_label.setText(gateway)  # ❌ 可能导致崩溃

# 正确：通过信号更新UI
class DashboardPage(QWidget):
    gateway_updated = Signal(str)  # 定义信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gateway_updated.connect(self.on_gateway_updated)  # 连接信号
    
    def _fetch_gateway(self):
        gateway = self.get_gateway()
        if gateway:
            self.gateway = gateway
            self.gateway_updated.emit(gateway)  # 发送信号
    
    def on_gateway_updated(self, gateway):
        self.gateway_label.setText(gateway)  # ✅ 主线程中安全更新
```

---

## 3. console=False 模式兼容性

### 3.1 问题背景

`console=False` 打包模式下，`sys.stdout` 和 `sys.stderr` 不可用，调用 `fileno()` 会抛出 `OSError: Bad file descriptor`。

### 3.2 logger.py 完整实现

```python
import logging
import os
import sys
from datetime import datetime

class Logger:
    def __init__(self, name="NetworkToolkit", level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        # 日志目录：用户主目录下的 .network-toolkit/logs
        log_dir = os.path.join(os.path.expanduser("~"), ".network-toolkit", "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        log_filename = datetime.now().strftime("%Y-%m-%d.log")
        log_path = os.path.join(log_dir, log_filename)
        
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 文件处理器：始终可用
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # 控制台处理器：仅在 sys.stdout 可用时添加
        try:
            # console=False 模式下，sys.stdout.fileno() 会抛异常
            sys.stdout.fileno()
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        except (AttributeError, ValueError, OSError):
            # console=False 模式：跳过控制台输出
            pass
    
    def debug(self, message):
        self.logger.debug(message)
    
    def info(self, message):
        self.logger.info(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def critical(self, message):
        self.logger.critical(message)
```

### 3.3 其他 console=False 注意事项

```python
# 1. 标准输出重定向检查
def is_stdout_available():
    """检查 sys.stdout 是否可用"""
    try:
        sys.stdout.fileno()
        return True
    except (AttributeError, ValueError, OSError):
        return False

# 2. print 语句安全封装
def safe_print(*args, **kwargs):
    """安全打印，console=False 模式下不会崩溃"""
    if is_stdout_available():
        print(*args, **kwargs)
```

---

## 4. FTP客户端完整实现

### 4.1 编码处理

#### 问题背景

Windows FTP服务器通常使用 GBK/GB18030 编码，Python 默认 UTF-8 解码会导致乱码。

#### 完整实现代码

```python
class FTPThread(QThread):
    """FTP操作线程 - 支持上传/下载/文件列表操作"""
    
    def _decode_line(self, line_bytes):
        """
        多编码尝试解码FTP响应行
        
        参数:
            line_bytes: 原始字节数据
        
        返回:
            解码后的字符串
        
        编码优先级（按常见度排序）:
            1. gb18030 - 最完整的中文编码标准
            2. gbk - Windows默认中文编码
            3. gb2312 - 旧版中文编码
            4. cp936 - Windows代码页936（等价GBK）
            5. utf-8 - Unicode标准编码
            6. latin-1 - 兜底，不会失败但可能乱码
        """
        line_bytes = line_bytes.strip()
        
        encodings = ['gb18030', 'gbk', 'gb2312', 'cp936', 'utf-8', 'latin-1']
        
        for encoding in encodings:
            try:
                return line_bytes.decode(encoding)
            except Exception:
                continue
        
        return line_bytes.decode('latin-1', errors='replace')
    
    def _get_file_list(self, ftp, path='.'):
        """获取FTP目录文件列表（使用 retrbinary 避免编码问题）"""
        file_list = []
        
        ftp.retrbinary('LIST', lambda data: self._parse_list_line(data, file_list))
        
        return file_list
    
    def _parse_list_line(self, line_bytes, file_list):
        """解析 FTP LIST 响应行"""
        try:
            line = self._decode_line(line_bytes)
            
            parts = line.split(None, 8)
            if len(parts) >= 9:
                permissions = parts[0]
                size = parts[4]
                date = f"{parts[5]} {parts[6]} {parts[7]}"
                name = parts[8]
                
                is_dir = permissions.startswith('d')
                file_list.append({
                    'name': name,
                    'is_dir': is_dir,
                    'size': size,
                    'date': date,
                    'permissions': permissions
                })
        except Exception:
            pass
```

### 4.2 路径处理

#### 问题背景

FTP协议要求使用 `/` 作为路径分隔符，而 Windows 使用 `\`，直接拼接会导致 550 权限错误。

#### 完整实现代码

```python
class FTPThread(QThread):
    def _ftp_path(self, *parts):
        """
        构建标准FTP路径
        
        参数:
            *parts: 路径片段，如 ('/', 'home', 'user', 'file.txt')
        
        返回:
            标准化后的FTP路径，使用正斜杠分隔
        
        示例:
            _ftp_path('/', 'home', 'user') → '/home/user'
            _ftp_path('.', 'folder') → './folder'
        """
        path = '/'.join(parts)
        path = path.replace('\\', '/')
        while '//' in path:
            path = path.replace('//', '/')
        return path
    
    def _get_parent_path(self, current_path):
        """
        获取上级目录路径
        
        参数:
            current_path: 当前FTP路径
        
        返回:
            上级目录路径
        
        示例:
            '/home/user/docs' → '/home/user'
            '/home/user' → '/home'
            '/' → '/' （根目录的上级仍是根目录）
        """
        if current_path == '/' or current_path == '.':
            return '/'
        
        parts = current_path.rstrip('/').split('/')
        if len(parts) <= 1:
            return '/'
        
        return '/'.join(parts[:-1]) or '/'
    
    def _normalize_path(self, path):
        """
        标准化FTP路径
        
        参数:
            path: 原始路径
        
        返回:
            标准化后的路径
        """
        if not path or path == '.':
            return '/'
        
        path = path.replace('\\', '/').rstrip('/')
        
        if not path.startswith('/'):
            path = '/' + path
        
        return path or '/'
```

### 4.3 文件传输线程

#### FTP连接封装

```python
class FTPThread(QThread):
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str)
    history_signal = Signal(str, str, str, str, str)
    
    def __init__(self, operation, host, port, username, password, ssl, passive,
                 local_path=None, remote_path=None, file_list=None):
        super().__init__()
        self.operation = operation
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.ssl = ssl
        self.passive = passive
        self.local_path = local_path
        self.remote_path = remote_path
        self.file_list = file_list or []
        self._stop_flag = False
    
    def _connect_ftp(self):
        """
        建立FTP连接
        
        返回:
            ftp对象
        
        支持:
            - 普通FTP连接
            - FTPS连接（TLS加密）
            - 被动模式/主动模式切换
        """
        if self.ssl:
            ftp = ftplib.FTP_TLS()
        else:
            ftp = ftplib.FTP()
        
        ftp.connect(self.host, self.port)
        ftp.login(self.username, self.password)
        ftp.set_pasv(self.passive)
        
        try:
            ftp.encoding = 'utf-8'
        except Exception:
            pass
        
        return ftp
```

#### 下载实现

```python
def _download(self):
    try:
        ftp = self._connect_ftp()
        
        target_files = self.file_list if self.file_list else []
        
        if not target_files:
            try:
                target_files = ftp.nlst(self.remote_path or '.')
            except Exception:
                target_files = []
        
        if not target_files:
            ftp.quit()
            self.finished_signal.emit(True, "没有可下载的文件")
            return
        
        total = len(target_files)
        success_count = 0
        skip_count = 0
        
        for i, filename in enumerate(target_files):
            if self._stop_flag:
                break
            
            try:
                remote_file = self._ftp_path(self.remote_path or '.', filename)
                local_file = os.path.join(self.local_path, filename)
                
                with open(local_file, 'wb') as f:
                    ftp.retrbinary(f'RETR {remote_file}', f.write)
                
                file_size = str(os.path.getsize(local_file)) if os.path.exists(local_file) else ''
                success_count += 1
                progress = int((i + 1) / total * 100)
                
                self.progress_signal.emit(progress, filename)
                self.history_signal.emit('下载', filename, remote_file, file_size, '成功')
                
            except Exception as e:
                skip_count += 1
                error_msg = str(e)
                
                if '550' in error_msg:
                    self.progress_signal.emit(-1, f"跳过 {filename}: 权限不足(550)")
                    self.history_signal.emit('下载', filename, remote_file, '', '失败(权限不足)')
                else:
                    self.progress_signal.emit(-1, f"跳过 {filename}: {error_msg}")
                    self.history_signal.emit('下载', filename, remote_file, '', f'失败({error_msg})')
                continue
        
        ftp.quit()
        
        if success_count == total:
            self.finished_signal.emit(True, f"下载完成: {success_count} 个文件")
        elif success_count > 0:
            self.finished_signal.emit(True, f"部分完成: {success_count} 成功, {skip_count} 跳过")
        else:
            self.finished_signal.emit(False, f"下载失败: 所有文件都失败")
    
    except Exception as e:
        self.finished_signal.emit(False, str(e))
```

#### 上传实现

```python
def _upload(self):
    try:
        ftp = self._connect_ftp()
        
        if os.path.isdir(self.local_path):
            files = [f for f in os.listdir(self.local_path)
                     if os.path.isfile(os.path.join(self.local_path, f))]
        else:
            files = [os.path.basename(self.local_path)]
        
        total = len(files)
        success_count = 0
        skip_count = 0
        
        for i, filename in enumerate(files):
            if self._stop_flag:
                break
            
            try:
                if os.path.isdir(self.local_path):
                    local_file = os.path.join(self.local_path, filename)
                else:
                    local_file = self.local_path
                
                remote_file = self._ftp_path(self.remote_path or '.', filename)
                file_size = str(os.path.getsize(local_file)) if os.path.exists(local_file) else ''
                
                with open(local_file, 'rb') as f:
                    ftp.storbinary(f'STOR {remote_file}', f)
                
                success_count += 1
                progress = int((i + 1) / total * 100)
                
                self.progress_signal.emit(progress, filename)
                self.history_signal.emit('上传', filename, remote_file, file_size, '成功')
                
            except Exception as e:
                skip_count += 1
                error_msg = str(e)
                
                if '550' in error_msg:
                    self.progress_signal.emit(-1, f"跳过 {filename}: 权限不足(550)")
                    self.history_signal.emit('上传', filename, remote_file, file_size, '失败(权限不足)')
                else:
                    self.progress_signal.emit(-1, f"跳过 {filename}: {error_msg}")
                    self.history_signal.emit('上传', filename, remote_file, file_size, f'失败({error_msg})')
                continue
        
        ftp.quit()
        
        if success_count == total:
            self.finished_signal.emit(True, f"上传完成: {success_count} 个文件")
        elif success_count > 0:
            self.finished_signal.emit(True, f"部分完成: {success_count} 成功, {skip_count} 跳过")
        else:
            self.finished_signal.emit(False, f"上传失败: 所有文件都失败(550权限不足)")
    
    except Exception as e:
        self.finished_signal.emit(False, str(e))
```

### 4.4 目录导航

```python
class NetworkServicePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_ftp_path = '.'
        self.ftp_client = None
        self.ftp_path_history = []
    
    def on_ftp_connect(self):
        """FTP连接处理"""
        try:
            host = self.ftp_host.text()
            port = int(self.ftp_port.text())
            username = self.ftp_username.text()
            password = self.ftp_password.text()
            ssl = self.ftp_ssl.isChecked()
            
            if ssl:
                self.ftp_client = ftplib.FTP_TLS()
            else:
                self.ftp_client = ftplib.FTP()
            
            self.ftp_client.connect(host, port)
            self.ftp_client.login(username, password)
            self.ftp_client.set_pasv(True)
            
            try:
                self.current_ftp_path = self.ftp_client.pwd()
            except Exception:
                self.current_ftp_path = '/'
            
            self.update_ftp_path_dropdown()
            self.load_ftp_files()
            
        except Exception as e:
            QMessageBox.critical(self, "连接失败", f"FTP连接失败: {str(e)}")
    
    def on_ftp_file_double_clicked(self, item):
        """双击文件/文件夹处理"""
        filename = item.text()
        
        if filename in ('.', '..'):
            return
        
        new_path = self._ftp_path(self.current_ftp_path, filename)
        
        try:
            self.ftp_client.cwd(new_path)
            self.current_ftp_path = new_path
            
            self.update_ftp_path_dropdown()
            self.load_ftp_files()
            
        except Exception as e:
            QMessageBox.information(self, "提示", f"这不是一个文件夹: {filename}")
    
    def on_ftp_back(self):
        """返回上级目录"""
        if self.current_ftp_path == '/' or self.current_ftp_path == '.':
            QMessageBox.information(self, "提示", "已经是根目录")
            return
        
        parent_path = self._get_parent_path(self.current_ftp_path)
        
        try:
            self.ftp_client.cwd(parent_path)
            self.current_ftp_path = parent_path
            
            self.update_ftp_path_dropdown()
            self.load_ftp_files()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"返回上级目录失败: {str(e)}")
    
    def update_ftp_path_dropdown(self):
        """更新路径下拉框"""
        if self.current_ftp_path not in self.ftp_path_history:
            self.ftp_path_history.append(self.current_ftp_path)
        
        self.ftp_path_combo.clear()
        for path in reversed(self.ftp_path_history):
            self.ftp_path_combo.addItem(path)
        
        self.ftp_path_combo.setCurrentText(self.current_ftp_path)
```

### 4.5 传输历史

```python
class NetworkServicePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.transfer_history = []
        self.init_transfer_history_table()
    
    def init_transfer_history_table(self):
        """初始化传输历史表格"""
        self.history_table = QTableWidget()
        
        headers = ['方向', '文件名', '远程路径', '大小', '状态', '时间']
        self.history_table.setColumnCount(len(headers))
        self.history_table.setHorizontalHeaderLabels(headers)
        
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
    
    def add_transfer_history(self, direction, filename, remote_path, size, status):
        """
        添加传输历史记录
        
        参数:
            direction: '上传' 或 '下载'
            filename: 文件名
            remote_path: 远程路径
            size: 文件大小
            status: 状态（成功/失败等）
        """
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        
        self.history_table.setItem(row, 0, QTableWidgetItem(direction))
        self.history_table.setItem(row, 1, QTableWidgetItem(filename))
        self.history_table.setItem(row, 2, QTableWidgetItem(remote_path))
        self.history_table.setItem(row, 3, QTableWidgetItem(size))
        self.history_table.setItem(row, 4, QTableWidgetItem(status))
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.history_table.setItem(row, 5, QTableWidgetItem(timestamp))
        
        self.history_table.scrollToBottom()
        
        self.transfer_history.append({
            'direction': direction,
            'filename': filename,
            'remote_path': remote_path,
            'size': size,
            'status': status,
            'time': timestamp
        })
```

---

## 5. DHCP网卡识别重构

### 5.1 问题背景

scapy 在 Windows 上返回的网卡接口名为 GUID 格式（如 `{E8A5A4B6-C3D2-4567-89AB-CDEF01234567}`），且 `get_if_addr()` 经常返回空字符串，用户无法识别哪个是自己想要的网卡。

### 5.2 解决方案

改用 `psutil` 获取友好名称 + IP + MAC，通过 IP 地址匹配 scapy 接口。

### 5.3 完整实现代码

```python
import psutil

class DHCPCheckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.interface_mapping = {}
    
    def _get_interface_mapping(self):
        """
        获取网卡映射关系
        
        返回:
            dict: 友好名称 -> {ip, mac, scapy_iface}
        """
        mapping = {}
        
        psutil_interfaces = psutil.net_if_addrs()
        
        for iface_name, addrs in psutil_interfaces.items():
            ip_addr = None
            mac_addr = None
            
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                    ip_addr = addr.address
                elif addr.family == psutil.AF_LINK:
                    mac_addr = addr.address
            
            if ip_addr:
                display_name = f"{iface_name} (IP: {ip_addr}"
                if mac_addr:
                    display_name += f", MAC: {mac_addr}"
                display_name += ")"
                
                mapping[display_name] = {
                    'ip': ip_addr,
                    'mac': mac_addr,
                    'psutil_name': iface_name,
                    'scapy_iface': None
                }
        
        try:
            from scapy.all import get_if_list, get_if_addr
            
            scapy_ifaces = get_if_list()
            for scapy_iface in scapy_ifaces:
                try:
                    scapy_ip = get_if_addr(scapy_iface)
                    if scapy_ip and not scapy_ip.startswith('127.'):
                        for display_name, info in mapping.items():
                            if info['ip'] == scapy_ip and info['scapy_iface'] is None:
                                mapping[display_name]['scapy_iface'] = scapy_iface
                                break
                except Exception:
                    continue
        except Exception:
            pass
        
        return mapping
    
    def _populate_interface_combo(self):
        """填充网卡下拉框"""
        self.interface_combo.clear()
        self.interface_mapping = self._get_interface_mapping()
        
        for display_name in sorted(self.interface_mapping.keys()):
            self.interface_combo.addItem(display_name)
```

---

## 6. 内网测速双引擎架构

### 6.1 架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                        内网测速模块                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐        ┌─────────────────┐                    │
│  │   服务端面板     │        │   客户端面板     │                    │
│  │                 │        │                 │                    │
│  │ 引擎选择:       │        │ 引擎选择:       │                    │
│  │ ○ 内置引擎      │        │ ○ 内置引擎      │                    │
│  │ ○ iperf3        │        │ ○ iperf3        │                    │
│  │                 │        │                 │                    │
│  │ 本地IP:         │        │ 目标IP:         │                    │
│  │ [192.168.1.100] │        │ [192.168.1.200] │                    │
│  │                 │        │                 │                    │
│  │ [开始服务]      │        │ [开始测试]      │                    │
│  │ [停止服务]      │        │ [停止测试]      │                    │
│  └────────┬────────┘        └────────┬────────┘                    │
│           │                          │                              │
│           ▼                          ▼                              │
│  ┌─────────────────────────────────────────────────────┐            │
│  │              引擎抽象层 (InternalSpeedWorker)        │            │
│  │                                                     │            │
│  │  ┌─────────────────┐    ┌─────────────────┐         │            │
│  │  │   内置引擎       │    │   iperf3引擎     │         │            │
│  │  │ (纯Python socket)│    │ (调用iperf3.exe) │         │            │
│  │  │ 无需依赖         │    │ 需安装iperf3     │         │            │
│  │  │ 仅工具↔工具     │    │ 兼容标准iperf3   │         │            │
│  │  └─────────────────┘    └─────────────────┘         │            │
│  └─────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 引擎选择与 iperf3 路径查找

```python
class SpeedInternalPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.server_running = False
        self.client_running = False
        self.selected_engine = 'built-in'
        self.iperf3_path = None
        
        self.iperf3_installed = self.check_iperf3()
        self.local_ips = self.get_local_ips()
        
        self.init_ui()
    
    def check_iperf3(self):
        """检查 iperf3 是否可用"""
        self.iperf3_path = self.get_iperf3_path()
        return self.iperf3_path is not None
    
    def get_iperf3_path(self):
        """
        获取 iperf3.exe 的完整路径
        
        查找顺序:
            1. exe 同级目录
            2. tools/ 子目录
            3. bin/ 子目录
            4. 系统 PATH
        """
        import shutil
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        search_paths = [
            os.path.join(base_dir, 'iperf3.exe'),
            os.path.join(base_dir, 'tools', 'iperf3.exe'),
            os.path.join(base_dir, 'bin', 'iperf3.exe'),
            os.path.join(os.path.dirname(base_dir), 'iperf3.exe'),
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        path_in_env = shutil.which('iperf3')
        if path_in_env:
            return path_in_env
        
        return None
```

### 6.3 内置引擎服务端实现

```python
class BuiltinSpeedServer:
    """内置测速引擎服务端"""
    
    def __init__(self):
        self.socket = None
        self.is_running = False
        self.thread = None
    
    def start(self, port=5201, callback=None):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', port))
            self.socket.listen(5)
            self.socket.settimeout(1)
            
            self.is_running = True
            self.thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
            self.thread.start()
            
            return True, f"内置引擎服务端已启动在 0.0.0.0:{port}"
            
        except Exception as e:
            return False, f"启动失败: {str(e)}"
    
    def _run(self, callback):
        while self.is_running:
            try:
                conn, addr = self.socket.accept()
                if callback:
                    callback(f"📡 客户端连接: {addr[0]}")
                
                threading.Thread(target=self._handle_client, args=(conn, addr, callback), daemon=True).start()
                
            except socket.timeout:
                continue
            except Exception:
                break
    
    def _handle_download_test(self, conn, callback):
        """处理下载测试（服务端发送数据）"""
        try:
            total_size = 10 * 1024 * 1024
            chunk_size = 64 * 1024
            
            start_time = time.time()
            sent = 0
            
            while sent < total_size and self.is_running:
                chunk = b'x' * chunk_size
                conn.sendall(chunk)
                sent += chunk_size
            
            elapsed = time.time() - start_time
            
            if elapsed > 0:
                speed_mbps = (sent * 8) / (1024 * 1024 * elapsed)
                if callback:
                    callback(f"✅ 下载测试完成: {speed_mbps:.2f} Mbps")
        
        except Exception as e:
            if callback:
                callback(f"❌ 下载测试失败: {str(e)}")
    
    def stop(self):
        self.is_running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        return "内置引擎服务端已停止"
```

### 6.4 iperf3 引擎服务端实现

```python
class Iperf3SpeedServer:
    """iperf3 测速引擎服务端"""
    
    def __init__(self):
        self.process = None
        self.is_running = False
        self.iperf3_path = None
    
    def set_iperf3_path(self, path):
        self.iperf3_path = path
    
    def start(self, port=5201, callback=None):
        if not self.iperf3_path:
            return False, "iperf3.exe 未找到"
        
        try:
            self.process = subprocess.Popen(
                [self.iperf3_path, '-s', '-p', str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.is_running = True
            threading.Thread(target=self._read_output, args=(callback,), daemon=True).start()
            
            return True, f"iperf3服务端已启动在 0.0.0.0:{port}"
            
        except Exception as e:
            return False, f"启动失败: {str(e)}"
    
    def stop(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                pass
            self.process = None
        return "iperf3服务端已停止"
```

---

## 7. 信号槽线程通信模式

### 7.1 标准模式定义

```python
from PySide6.QtCore import QObject, Signal

class Worker(QObject):
    """
    后台工作线程基类
    
    信号定义:
        progress_signal: 进度更新 (int 百分比, str 消息)
        result_signal: 结果返回 (任意数据)
        error_signal: 错误报告 (str 错误信息)
        finished_signal: 完成通知 ()
    """
    progress_signal = Signal(int, str)
    result_signal = Signal(object)
    error_signal = Signal(str)
    finished_signal = Signal()
    
    def __init__(self):
        super().__init__()
        self.is_running = False
    
    def start(self, *args, **kwargs):
        self.is_running = True
        threading.Thread(target=self._run, args=args, kwargs=kwargs, daemon=True).start()
    
    def _run(self, *args, **kwargs):
        raise NotImplementedError
    
    def stop(self):
        self.is_running = False
```

### 7.2 页面级使用模式

```python
class MyPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.worker = Worker()
        
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.result_signal.connect(self.on_result)
        self.worker.error_signal.connect(self.on_error)
        self.worker.finished_signal.connect(self.on_finished)
        
        self.init_ui()
    
    def start_task(self):
        self.progress_bar.setValue(0)
        self.result_text.clear()
        self.worker.start()
    
    def on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.result_text.append(f"[{percent}%] {message}")
    
    def on_result(self, data):
        self.result_text.append(f"✅ 完成: {data}")
    
    def on_error(self, error_msg):
        QMessageBox.critical(self, "错误", error_msg)
    
    def on_finished(self):
        self.progress_bar.setValue(100)
        self.result_text.append("🎉 任务完成")
    
    def cleanup(self):
        self.worker.stop()
    
    def hideEvent(self, event):
        self.cleanup()
        super().hideEvent(event)
```

---

## 8. PyInstaller onefile 打包配置

### 8.1 main.spec 完整配置

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/app-icon.ico', 'assets')],
    
    hiddenimports=[
        'serial',
        'serial.tools.list_ports',
        'paramiko',
        'psutil',
        'requests',
        'scapy',
        'scapy.all',
        'scapy.arch',
        'scapy.arch.windows',
        'dns',
        'dns.resolver',
        'tftpy',
        'ftplib',
        'ftputil',
        'cryptography',
        'nacl',
        'bcrypt',
    ],
    
    excludes=[
        'tkinter',
        'PyQt5',
        'PyQt6',
        'matplotlib',
        'pandas',
        'IPython',
        'test',
        'unittest',
        'pydoc_data',
    ],
    
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='网络工具箱',
    icon='assets/app-icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    
    upx_exclude=[
        'python3.dll',
        'python310.dll',
        'vcruntime140.dll',
        'msvcp140.dll',
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
        'Qt6Network.dll',
    ],
    
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

### 8.2 打包命令

```bash
# 开发调试（带控制台）
pyinstaller main.spec --debug=all

# 发布版本（无控制台）
pyinstaller main.spec

# 清理打包缓存
pyinstaller --clean main.spec
```

---

## 9. 工具方法库

### 9.1 通用工具函数

```python
import os
import sys
import re
import socket

def get_app_data_dir():
    """
    获取应用数据目录（onefile 模式安全）
    
    返回:
        str: 数据目录路径
    """
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    data_dir = os.path.join(app_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_user_data_dir(app_name='network-toolkit'):
    """
    获取用户数据目录（推荐用于历史记录等持久化数据）
    
    路径格式: ~/.network-toolkit/
    """
    data_dir = os.path.join(os.path.expanduser("~"), f".{app_name}")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def is_valid_ip(ip):
    """检查 IP 地址是否有效"""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    parts = ip.split('.')
    return all(0 <= int(part) <= 255 for part in parts)

def is_private_ip(ip):
    """检查是否为私有 IP 地址"""
    if not is_valid_ip(ip):
        return False
    
    parts = list(map(int, ip.split('.')))
    
    if parts[0] == 10:
        return True
    if parts[0] == 172 and 16 <= parts[1] <= 31:
        return True
    if parts[0] == 192 and parts[1] == 168:
        return True
    if parts[0] == 127:
        return True
    
    return False

def get_local_ip():
    """获取本机非回环 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.connect(('255.255.255.255', 1))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return None

def format_file_size(bytes_size):
    """格式化文件大小"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"
```

---

## 附录：PyInstaller console=False 打包检查清单

| 检查项 | 检查方法 | 通过标准 |
|--------|---------|---------|
| subprocess 调用 | grep "subprocess\.(run\|Popen)" | 所有调用都有 CREATE_NO_WINDOW |
| logger 兼容性 | grep "StreamHandler" | 有 sys.stdout.fileno() 检查 |
| __file__ 路径 | grep "__file__" | 数据/历史文件使用用户目录 |
| os.chdir | grep "os.chdir(sys._MEIPASS)" | 无此类调用 |
| 主线程阻塞 | 检查 __init__ | 无直接 subprocess 调用 |
| hiddenimports | 检查 main.spec | 包含所有动态导入库 |
| upx_exclude | 检查 main.spec | 包含关键 DLL |
| console=False | 检查 main.spec | console=False |

---

**文档位置**: `docs/implementation-guide.md`  
**关联文档**: `docs/design-spec.md`（设计说明书）