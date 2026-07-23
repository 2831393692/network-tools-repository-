# 网络工具箱 - 详细设计说明书

> **版本**: V1.2  
> **更新日期**: 2026-07-23  
> **状态**: 持续迭代中  

---

## 1. 引言

### 1.1 文档目的
本文档详细描述网络工具箱的技术设计方案，包括系统架构、模块划分、接口定义、UI设计、打包部署、踩坑经验等内容，作为开发人员的实现依据和项目知识沉淀。

### 1.2 参考文档
- [UI设计稿拆解](docs/ui-overview.md)
- [开发规划](docs/development-plan.md)

### 1.3 术语定义
| 术语 | 说明 |
|------|------|
| GUI | 图形用户界面 |
| API | 应用程序编程接口 |
| CLI | 命令行接口 |
| DPI | 每英寸点数，用于屏幕分辨率 |
| UAC | 用户账户控制，Windows安全机制 |
| VPN | 虚拟专用网络 |
| SSH | 安全外壳协议 |
| TFTP | 简单文件传输协议 |
| DHCP | 动态主机配置协议 |
| SNMP | 简单网络管理协议 |
| FTPS | FTP over SSL/TLS 加密传输 |
| PASV | FTP 被动模式 |
| CREATE_NO_WINDOW | Windows 子进程创建标志，隐藏控制台窗口 |

### 1.4 版本历史
| 版本 | 日期 | 主要变更 |
|------|------|---------|
| V1.0 | 2026-07-20 | 初始版本，完成全部基础功能 |
| V1.1 | 2026-07-22 | onefile单文件打包、去除黑框、自定义图标、移除5个页面 |
| V1.2 | 2026-07-23 | 修复黑框闪烁（33处subprocess）、DHCP网卡识别、内网测速双引擎、FTP客户端完整重写、仪表盘卡顿优化 |

---

## 2. 需求分析

### 2.1 功能需求

#### 2.1.1 仪表盘模块
- 系统资源监控（CPU/内存/磁盘/网络）
- 进程管理（查看/结束进程）
- 系统运行时长统计
- 网络状态总览（网关/DNS/互联网延迟）
- **异步初始化**：网关获取通过后台线程执行，不阻塞UI

#### 2.1.2 诊断检测模块
- Ping测试（单个/批量/网段/TCP Ping）
- 路由追踪
- 端口扫描
- 主机发现

#### 2.1.3 实用工具模块
- 子网计算（IPv4/IPv6/VLSM）
- IP信息查询
- MAC地址工具
- 路由表查看
- 连接测试（DNS/SSL/Telnet/MTU/密码生成/Whois/HTTP Headers等11个子功能）

#### 2.1.4 网络分析模块
- 数据包抓包
- 协议分析
- DHCP检测（基于psutil获取网卡信息，兼容Windows GUID格式接口名）
- 摄像头扫描（RTSP/ONVIF/HTTP协议扫描）

#### 2.1.5 安全模块
- 防火墙配置（快捷配置/高级规则/规则管理）
- 高级规则支持五元组配置和域名规则（域名自动解析为IP）

#### 2.1.6 速度测试模块
- **外网测速**：测试下载速度、网络延迟、网络抖动，支持多测速站点切换
- **内网测速**：服务端/客户端双模式，支持上传/下载/双向测试，**内置引擎与iPerf3双引擎可选**
  - 服务端和客户端必须使用相同引擎
  - iPerf3引擎自动查找exe同级目录的iperf3.exe
  - 内置引擎无需安装任何依赖，开箱即用
- **会话数测试**：并发连接压力测试，支持主/备服务器、自定义线程数、最大连接数、失败上限

#### 2.1.7 网络服务模块
- **FTP客户端**：连接远程FTP服务器，支持文件上传/下载/目录导航
  - 多编码自动识别（GB18030/GBK/GB2312/cp936/UTF-8/latin-1）
  - 双击进入文件夹、返回上级目录、路径下拉框快速切换
  - 传输历史记录（方向/文件名/远程路径/大小/状态/时间）
  - SSL/FTPS加密传输支持
  - 550权限错误友好提示
- **FTP服务**：基于pyftpdlib的FTP服务器（需安装依赖）
- **HTTP文件分发**：基于http.server的简易HTTP文件服务器
- **TFTP服务**：基于tftpy的TFTP服务器

#### 2.1.8 远程工具模块
- SSH终端（多会话、终端模式输入、历史记录）
- 串口调试（多会话、终端模式输入、设备预设、数据缓冲区）

#### 2.1.9 摄像头扫描模块
- **扫描范围**：基于IP网段（如 192.168.140.0/24）
- **扫描品牌**：海康威视、大华、宇视、天地伟业、通用（多选）
- **扫描模式**：快速扫描/深度扫描/ONVIF发现
- **结果展示**：IP/端口/品牌/型号/RTSP可用性/在线状态/Web访问URL/MAC地址
- **结果导出**：支持导出为CSV/TXT清单

### 2.2 非功能需求

| 需求类型 | 描述 |
|----------|------|
| 性能 | 端口扫描支持500+并发，响应时间<500ms |
| 兼容性 | 支持Windows 7/10/11 |
| 可靠性 | 异常情况有完善的错误处理和提示 |
| 易用性 | 中文界面，系统图标风格 |
| 可扩展性 | 模块化设计，方便新增功能 |
| 打包体积 | 目标<80MB |
| 无黑框 | console=False模式下所有subprocess调用必须添加CREATE_NO_WINDOW |

### 2.3 权限需求

| 功能 | 权限要求 |
|------|----------|
| 防火墙配置 | 管理员 |
| 安全日志审计 | 管理员 |
| 数据包抓包 | 管理员 |
| 路由表修改 | 管理员 |
| 进程管理（结束） | 管理员 |
| 常规功能 | 普通用户 |

---

## 3. 系统架构设计

### 3.1 整体架构

本项目采用 PySide6 为核心的桌面应用架构，整体分为四层：表示层、业务逻辑层、核心基础设施层、数据持久化层。各层之间通过明确的接口进行交互，层与层之间单向依赖。

```
┌──────────────────────────────────────────────────────────────┐
│                    表示层 (Presentation Layer)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   主窗口框架  │  │  功能页面集合  │  │  自定义组件  │  │
│  │ MainWindow   │  │  (20+ Pages)  │  │  (Widgets)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                  业务逻辑层 (Business Logic Layer)           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  网络诊断   │  │  系统管理   │  │  远程连接   │  │
│  │ Ping/扫描/  │  │ 进程/防火墙/ │  │ SSH/Telnet/ │  │
│  │ 抓包/路由   │  │ 配置/服务     │  │ RDP/串口    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                核心基础设施层 (Core Infrastructure)           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  配置管理    │  │  日志系统    │  │  权限检测    │  │
│  │ ConfigManager │  │    Logger    │  │ AdminChecker  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │  线程池      │  │  异常处理    │                        │
│  │ ThreadPool    │  │ Exception    │                        │
│  └──────────────┘  └──────────────┘                        │
├──────────────────────────────────────────────────────────────┤
│                数据持久化层 (Data Persistence)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  JSON配置文件 │  │  日志文件   │  │  历史记录    │  │
│  │ config.json  │  │  *.log      │  │  ssh_history │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构（实际）

```
project_03_network-testing-toolkit/
├── main.py                    # 程序入口，全局异常捕获
├── main.spec                  # PyInstaller打包配置（onefile模式）
├── requirements.txt           # 依赖清单
├── cygwin1.dll                # iperf3依赖的Cygwin运行库
├── app/
│   ├── __init__.py
│   ├── main_window.py         # 主窗口：导航、页面切换、状态栏
│   ├── core/                  # 核心基础设施
│   │   ├── __init__.py
│   │   ├── config.py          # 配置管理器（JSON持久化）
│   │   ├── logger.py          # 日志系统（文件+控制台，console=False兼容）
│   │   ├── permission.py      # 管理员权限检测与提权
│   │   └── thread_pool.py     # 线程池工具
│   ├── ui/                    # 表示层（所有页面）
│   │   ├── __init__.py
│   │   ├── dashboard.py       # 概览-仪表盘
│   │   ├── ping_test.py       # 诊断-Ping测试
│   │   ├── traceroute.py      # 诊断-路由追踪
│   │   ├── port_scan.py       # 诊断-端口扫描
│   │   ├── host_discovery.py  # 诊断-主机发现
│   │   ├── camera_scan.py     # 诊断-摄像头扫描
│   │   ├── network_health.py  # 诊断-网络健康
│   │   ├── speed_external.py  # 测速-外网测速
│   │   ├── speed_internal.py  # 测速-内网测速（双引擎）
│   │   ├── speed_session.py   # 测速-会话测试
│   │   ├── packet_capture.py  # 分析-数据包抓包
│   │   ├── protocol_analysis.py # 分析-协议分析
│   │   ├── dhcp_check.py      # 分析-DHCP检测
│   │   ├── subnet_calc.py     # 工具-子网计算
│   │   ├── ip_info.py         # 工具-IP信息检测
│   │   ├── mac_tool.py        # 工具-MAC地址工具
│   │   ├── route_table.py     # 工具-路由表
│   │   ├── connection_test.py # 工具-连接测试（11标签页）
│   │   ├── tools.py           # 工具-其他工具集合
│   │   ├── network_service.py # 服务-网络服务（FTP客户端/FTP/HTTP/TFTP）
│   │   ├── local_settings.py  # 服务-本机设置
│   │   ├── firewall.py        # 服务-防火墙配置
│   │   ├── link_monitor.py    # 监控-链路监控
│   │   ├── traffic_monitor.py # 监控-流量监控
│   │   ├── remote_terminal.py # 远程-SSH/Telnet终端
│   │   ├── remote_desktop.py  # 远程-远程桌面（RDP）
│   │   ├── serial_debug.py    # 远程-串口调试
│   │   ├── about.py           # 关于-软件信息
│   │   └── placeholder.py     # 占位页面
│   └── widgets/               # 自定义组件
│       └── __init__.py
├── assets/                    # 静态资源
│   ├── app-icon.ico           # 应用图标
│   └── ui-screenshots/        # UI截图
├── docs/                      # 文档
│   ├── design-spec.md         # 设计文档（本文件）
│   ├── development-plan.md    # 开发规划
│   └── ui-overview.md         # UI拆解
└── scripts/                   # 辅助脚本
    ├── _test_ping_parser.py
    ├── _test_subnet_scan.py
    └── _test_traceroute_format.py
```

### 3.3 导航菜单结构（V1.2 实际）

```
├── 概览
│   └── 仪表盘
├── 诊断检测
│   ├── Ping测试
│   ├── 路由追踪
│   ├── 端口扫描
│   ├── 主机发现
│   └── 网络健康检查
├── 实用工具
│   ├── 子网计算
│   ├── IP信息检测
│   ├── MAC地址工具
│   ├── 路由表查看
│   └── 连接测试
├── 网络分析
│   ├── 数据包抓包
│   ├── 协议分析
│   ├── DHCP检测
│   └── 摄像头扫描
├── 速度测试
│   ├── 外网测速
│   ├── 内网测速
│   └── 会话测试
├── 网络服务
│   ├── 网络服务（FTP客户端/FTP/HTTP/TFTP）
│   ├── 本机设置
│   └── 防火墙配置
├── 监控运维
│   ├── 链路监控
│   └── 流量监控
├── 远程工具
│   ├── 远程终端
│   ├── 远程桌面
│   └── 串口调试
└── 智能系统
    └── 关于和支持
```

> **注**：V1.1版本移除了WiFi密码、WiFi分析、终端端口、AI助手、系统设置5个页面

### 3.4 关键技术选型

| 技术 | 用途 | 说明 |
|------|------|------|
| Python 3.12 | 开发语言 | 主要运行环境 |
| PySide6 | GUI框架 | Qt官方Python绑定，LGPL授权 |
| psutil | 系统信息 | 跨平台系统/进程信息获取、网卡枚举 |
| pyserial | 串口通信 | RS232/USB串口通信 |
| paramiko | SSH客户端 | SSH2协议Python实现 |
| dnspython | DNS解析 | 支持所有DNS记录类型 |
| requests | HTTP请求 | HTTP/HTTPS网络请求 |
| cryptography | 加密安全 | SSL证书解析、加解密 |
| scapy | 网络探测 | 数据包构造与解析 |
| ftplib | FTP客户端 | Python标准库，FTP协议实现 |
| pyftpdlib | FTP服务端 | 纯Python FTP服务器（需安装） |
| tftpy | TFTP服务端 | 纯Python TFTP服务器 |
| pyqtgraph | 实时图表 | 仪表盘和流量监控的实时数据可视化 |
| PyInstaller | 打包发布 | onefile单文件模式，console=False |

### 3.5 核心设计模式

#### 3.5.1 页面懒加载模式

主窗口采用**懒加载**策略管理功能页面：

```
用户点击导航 → switch_page(key, page_class, name)
    → 检查 pages 缓存中是否已存在
    → 存在：直接切换显示
    → 不存在：实例化页面 → 存入缓存 → 切换显示
```

- 优点：启动快、内存占用低
- 页面切换时调用 `cleanup()` 停止后台线程

#### 3.5.2 信号槽线程通信

所有耗时操作通过 `QThread` 后台执行，通过 `Signal` 与UI线程通信：

```
UI线程 (主线程)
    ↓ 创建 Worker(QThread)
    ↓ start()
后台线程
    ↓ 执行耗时操作
    ↓ emit signal.emit(result)
    ↓
UI线程 (槽函数更新)
```

- 页面基类约定：
  - `cleanup()`: 页面切换时清理资源
  - `stop_all()`: 停止所有后台线程
  - 通过 `Signal` 更新UI，禁止后台线程直接操作UI控件

#### 3.5.3 终端输入模式

远程终端和串口调试采用**终端模式**输入：
- 通过 `eventFilter` 拦截键盘事件
- `command_buffer` 维护当前输入行
- 支持历史记录（上下键翻历史）
- 支持控制字符处理（Ctrl+C/D/Z/U/W/A/E）
- 设备回显与用户输入分离
- PySide6 正确写法：`QEvent.Type.KeyPress`（非 `Qt.KeyPress`）、`QTextCursor.MoveOperation.End`

#### 3.5.4 多会话管理

远程终端和串口调试支持多会话（Tab多标签页管理）

```
MainPage
 ├── Tab 1 (会话1)
 ├── Tab 2 (会话2)
 └── Tab N (会话N)
```

每个会话独立的独立线程独立资源，切换Tab关闭时清理对应资源

#### 3.5.5 subprocess 安全调用模式（V1.2 新增）

**核心规则**：`console=False` 打包模式下，所有 `subprocess.run()` 和 `subprocess.Popen()` 调用**必须**添加 `creationflags=subprocess.CREATE_NO_WINDOW`，否则会弹出黑色控制台窗口。

```python
# ✅ 正确写法
result = subprocess.run(
    ["ping", "-n", "1", host],
    capture_output=True, text=True, timeout=5,
    creationflags=subprocess.CREATE_NO_WINDOW
)

# ❌ 错误写法（会弹黑框）
result = subprocess.run(
    ["ping", "-n", "1", host],
    capture_output=True, text=True, timeout=5
)
```

**已修复的文件清单（共33处）**：

| 文件 | 修复数 | 涉及命令 |
|------|--------|---------|
| firewall.py | 10 | powershell |
| ping_test.py | 4 | ping |
| traffic_monitor.py | 4 | ipconfig/route |
| traceroute.py | 3 | tracert/ping |
| ip_info.py | 3 | arp/ipconfig |
| route_table.py | 2 | route |
| connection_test.py | 2 | tracert/ping |
| network_health.py | 2 | ping |
| mac_tool.py | 2 | arp |
| host_discovery.py | 2 | arp/ping |
| dashboard.py | 2 | route/ping |
| speed_internal.py | 1 | iperf3/ipconfig |
| camera_scan.py | 1 | arp |
| tools.py | 1 | system |
| link_monitor.py | 1 | ping |

#### 3.5.6 异步初始化模式（V1.2 新增）

仪表盘的 `get_gateway()` 方法内部执行 `subprocess.run(["route", "print", "0.0.0.0"])`，会阻塞主线程导致卡顿。解决方案：

```python
def __init__(self, parent=None):
    # ...
    self.gateway = "192.168.1.1"  # 默认值，不阻塞
    # ...
    self.start_update_timer()
    QTimer.singleShot(500, self._init_gateway)  # 延迟500ms后异步获取

def _init_gateway(self):
    threading.Thread(target=self._fetch_gateway, daemon=True).start()

def _fetch_gateway(self):
    gateway = self.get_gateway()
    if gateway:
        self.gateway = gateway
```

### 3.6 数据流架构

```
用户操作
    ↓
UI组件 (QWidgets)
    ↓ 信号槽
业务逻辑 (页面内方法)
    ↓
系统命令/第三方库
    ↓ subprocess（CREATE_NO_WINDOW）/pyserial/paramiko
    ↓
系统/网络
    ↓
结果返回
    ↓ Signal
UI更新
```

### 3.7 异常处理机制

#### 3.7.1 全局异常捕获

`main.py` 中设置 `sys.excepthook` 全局异常处理：
- 记录异常堆栈到日志文件
- 弹出错误对话框提示用户
- 防止程序直接崩溃无提示

#### 3.7.2 页面级异常

每个功能页面内部异常处理：
- 操作失败 → QMessageBox提示
- 后台线程异常 → error_signal 信号传递
- 资源清理 → finally 块确保资源释放

#### 3.7.3 console=False 模式兼容（V1.2 关键修复）

`console=False` 打包模式下 `sys.stdout` 不可用，`logger.py` 中的 `StreamHandler` 会抛出 `OSError: Bad file descriptor`：

```python
# ✅ 正确写法：检查 stdout 可用性
try:
    sys.stdout.fileno()
    console_handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(console_handler)
except (OSError, AttributeError):
    pass  # console=False 模式下跳过控制台输出
```

---

## 4. 关键模块详细设计

### 4.1 DHCP检测模块（V1.2 重构）

**问题**：Windows 上 scapy 返回的网卡接口名为 GUID 格式（如 `{E8A5A4B6-...}`），且 `get_if_addr()` 经常返回空字符串。

**解决方案**：改用 `psutil` 作为主要网卡信息来源，通过 IP 地址匹配 scapy 接口。

```python
def _get_interface_mapping(self):
    # 1. 遍历 psutil 网卡，获取友好名称 + IP + MAC
    # 2. 通过 IP 匹配 scapy 接口名
    # 3. 只显示有有效 IP 的非回环网卡
    # 4. 显示格式："以太网 (IP: 192.168.1.100, MAC: xx:xx:...)"
```

### 4.2 内网测速模块（V1.2 双引擎）

#### 4.2.1 双引擎架构

| 引擎 | 服务端 | 客户端 | 协议 | 兼容性 |
|------|--------|--------|------|--------|
| 内置引擎 | Python socket | Python socket | 自定义 | 仅工具↔工具 |
| iperf3 | iperf3.exe -s | iperf3.exe -c | 标准iperf3 | 任何iperf3客户端 |

**关键规则**：服务端和客户端必须使用相同引擎！

#### 4.2.2 iperf3 路径查找

```python
def get_iperf3_path(self):
    # 优先级：
    # 1. exe 同级目录的 iperf3.exe
    # 2. exe 同级的 tools/iperf3.exe
    # 3. exe 同级的 bin/iperf3.exe
    # 4. 系统 PATH 中的 iperf3
```

#### 4.2.3 服务端引擎选择（V1.2 新增）

服务端面板添加了引擎选择单选按钮：
- **内置引擎**：启动 Python socket 服务端
- **iperf3**：调用 `iperf3 -s -p <port>` 启动标准服务端，使用 `CREATE_NO_WINDOW` 隐藏窗口

### 4.3 FTP客户端模块（V1.2 完整重写）

#### 4.3.1 编码处理

FTP服务器编码不确定，Windows FTP常用GBK，Python默认UTF-8：

```python
def _decode_line(self, line_bytes):
    # 依次尝试：gb18030 → gbk → gb2312 → cp936 → utf-8 → latin-1
    for encoding in ['gb18030', 'gbk', 'gb2312', 'cp936', 'utf-8', 'latin-1']:
        try:
            return line_bytes.decode(encoding)
        except Exception:
            continue
    return line_bytes.decode('latin-1', errors='replace')
```

#### 4.3.2 路径处理

FTP协议必须使用 `/` 分隔符，Windows使用 `\`：

```python
def _ftp_path(self, *parts):
    return '/'.join(parts).replace('\\', '/')
```

#### 4.3.3 目录导航

| 操作 | 方法 |
|------|------|
| 连接成功 | `pwd()` 获取实际工作目录 |
| 双击文件夹 | `cwd(new_path)` 进入目录 |
| 返回上级 | 分割路径获取父目录，`cwd(parent_path)` |
| 路径下拉框 | 记录访问历史，点击切换 |

#### 4.3.4 传输历史

上传/下载完成后通过 `history_signal` 发送历史记录：
- 方向（上传/下载）
- 文件名
- 远程路径
- 文件大小
- 状态（成功/失败）
- 时间戳

#### 4.3.5 错误处理

| 错误码 | 原因 | 提示 |
|--------|------|------|
| 530 | 用户名或密码错误 | "登录失败：用户名或密码错误" |
| 550 | 权限不足或路径不存在 | "权限不足，请联系管理员开启写入权限" |
| 421 | 服务不可用 | "服务不可用，连接被关闭" |

### 4.4 串口调试模块

#### 4.4.1 数据缓冲区

设备返回数据可能分多个chunk到达，导致换行去重逻辑失效：

```python
# 添加数据缓冲区，延迟50ms统一处理
self._data_buffer = b''
self._buffer_timer = QTimer()
self._buffer_timer.setSingleShot(True)
self._buffer_timer.timeout.connect(self._process_buffer)
```

#### 4.4.2 PySide6 枚举访问

```python
# ✅ 正确写法（PySide6）
cursor.movePosition(QTextCursor.MoveOperation.End)
QEvent.Type.KeyPress

# ❌ 错误写法（PyQt5 风格）
cursor.movePosition(cursor.End)
event.KeyPress
```

---

## 5. 打包部署设计

### 5.1 PyInstaller 配置（main.spec）

#### 5.1.1 onefile 单文件模式

```python
# 关键配置
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,    # onefile模式必须传入
    a.datas,       # onefile模式必须传入
    [],
    name='网络工具箱',
    icon='assets/app-icon.ico',
    console=False,  # 无控制台黑框
    upx=True,
    upx_exclude=[
        'python3.dll', 'python310.dll',
        'vcruntime140.dll', 'msvcp140.dll',
        'Qt6Core.dll', 'Qt6Gui.dll',
        'Qt6Widgets.dll', 'Qt6Network.dll',
    ],
)
# 注意：onefile模式不需要 COLLECT() 块
```

#### 5.1.2 隐藏导入清单

```python
hiddenimports=[
    'serial', 'serial.tools.list_ports',  # pyserial
    'paramiko',                            # SSH
    'psutil',                              # 系统信息
    'requests',                            # HTTP
    'scapy', 'scapy.all', 'scapy.arch', 'scapy.arch.windows',  # 网络探测
    'dns', 'dns.resolver',                 # DNS
    'tftpy',                               # TFTP
    'ftplib',                              # FTP
    'cryptography', 'nacl', 'bcrypt',     # 加密
]
```

#### 5.1.3 排除模块清单

```python
excludes=[
    'tkinter',       # 未使用的GUI框架
    'PyQt5', 'PyQt6',  # 未使用的Qt绑定
    'matplotlib',    # 未使用的数据科学库
    'pandas',        # 未使用
    'IPython',       # 未使用
    'test', 'unittest',  # 测试模块
    'pydoc_data',
]
```

### 5.2 打包后目录结构

```
分发目录/
├── 网络工具箱.exe     # 主程序（onefile单文件）
├── iperf3.exe         # 可选：内网测速工具（放同目录自动识别）
├── cygwin1.dll        # iperf3依赖的Cygwin运行库
└── assets/
    └── app-icon.ico   # 应用图标
```

### 5.3 踩坑经验总结

#### 5.3.1 黑框闪烁问题（V1.2 核心修复）

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 打开应用闪黑框 | logger.py 的 StreamHandler 访问不可用的 sys.stdout | 添加 sys.stdout.fileno() 检查 |
| 点击功能闪黑框 | subprocess.run 调用系统命令时创建控制台窗口 | 添加 creationflags=CREATE_NO_WINDOW |
| iperf3服务端闪黑框 | subprocess.Popen 使用 CREATE_NEW_CONSOLE | 改用 CREATE_NO_WINDOW + STARTF_USESHOWWINDOW |
| dashboard 卡顿 | __init__ 中直接调用 subprocess.run 阻塞主线程 | 改用 QTimer.singleShot + 后台线程 |

#### 5.3.2 onefile 模式路径问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 文件保存到临时目录 | `__file__` 指向 _MEIPASS 临时目录 | 使用 `~/.network-toolkit/data/` 用户目录 |
| os.chdir(sys._MEIPASS) 副作用 | 改变工作目录后文件路径错乱 | 删除 chdir 调用 |

#### 5.3.3 PySide6 兼容性

| 问题 | PyQt5 写法 | PySide6 正确写法 |
|------|-----------|-----------------|
| 事件类型判断 | `event.KeyPress` | `QEvent.Type.KeyPress` |
| 光标移动 | `cursor.End` | `QTextCursor.MoveOperation.End` |

#### 5.3.4 FTP 编码问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 文件列表乱码 | Windows FTP服务器使用GBK编码 | retrbinary + 多编码尝试解码 |
| 200响应行混入列表 | retrlines 不过滤响应码 | 改用 retrbinary 手动解析 |
| 路径分隔符错误 | Windows使用\，FTP使用/ | _ftp_path() 统一转换为/ |
| 550 Permission denied | 权限不足或路径分隔符错误 | 修复路径 + 友好提示 |

#### 5.3.5 串口调试问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 按Enter换两行 | 设备返回数据分多个chunk到达 | 添加50ms数据缓冲区 |
| 时间戳与命令粘连 | append_data 添加时间戳 | 移除数据接收时的时间戳 |
| Ctrl+C不可用 | eventFilter 未处理控制字符 | 添加 Ctrl+C/D/Z/U/W/A/E 支持 |

#### 5.3.6 图标缓存问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 移动exe后图标变回默认 | Windows图标缓存 | `ie4uinit.exe -show` 或重启资源管理器 |

---

## 6. UI设计

### 6.1 主窗口布局

```
┌─────────────────────────────────────────────────────────────┐
│  标题栏 (网络工具箱 V1.0 + 最小化/最大化/关闭按钮)            │
├──────────────────┬──────────────────────────────────────────┤
│                  │                                          │
│   左侧导航栏     │              主内容区                      │
│   (菜单列表)     │              (功能页面)                    │
│                  │                                          │
│                  │                                          │
│                  │                                          │
│                  │                                          │
├──────────────────┼──────────────────────────────────────────┤
│                  │              状态栏                       │
│                  │  (系统状态 + 网络延迟 + 运行时长)          │
└──────────────────┴──────────────────────────────────────────┘
```

### 6.2 颜色规范

| 颜色类型 | RGB值 | 用途 |
|----------|-------|------|
| 主色调 | #1E90FF | 按钮/选中状态 |
| 成功 | #27ae60 / #00B894 | 成功状态指示 |
| 警告 | #FDCB6E / #ed7d31 | 警告状态指示 |
| 错误 | #FF6B6B / #c00 | 错误状态指示 |
| 背景 | #F5F6FA / #f5f7fa | 页面背景 |
| 卡片 | #FFFFFF | 卡片背景 |
| 文字 | #2D3436 / #2c3e50 | 主要文字 |
| 次要文字 | #636E72 / #555 | 次要文字 |

### 6.3 FTP客户端页面设计

| 区域 | 内容 | 组件 |
|------|------|------|
| 连接配置 | 主机/端口/用户名/密码/SSL | 输入框+复选框 |
| 操作按钮 | 连接/断开/上传/下载/刷新 | 按钮组 |
| 路径导航 | 当前路径下拉框/返回/加载 | 下拉框+按钮 |
| 远程文件列表 | 文件名/大小/日期/类型 | QTableWidget |
| 传输历史 | 方向/文件名/路径/大小/状态/时间 | QTableWidget |
| 状态指示 | 已连接/未连接 | 状态标签 |

### 6.4 内网测速页面设计

**服务端面板**：

| 区域 | 内容 | 组件 |
|------|------|------|
| 监听端口 | 默认5201 | QSpinBox |
| 本机IP | 自动获取 | QLabel |
| 测试引擎 | 内置引擎/iperf3 | QRadioButton |
| 操作按钮 | 启动服务端/停止 | 按钮组 |
| 服务端日志 | 实时日志输出 | QTextEdit |

**客户端面板**：

| 区域 | 内容 | 组件 |
|------|------|------|
| 服务器IP | 输入框 | QLineEdit |
| 端口 | 默认5201 | QSpinBox |
| 测试时长 | 默认10秒 | QSpinBox |
| 测试模式 | 上传/下载/双向 | QRadioButton |
| 测试引擎 | 内置引擎/iperf3 | QRadioButton |
| 操作按钮 | 开始测速/停止 | 按钮组 |
| 测试结果 | 速度/延迟 | QTextEdit + QProgressBar |

---

## 7. 安全性设计

### 7.1 权限管理

#### 7.1.1 权限检测机制

```python
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False
```

#### 7.1.2 需要管理员权限的功能清单

| 功能 | 权限要求 | 原因 |
|------|----------|------|
| 防火墙配置 | 管理员 | 修改系统防火墙规则 |
| 安全日志审计 | 管理员 | 读取安全日志需要高权限 |
| 数据包抓包 | 管理员 | npcap驱动需要管理员权限 |
| 路由表修改 | 管理员 | 修改系统路由表 |
| 进程管理（结束） | 管理员 | 结束系统进程 |
| 修改远程端口 | 管理员 | 修改注册表 |

### 7.2 命令注入防护

| 风险点 | 防护措施 |
|--------|----------|
| 系统命令参数 | 使用subprocess的列表形式，避免字符串拼接 |
| 文件路径 | 使用pathlib处理路径，验证路径安全性 |
| 网络请求参数 | 使用requests的参数传递，自动编码 |

```python
# ✅ 安全方式
subprocess.run(["ping", user_input], shell=False,
               creationflags=subprocess.CREATE_NO_WINDOW)

# ❌ 不安全方式
subprocess.run(f"ping {user_input}", shell=True)
```

---

## 8. 性能设计

### 8.1 并发处理

| 场景 | 线程数 | 理由 |
|------|--------|------|
| Ping测试 | 50-100 | 网络IO密集，需要高并发 |
| 端口扫描 | 100-300 | 大量连接尝试，需要高并发 |
| 主机发现 | 100-200 | 网段扫描，需要高并发 |
| 数据采集 | 4-8 | CPU密集，避免过多线程 |

### 8.2 响应时间要求

| 操作 | 响应时间 | 说明 |
|------|----------|------|
| 应用启动 | <3秒 | onefile解压+初始化 |
| 页面切换 | <200ms | UI操作 |
| 单主机Ping | <1s | 网络操作 |
| 端口扫描(100端口) | <10s | 并发操作 |
| 仪表盘初始化 | <500ms | 异步加载，不阻塞 |

### 8.3 资源优化

| 措施 | 说明 |
|------|------|
| 懒加载 | 按需加载模块，减少启动时间 |
| 异步初始化 | 仪表盘网关获取通过后台线程 |
| 对象复用 | 复用表格模型等大型对象 |
| 排除模块 | 打包排除matplotlib等未使用库 |
| UPX压缩 | 关键DLL排除压缩，其余压缩 |

---

## 9. Git版本管理

### 9.1 版本历史

| 版本 | 日期 | 提交信息 |
|------|------|---------|
| v1.0 | 2026-07-20 | Initial commit: 网络测试工具箱 - 完整功能 |
| v1.1 | 2026-07-22 | fix: onefile模式下历史记录路径修复，移除chdir临时目录 |
| v1.2 | 2026-07-23 | fix: 修复黑框闪烁和卡顿问题，优化FTP客户端功能 |

### 9.2 仓库信息

- **仓库地址**: `https://github.com/2831393692/network-tools-repository-.git`
- **主分支**: `main`
- **备份策略**: 每次发布创建 Git Tag (`vX.Y.Z`) + 备份分支 (`backup/vX.Y.Z`)

### 9.3 提交信息规范

格式：`<类型>: <简短描述>`

| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug修复 |
| docs | 文档更新 |
| style | 代码格式 |
| refactor | 重构 |
| test | 测试 |
| chore | 构建/工具 |

---

## 10. 附录

### 10.1 需要管理员权限的系统命令清单

| 命令 | 用途 |
|------|------|
| `netsh advfirewall` | 防火墙配置 |
| `wevtutil` | 日志查询 |
| `route` | 路由表管理 |
| `reg` | 注册表操作 |
| `taskkill` | 结束进程 |

### 10.2 常用端口列表

| 端口 | 服务 |
|------|------|
| 21 | FTP |
| 22 | SSH |
| 23 | Telnet |
| 25 | SMTP |
| 53 | DNS |
| 69 | TFTP |
| 80 | HTTP |
| 443 | HTTPS |
| 3389 | RDP |
| 5201 | iperf3 默认端口 |

### 10.3 打包命令

```bash
cd E:\project3\project_03_network-testing-toolkit
pyinstaller main.spec --noconfirm
```

输出：`dist/网络工具箱.exe`

### 10.4 Git 推送命令

```bash
cd E:\project3\project_03_network-testing-toolkit

# 添加并提交
git add -A
git commit -m "fix: 修复描述"

# 创建标签和备份分支
git tag vX.Y.Z
git branch backup/vX.Y.Z

# 推送到远程
git push origin main
git push origin vX.Y.Z
git push origin backup/vX.Y.Z
```

### 10.5 依赖清单（requirements.txt）

```
PySide6>=6.5.0
psutil>=5.9.0
pyserial>=3.5
paramiko>=3.0.0
dnspython>=2.3.0
requests>=2.31.0
cryptography>=41.0.0
scapy>=2.5.0
pyqtgraph>=0.13.0
tftpy>=0.8.2
pyftpdlib>=1.5.7  # 可选，FTP服务功能需要
pycryptodome>=3.18.0
bcrypt>=4.0.0
pynacl>=1.5.0
```

### 10.6 关键约束检查清单

打包前必须确认：

- [ ] 所有 `subprocess.run/Popen` 调用都有 `creationflags=subprocess.CREATE_NO_WINDOW`
- [ ] `logger.py` 的 StreamHandler 有 `sys.stdout.fileno()` 可用性检查
- [ ] `main.spec` 中 `console=False`
- [ ] `main.spec` 中 `hiddenimports` 包含所有动态导入的库
- [ ] `main.spec` 中 `excludes` 排除了未使用的大模块
- [ ] `main.spec` 中 `upx_exclude` 排除了关键DLL
- [ ] onefile 模式下 `EXE()` 包含 `a.binaries` 和 `a.datas`
- [ ] onefile 模式下没有 `COLLECT()` 块
- [ ] 文件路径不依赖 `__file__`（onefile模式下指向临时目录）
- [ ] 没有 `os.chdir(sys._MEIPASS)` 调用
- [ ] 没有裸 `print()` 语句（console=False模式下会异常）
