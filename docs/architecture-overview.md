# 网络测试工具箱 - 项目架构说明文档

## 版本信息
- **版本**: V1.2
- **日期**: 2026-07-23
- **作者**: 网络测试工具箱开发团队

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [项目目录结构](#3-项目目录结构)
4. [核心架构设计](#4-核心架构设计)
5. [模块详细说明](#5-模块详细说明)
6. [关键技术实现](#6-关键技术实现)
7. [页面功能矩阵](#7-页面功能矩阵)
8. [数据流与通信机制](#8-数据流与通信机制)
9. [打包与部署](#9-打包与部署)
10. [扩展开发指南](#10-扩展开发指南)

---

## 1. 项目概述

**网络测试工具箱**是一款基于 Python + PySide6 开发的综合性网络测试与诊断工具，提供一站式网络运维解决方案。

### 核心价值

| 维度 | 说明 |
|------|------|
| **功能覆盖** | 20+ 网络测试工具，涵盖诊断、测速、分析、服务、监控、远程等六大领域 |
| **用户体验** | 统一的现代化 UI，实时数据展示，操作简单直观 |
| **性能优化** | 异步初始化模式，避免主线程阻塞；后台线程执行耗时操作 |
| **打包兼容** | 支持 PyInstaller onefile 打包，console=False 模式下无黑框闪烁 |
| **跨平台** | 基于 Python，理论支持 Windows/macOS/Linux（当前主要适配 Windows） |

---

## 2. 技术栈

### 核心框架

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 开发语言 |
| PySide6 | 6.7.2 | GUI 框架 |
| psutil | 5.9.8 | 系统信息采集 |
| scapy | 2.5.0 | 数据包捕获与分析 |
| requests | 2.31.0 | HTTP 请求 |
| matplotlib | 3.7.5 | 数据可视化 |
| pyqtgraph | 0.13.7 | 实时图表 |
| pyserial | 3.5 | 串口通信 |
| paramiko | 3.4.0 | SSH 客户端 |
| dnspython | 2.4.2 | DNS 查询 |

### 可选依赖

| 组件 | 用途 | 状态 |
|------|------|------|
| pyftpdlib | FTP 服务端 | 运行时按需加载 |
| tftpy | TFTP 服务端 | 运行时按需加载 |
| iperf3 | 内网测速引擎 | 外部工具 |

---

## 3. 项目目录结构

```
project_03_network-testing-toolkit/
├── main.py                    # 应用入口
├── requirements.txt           # 依赖清单
├── main.spec                  # PyInstaller 打包配置
├── app/
│   ├── __init__.py
│   ├── main_window.py         # 主窗口框架
│   ├── core/                  # 核心模块
│   │   ├── __init__.py
│   │   ├── config.py          # 配置管理
│   │   ├── logger.py          # 日志系统
│   │   ├── permission.py      # 权限检查
│   │   └── thread_pool.py     # 线程池管理
│   ├── ui/                    # 页面模块（25个页面）
│   │   ├── dashboard.py       # 仪表盘
│   │   ├── ping_test.py       # Ping测试
│   │   ├── traceroute.py      # 路由追踪
│   │   ├── port_scan.py       # 端口扫描
│   │   ├── host_discovery.py  # 主机发现
│   │   ├── speed_internal.py  # 内网测速
│   │   ├── speed_external.py  # 外网测速
│   │   ├── network_service.py # 网络服务(FTP/HTTP/TFTP)
│   │   ├── dhcp_check.py      # DHCP检测
│   │   ├── firewall.py        # 防火墙配置
│   │   ├── ...                # 其他页面
│   ├── widgets/               # 自定义控件
│   │   └── __init__.py
│   └── data/                  # 数据文件
│       ├── ssh_history.json   # SSH连接历史
│       └── rdp_history.json   # RDP连接历史
├── assets/                    # 资源文件
│   ├── app-icon.ico           # 应用图标
│   └── ui-screenshots/        # UI截图
├── docs/                      # 文档
│   ├── design-spec.md         # 设计说明书
│   ├── implementation-guide.md # 实现指南
│   └── architecture-overview.md # 架构说明（本文档）
└── scripts/                   # 测试脚本
    ├── _test_ping_parser.py
    ├── _test_subnet_scan.py
    └── _test_traceroute_format.py
```

---

## 4. 核心架构设计

### 4.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py (入口)                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  异常捕获 → 配置加载 → 权限检查 → QApplication 创建       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MainWindow (主窗口)                          │
│  ┌───────────────┐    ┌─────────────────────────────────────┐  │
│  │   Sidebar     │    │         Content Area                │  │
│  │   (导航菜单)   │    │  ┌─────────────────────────────┐   │  │
│  │               │    │  │   当前页面 Widget              │   │  │
│  │  • 概览       │    │  │   (根据导航动态加载)           │   │  │
│  │  • 诊断检测   │    │  │                               │   │  │
│  │  • 速度测试   │    │  │   - DashboardPage             │   │  │
│  │  • 网络分析   │    │  │   - PingTestPage              │   │  │
│  │  • 实用工具   │    │  │   - SpeedInternalPage         │   │  │
│  │  • 网络服务   │    │  │   - NetworkServicePage        │   │  │
│  │  • 监控运维   │    │  │   - ... (25个页面)            │   │  │
│  │  • 远程工具   │    │  └─────────────────────────────┘   │  │
│  │  • 智能系统   │    └─────────────────────────────────────┘  │
│  └───────────────┘                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    StatusBar (状态栏)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Modules (核心模块)                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ ConfigMgr  │ │  Logger    │ │ AdminCheck │ │ ThreadPool │   │
│  │ 配置管理   │ │  日志系统   │ │  权限检查   │ │  线程池    │   │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 架构设计原则

| 原则 | 说明 |
|------|------|
| **单一职责** | 每个页面模块负责单一功能，核心模块提供通用服务 |
| **分层架构** | UI层 → 业务层 → 核心服务层，职责清晰分离 |
| **事件驱动** | 基于 Qt 信号槽机制，实现组件解耦 |
| **异步执行** | 耗时操作在后台线程执行，避免阻塞 UI |
| **资源管理** | 页面切换时自动调用 cleanup 方法释放资源 |

---

## 5. 模块详细说明

### 5.1 入口模块 (main.py)

**职责**：应用启动入口，初始化环境，创建主窗口。

**核心流程**：
1. 全局异常捕获注册
2. 日志系统初始化
3. 配置文件加载
4. 管理员权限检查
5. QApplication 创建并设置字体
6. 主窗口创建并显示

**关键代码**：
```python
def main():
    logger = Logger()
    logger.info("网络测试工具箱启动...")
    
    config = ConfigManager()
    config.load()
    
    if not AdminChecker.is_admin():
        logger.warning("当前非管理员权限运行，部分功能可能受限")
    
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
```

### 5.2 主窗口模块 (app/main_window.py)

**职责**：主窗口框架，管理侧边栏导航和页面切换。

**核心组件**：

| 组件 | 类名 | 功能 |
|------|------|------|
| 侧边栏 | `QFrame` | 包含导航菜单和权限状态 |
| 导航分组 | `NavGroupButton` | 可折叠的功能分组按钮 |
| 导航项 | `NavItemButton` | 具体页面导航按钮 |
| 内容区域 | `QFrame` | 动态加载页面的容器 |
| 状态栏 | `QStatusBar` | 显示当前页面和网络状态 |

**页面切换机制**：
```python
def switch_page(self, page_key, page_class, page_name=None):
    # 1. 更新导航按钮状态
    for btn, key in self.all_nav_buttons:
        btn.setChecked(key == page_key)
    
    # 2. 清理当前页面（防止后台线程泄漏）
    if self.current_page:
        for cleanup_method in ['cleanup', 'stop_all', 'stop_update_timer']:
            if hasattr(self.current_page, cleanup_method):
                getattr(self.current_page, cleanup_method)()
                break
        self.current_page.deleteLater()
    
    # 3. 创建新页面
    self.current_page = page_class(self)
    self.page_layout.addWidget(self.current_page)
```

### 5.3 核心服务模块

#### 5.3.1 配置管理 (app/core/config.py)

**职责**：统一管理应用配置，支持持久化存储。

**配置结构**：
```python
{
    "app": { "theme", "language", "auto_update" },      # 应用设置
    "dashboard": { "update_interval", "show_cpu" },     # 仪表盘配置
    "ping": { "default_count", "default_timeout" },     # Ping测试配置
    "port_scan": { "default_threads", "common_ports" }, # 端口扫描配置
    "speed_test": { "server_list", "iperf3_path" },     # 测速配置
    "ui": { "window_width", "splitter_position" }       # UI配置
}
```

**特性**：
- 配置文件存储于 `~/.network-toolkit/config.json`
- 支持嵌套键值访问 (`config.get("ping.default_count")`)
- 配置合并策略：保留用户自定义值，合并新增配置项

#### 5.3.2 日志系统 (app/core/logger.py)

**职责**：统一日志管理，支持文件和控制台输出。

**特性**：
- 日志文件存储于 `~/.network-toolkit/logs/YYYY-MM-DD.log`
- 支持 console=False 模式（检查 sys.stdout.fileno() 可用性）
- 自动按日期分割日志文件
- 格式化输出：`[时间] - [级别] - [消息]`

**关键代码**：
```python
def _setup_handlers(self):
    # 文件处理器
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器（仅在可用时）
    try:
        sys.stdout.fileno()  # 检查stdout是否可用
        console_handler = logging.StreamHandler()
        self.logger.addHandler(console_handler)
    except (AttributeError, ValueError, OSError):
        pass  # console=False模式下跳过
```

#### 5.3.3 权限检查 (app/core/permission.py)

**职责**：Windows 管理员权限检测与提权。

**核心方法**：

| 方法 | 功能 |
|------|------|
| `is_admin()` | 检测当前是否为管理员权限 |
| `run_as_admin()` | 以管理员身份重新启动程序 |
| `require_admin()` | 装饰器，要求管理员权限 |

**使用场景**：
- 防火墙配置页面需要管理员权限
- 数据包捕获需要管理员权限
- 路由表修改需要管理员权限

#### 5.3.4 线程池管理 (app/core/thread_pool.py)

**职责**：提供统一的线程管理服务。

**核心组件**：

| 类 | 功能 |
|----|------|
| `Worker` | Qt信号槽模式的工作器，用于线程安全的数据传递 |
| `TaskThread` | 封装耗时任务的线程类 |
| `ThreadPool` | 单例线程池，基于 concurrent.futures |

**使用模式**：
```python
# 方式1：使用线程池
thread_pool = ThreadPool()
thread_pool.run_in_thread(func, callback=on_result)

# 方式2：使用TaskThread
thread = TaskThread(func, arg1, arg2)
thread.result_ready.connect(callback)
thread.start()
```

---

## 6. 关键技术实现

### 6.1 subprocess 安全调用模式

**问题背景**：PyInstaller console=False 打包后，subprocess 调用会弹出黑色控制台窗口。

**解决方案**：所有 subprocess 调用添加 `creationflags=subprocess.CREATE_NO_WINDOW`。

**标准封装**：
```python
result = subprocess.run(
    ["ping", "-n", "1", host],
    capture_output=True,
    text=True,
    timeout=5,
    creationflags=subprocess.CREATE_NO_WINDOW  # 关键参数
)
```

**修复范围**：33处 subprocess 调用，涉及15个文件。

### 6.2 异步初始化模式

**问题背景**：仪表盘在 `__init__` 中直接调用 subprocess 获取网关，阻塞主线程导致启动卡顿。

**解决方案**：使用 QTimer 延迟初始化 + threading.Thread 后台执行。

**实现代码**：
```python
def __init__(self):
    self.gateway = "192.168.1.1"  # 默认值，不阻塞
    QTimer.singleShot(500, self._init_gateway)  # 延迟500ms启动

def _init_gateway(self):
    threading.Thread(target=self._fetch_gateway, daemon=True).start()

def _fetch_gateway(self):
    gateway = self.get_gateway()
    if gateway:
        self.gateway = gateway  # 后台线程更新值
```

### 6.3 FTP客户端实现

**核心组件**：

| 类 | 功能 |
|----|------|
| `FTPThread` | FTP操作线程，支持上传/下载 |
| `FTPHandler` | FTP服务端处理器 |
| `NetworkServicePage` | 网络服务主页面 |

**关键特性**：

1. **编码处理**：多编码尝试解码，解决中文文件名乱码
   ```python
   def _decode_line(self, line_bytes):
       for encoding in ['gb18030', 'gbk', 'gb2312', 'cp936', 'utf-8', 'latin-1']:
           try:
               return line_bytes.decode(encoding)
           except Exception:
               continue
   ```

2. **路径统一**：使用正斜杠作为路径分隔符
   ```python
   def _ftp_path(self, *parts):
       return '/'.join(parts).replace('\\', '/')
   ```

3. **传输历史**：信号槽机制记录每笔传输
   ```python
   history_signal = Signal(str, str, str, str, str)  # 方向, 文件名, 远程路径, 大小, 状态
   ```

### 6.4 内网测速双引擎架构

**架构设计**：

```
┌────────────────────────────────────────────────────┐
│              SpeedInternalPage                     │
│  ┌────────────────┐    ┌───────────────────────┐   │
│  │   服务端模式    │    │      客户端模式       │   │
│  │  ┌──────────┐  │    │  ┌─────────────────┐  │   │
│  │  │ 内置引擎 │  │    │  │   内置引擎       │  │   │
│  │  │(socket) │  │    │  │   (socket)       │  │   │
│  │  └──────────┘  │    │  └─────────────────┘  │   │
│  │  ┌──────────┐  │    │  ┌─────────────────┐  │   │
│  │  │ iperf3   │  │    │  │   iperf3引擎     │  │   │
│  │  │(外部命令)│  │    │  │   (外部命令)     │  │   │
│  │  └──────────┘  │    │  └─────────────────┘  │   │
│  └────────────────┘    └───────────────────────┘   │
└────────────────────────────────────────────────────┘
```

**引擎选择逻辑**：
- 服务端和客户端必须使用相同引擎
- iperf3 路径自动查找：exe同级目录 → tools/ → bin/ → 系统PATH
- 内置引擎基于纯 Python socket，无需外部依赖

### 6.5 DHCP网卡识别重构

**问题背景**：scapy 返回 GUID 格式接口名（如 `{ABCD-1234-...}`），用户无法识别。

**解决方案**：改用 psutil 获取友好名称，通过 IP 地址匹配 scapy 接口。

**实现思路**：
1. 使用 `psutil.net_if_addrs()` 获取网卡友好名称和IP
2. 使用 `psutil.net_if_stats()` 获取网卡状态
3. 通过 IP 地址匹配 scapy 的接口对象

---

## 7. 页面功能矩阵

### 7.1 页面分类总览

| 分类 | 页面 | 文件 | 功能描述 |
|------|------|------|----------|
| **概览** | 仪表盘 | `dashboard.py` | 系统状态总览，CPU/内存/磁盘/网络实时监控 |
| **诊断检测** | 网络健康 | `network_health.py` | 综合网络健康检测 |
| | Ping测试 | `ping_test.py` | 单个/持续/批量/网段/TCP Ping |
| | 路由追踪 | `traceroute.py` | 逐跳显示路由路径 |
| | 端口扫描 | `port_scan.py` | TCP/UDP端口扫描 |
| | 主机发现 | `host_discovery.py` | 局域网主机扫描 |
| | 摄像头扫描 | `camera_scan.py` | RTSP/ONVIF摄像头检测 |
| **速度测试** | 外网测速 | `speed_external.py` | 基于Speedtest的外网测速 |
| | 内网测速 | `speed_internal.py` | 双引擎内网测速 |
| | 会话测试 | `speed_session.py` | 网络会话质量测试 |
| **网络分析** | 数据包抓包 | `packet_capture.py` | scapy数据包捕获 |
| | 协议分析 | `protocol_analysis.py` | 网络协议深度分析 |
| | DHCP检测 | `dhcp_check.py` | DHCP服务检测 |
| **实用工具** | 子网计算 | `subnet_calc.py` | IP子网掩码计算 |
| | IP信息检测 | `ip_info.py` | IP地理位置查询 |
| | MAC地址工具 | `mac_tool.py` | MAC厂商查询/格式化 |
| | 路由表 | `route_table.py` | 系统路由表查看 |
| | 连接测试 | `connection_test.py` | DNS/HTTP连接测试 |
| **网络服务** | 网络服务 | `network_service.py` | FTP客户端/服务、HTTP服务、TFTP服务 |
| | 本机设置 | `local_settings.py` | 本机网络配置 |
| | 防火墙配置 | `firewall.py` | Windows防火墙规则管理 |
| **监控运维** | 链路监控 | `link_monitor.py` | 网络链路状态监控 |
| | 流量监控 | `traffic_monitor.py` | 实时流量统计 |
| **远程工具** | 远程终端 | `remote_terminal.py` | SSH终端连接 |
| | 远程桌面 | `remote_desktop.py` | RDP远程桌面 |
| | 串口调试 | `serial_debug.py` | 串口数据收发 |
| **智能系统** | 关于和支持 | `about.py` | 软件信息和帮助 |

### 7.2 核心页面详细说明

#### 仪表盘 (DashboardPage)

**功能**：系统状态总览面板

**组件**：
- `StatCard`：统计卡片，包含标题、数值、迷你图表
- `MiniChart`：轻量级折线图，实时数据可视化
- `ConnectionCheckWidget`：连通性检测（网关/DNS/互联网）
- 快速启动按钮：一键跳转到常用功能

**数据更新**：
- 更新频率：2秒/次
- CPU/内存/网络：每次更新
- 磁盘：每3次更新（降低IO压力）
- 连通性：每5次更新（减少网络请求）

#### Ping测试 (PingTestPage)

**功能**：多模式Ping测试工具

**测试模式**：
| 模式 | 说明 |
|------|------|
| 单个Ping | 指定目标、次数、包大小 |
| 持续Ping | 持续Ping直到手动停止 |
| 批量Ping | 同时测试多个目标 |
| 网段Ping | 扫描整个网段的IP状态 |
| TCP Ping | 通过TCP端口检测连通性 |

**关键特性**：
- 中英文系统兼容的输出解析
- 线程安全的进度更新
- 支持结果导出

#### 网络服务 (NetworkServicePage)

**功能**：多种网络服务的配置和管理

**服务类型**：
| 服务 | 端口 | 说明 |
|------|------|------|
| FTP客户端 | 21 | 连接远程FTP服务器，支持上传/下载 |
| FTP服务端 | 21 | 启动本地FTP服务器 |
| HTTP服务 | 8080 | 文件分发服务器 |
| TFTP服务 | 69 | TFTP文件传输服务 |

---

## 8. 数据流与通信机制

### 8.1 信号槽线程通信模式

**标准模式**：
```python
class Worker(QObject):
    finished_signal = Signal(object)  # 完成信号
    error_signal = Signal(Exception)  # 错误信号
    
    def run(self):
        try:
            result = self.do_work()
            self.finished_signal.emit(result)  # 线程安全发送
        except Exception as e:
            self.error_signal.emit(e)

# 使用方式
worker = Worker()
worker.finished_signal.connect(on_result)  # 主线程接收
thread = QThread()
worker.moveToThread(thread)
thread.started.connect(worker.run)
thread.start()
```

### 8.2 页面生命周期管理

```
页面创建 → init_ui() → 信号连接 → 数据加载 → 用户操作 → 页面销毁
                              ↓                     ↓
                       后台线程执行              cleanup() 清理
                              ↓
                       信号槽更新UI
```

**清理机制**：
- 页面切换时自动调用 `cleanup()` / `stop_update_timer()` / `stop_all()`
- 定时器停止，线程中断，资源释放
- 防止后台线程向已删除的UI对象发送信号

---

## 9. 打包与部署

### 9.1 PyInstaller 配置

**main.spec 关键配置**：
```python
a = Analysis(
    ['main.py'],
    hiddenimports=[
        'PySide6.QtNetwork',
        'PySide6.QtPrintSupport',
        'psutil',
        'scapy',
        ...
    ],
    excludes=[
        'matplotlib',  # 可选依赖
        'pyqtgraph',   # 可选依赖
    ],
    console=False,  # 无控制台模式
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='NetworkToolkit',
    icon='assets/app-icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 关键：必须设置为False
)
```

### 9.2 打包检查清单

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 所有subprocess调用 | ✅ | 添加CREATE_NO_WINDOW |
| logger.py | ✅ | 检查stdout可用性 |
| 资源文件路径 | ✅ | 使用sys._MEIPASS |
| 权限检查 | ✅ | 非管理员模式降级提示 |
| 可选依赖 | ✅ | 运行时按需加载 |

---

## 10. 扩展开发指南

### 10.1 新增页面步骤

1. **创建页面文件**：在 `app/ui/` 目录下创建新文件
2. **定义页面类**：继承 `QWidget`，实现 `__init__` 和 `init_ui` 方法
3. **注册到主窗口**：在 `main_window.py` 的 `nav_groups` 中添加条目
4. **实现清理方法**：添加 `stop_update_timer()` 或 `cleanup()` 方法

**模板代码**：
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class MyNewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("我的新页面"))
    
    def stop_update_timer(self):
        # 停止定时器和后台线程
        pass
```

### 10.2 后台任务开发模式

**推荐模式**：使用 `TaskThread` + 信号槽

```python
from app.core.thread_pool import TaskThread

def start_background_task(self):
    thread = TaskThread(self._do_work, arg1, arg2)
    thread.result_ready.connect(self._on_result)
    thread.task_error.connect(self._on_error)
    thread.start()

def _do_work(self, arg1, arg2):
    # 耗时操作
    return result

def _on_result(self, result):
    # 更新UI
    pass

def _on_error(self, error):
    # 错误处理
    pass
```

### 10.3 subprocess调用规范

**必须遵循**：
```python
import subprocess

result = subprocess.run(
    ["command", "arg1", "arg2"],
    capture_output=True,
    text=True,
    timeout=30,
    creationflags=subprocess.CREATE_NO_WINDOW,  # 必须添加！
    encoding="utf-8"  # 或 "gbk" 根据实际需求
)
```

---

## 附录

### A. 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+Q | 退出程序 |

### B. 配置文件位置

- 配置：`~/.network-toolkit/config.json`
- 日志：`~/.network-toolkit/logs/`
- SSH历史：`app/data/ssh_history.json`
- RDP历史：`app/data/rdp_history.json`

### C. 已知限制

1. 部分功能需要管理员权限（防火墙、抓包）
2. iperf3引擎需要外部安装iperf3工具
3. TFTP服务需要安装tftpy库
4. FTP服务端需要安装pyftpdlib库

---

**文档版本**: V1.2  
**最后更新**: 2026-07-23