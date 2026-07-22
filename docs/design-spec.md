# 网络测试工具箱 - 详细设计说明书

## 1. 引言

### 1.1 文档目的
本文档详细描述网络测试工具箱的技术设计方案，包括系统架构、模块划分、接口定义、UI设计等内容，作为开发人员的实现依据。

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

---

## 2. 需求分析

### 2.1 功能需求

#### 2.1.1 仪表盘模块
- 系统资源监控（CPU/内存/磁盘/网络）
- 进程管理（查看/结束进程）
- 系统运行时长统计
- 网络状态总览（网关/DNS/互联网延迟）

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

#### 2.1.4 网络分析模块
- 数据包抓包
- 协议分析
- DHCP检测
- WiFi分析
- **摄像头扫描**：基于RTSP/ONVIF/HTTP协议扫描网段内的监控摄像头设备

#### 2.1.5 安全模块
- 本机安全自测
- 安全日志审计
- 防火墙配置

#### 2.1.6 速度测试模块
- **外网测速**：测试下载速度、网络延迟、网络抖动，支持多测速站点切换，提供外部在线测速链接
- **内网测速**：服务端/客户端双模式，支持上传/下载/双向测试，内置引擎与iPerf3双引擎
- **会话数测试**：并发连接压力测试，支持主/备服务器、自定义线程数、最大连接数、失败上限

#### 2.1.7 网络服务模块
- TFTP服务器
- FTP服务器
- HTTP文件分发
- Syslog服务器

#### 2.1.8 远程工具模块
- SSH终端
- 串口调试

#### 2.1.9 摄像头扫描模块
- **扫描范围**：基于IP网段（如 192.168.140.0/24）
- **扫描品牌**：海康威视、大华、宇视、天地伟业、通用（多选）
- **扫描模式**：
  - 快速扫描：仅探测默认端口（554/80/8080/8000等）
  - 深度扫描：全端口扫描 + 协议深度探测，耗时较长
  - ONVIF发现：使用ONVIF协议标准发现，兼容性最好
- **结果展示**：IP/端口/品牌/型号/RTSP可用性/在线状态/Web访问URL/MAC地址
- **结果导出**：支持导出为CSV/TXT清单

#### 2.1.10 连接测试模块
集成多种网络连接性测试工具，通过标签页形式组织：

- **DNS查询**：输入域名查询A/AAAA/CNAME/MX/TXT/NS等记录类型
- **DNS优选**：测试多个公共DNS服务器（114/阿里/Google/Cloudflare等）响应速度，推荐最快的DNS
- **站点测试**：批量测试网站可访问性，返回HTTP状态码/响应时间/标题
- **Telnet端口**：Telnet方式测试目标主机端口连通性，支持交互式终端
- **MTU测试**：通过Ping分片探测路径最大传输单元（MTU）
- **SSL检测**：检测HTTPS站点证书信息（颁发者/有效期/算法/链）
- **密码生成**：生成随机强密码，支持长度/字符集/特殊字符/排除字符配置
- **NSLookup**：交互式DNS查询工具，支持指定DNS服务器
- **Traceroute**：路由追踪（与诊断检测模块独立，这里提供快捷入口）
- **Whois查询**：查询域名注册信息（注册商/注册时间/到期时间/联系人）
- **HTTP Headers**：查看网站HTTP响应头信息

### 2.2 非功能需求

| 需求类型 | 描述 |
|----------|------|
| 性能 | 端口扫描支持500+并发，响应时间<500ms |
| 兼容性 | 支持Windows 7/10/11 |
| 可靠性 | 异常情况有完善的错误处理和提示 |
| 易用性 | 中文界面，系统图标风格 |
| 可扩展性 | 模块化设计，方便新增功能 |
| 打包体积 | 目标<80MB |

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

本项目采用 **PySide6为核心的桌面应用架构，整体分为四层：表示层、业务逻辑层、核心基础设施层、数据持久化层。各层之间通过明确的接口进行交互，层与层之间单向依赖。

```
┌──────────────────────────────────────────────────────────────┐
│                    表示层 (Presentation Layer)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   主窗口框架  │  │  功能页面集合  │  │  自定义组件  │  │
│  │ MainWindow   │  │  (30+ Pages)  │  │  (Widgets)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                  业务逻辑层 (Business Logic Layer)           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  网络诊断   │  │  系统管理   │  │  远程连接   │  │
│  │ Ping/扫描/  │  │ 进程/防火墙/ │  │ SSH/Telnet/ │  │
│  │ 抓包/路由   │  │ 配置/服务     │  │ RDP/串口    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                核心基础设施层 (Core Infrastructure)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  配置管理    │  │  日志系统    │  │  权限检测    │  │
│  │ ConfigManager │  │    Logger    │  │ AdminChecker  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │  线程池      │  │  异常处理    │                        │
│  │ ThreadPool    │  │ Exception    │                        │
│  └──────────────┘  └──────────────┘                        │
├──────────────────────────────────────────────────────────────┤
│                数据持久化层 (Data Persistence)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  JSON配置文件 │  │  日志文件   │  │  历史记录    │  │
│  │ config.json  │  │  *.log      │  │  ssh_history │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
project_03_network-testing-toolkit/
├── main.py                    # 程序入口，全局异常捕获
├── requirements.txt           # 依赖清单
├── app/
│   ├── __init__.py
│   ├── main_window.py       # 主窗口：导航、页面切换、状态栏
│   ├── core/                    # 核心基础设施
│   │   ├── __init__.py
│   │   ├── config.py       # 配置管理器（JSON持久化）
│   │   ├── logger.py       # 日志系统（文件+控制台）
│   │   ├── permission.py   # 管理员权限检测与提权
│   │   └── thread_pool.py  # 线程池工具
│   ├── ui/                      # 表示层（所有页面）
│   │   ├── __init__.py
│   │   ├── dashboard.py         # 概览-仪表盘
│   │   ├── ping_test.py         # 诊断-Ping测试
│   │   ├── traceroute.py        # 诊断-路由追踪
│   │   ├── port_scan.py       # 诊断-端口扫描
│   │   ├── host_discovery.py  # 诊断-主机发现
│   │   ├── camera_scan.py      # 诊断-摄像头扫描
│   │   ├── network_health.py  # 诊断-网络健康
│   │   ├── speed_external.py  # 测速-外网测速
│   │   ├── speed_internal.py  # 测速-内网测速
│   │   ├── speed_session.py   # 测速-会话测试
│   │   ├── packet_capture.py  # 分析-数据包抓包
│   │   ├── protocol_analysis.py # 分析-协议分析
│   │   ├── dhcp_check.py      # 分析-DHCP检测
│   │   ├── subnet_calc.py     # 工具-子网计算
│   │   ├── ip_info.py         # 工具-IP信息检测
│   │   ├── mac_tool.py        # 工具-MAC地址工具
│   │   ├── route_table.py     # 工具-路由表
│   │   ├── connection_test.py # 工具-连接测试（DNS/SSL/Telnet/MTU）
│   │   ├── tools.py           # 工具-其他工具集合
│   │   ├── network_service.py # 服务-网络服务（TFTP/HTTP等）
│   │   ├── local_settings.py  # 服务-本机设置
│   │   ├── firewall.py       # 服务-防火墙配置
│   │   ├── link_monitor.py   # 监控-链路监控
│   │   ├── traffic_monitor.py # 监控-流量监控
│   │   ├── remote_terminal.py # 远程-SSH/Telnet终端
│   │   ├── remote_desktop.py  # 远程-远程桌面（RDP）
│   │   ├── serial_debug.py   # 远程-串口调试
│   │   ├── about.py          # 关于-软件信息
│   │   └── placeholder.py    # 占位页面（未实现功能）
│   └── widgets/             # 自定义组件
│       └── __init__.py
├── assets/                 # 静态资源
│   └── ui-screenshots/
├── docs/                   # 文档
│   ├── design-spec.md       # 设计文档（本文件）
│   ├── development-plan.md
│   └── ui-overview.md
└── scripts/                # 辅助脚本
```

### 3.3 模块划分

#### 3.3.1 核心层 (app/core)

| 模块 | 类名 | 职责 | 文件位置 |
|------|------|------|----------|
| 配置管理 | `ConfigManager` | 配置文件读写、默认配置合并、键值访问 | `app/core/config.py` |
| 日志系统 | `Logger` | 日志记录（文件+控制台双通道）、按天切割 | `app/core/logger.py` |
| 权限检测 | `AdminChecker` | 管理员权限检测、UAC提权、装饰器 | `app/core/permission.py` |
| 线程池 | `ThreadPool` | 异步任务执行、并发控制 | `app/core/thread_pool.py` |

#### 3.3.2 表示层 (app/ui)

按功能分为 9 个导航分组，共 30+ 个页面组件：

| 分组 | 页面 | 说明 | 文件 |
|------|------|------|------|
| 概览 | 仪表盘 | 系统资源监控、网络状态总览 | `dashboard.py` |
| 诊断检测 | 网络健康 | 一键网络健康体检 | `network_health.py` |
| 诊断检测 | Ping测试 | 单个/批量/网段/TCP Ping | `ping_test.py` |
| 诊断检测 | 路由追踪 | Traceroute 路由追踪 | `traceroute.py` |
| 诊断检测 | 端口扫描 | TCP端口扫描、服务识别 | `port_scan.py` |
| 诊断检测 | 主机发现 | ARP扫描、存活主机检测 | `host_discovery.py` |
| 诊断检测 | 摄像头扫描 | ONVIF/RTSP摄像头扫描 | `camera_scan.py` |
| 速度测试 | 外网测速 | 宽带测速 | `speed_external.py` |
| 速度测试 | 内网测速 | iperf3内网测速 | `speed_internal.py` |
| 速度测试 | 会话测试 | 并发会话数测试 | `speed_session.py` |
| 网络分析 | 数据包抓包 | scapy数据包捕获 | `packet_capture.py` |
| 网络分析 | 协议分析 | 协议统计分析 | `protocol_analysis.py` |
| 网络分析 | DHCP检测 | DHCP服务器检测 | `dhcp_check.py` |
| 实用工具 | 子网计算 | IPv4/IPv6/VLSM计算 | `subnet_calc.py` |
| 实用工具 | IP信息检测 | IP归属地、运营商查询 | `ip_info.py` |
| 实用工具 | MAC地址工具 | MAC厂商查询、格式转换 | `mac_tool.py` |
| 实用工具 | 路由表 | 查看/添加/删除路由 | `route_table.py` |
| 实用工具 | 连接测试 | DNS/SSL/Telnet/MTU/密码生成 | `connection_test.py` |
| 网络服务 | 网络服务 | TFTP/HTTP/Syslog服务器 | `network_service.py` |
| 网络服务 | 本机设置 | 系统工具快捷入口 | `local_settings.py` |
| 网络服务 | 防火墙配置 | 防火墙规则管理 | `firewall.py` |
| 监控运维 | 链路监控 | 多目标Ping监控、告警 | `link_monitor.py` |
| 监控运维 | 流量监控 | 网卡实时流量图表 | `traffic_monitor.py` |
| 远程工具 | 远程终端 | SSH/Telnet多会话终端 | `remote_terminal.py` |
| 远程工具 | 远程桌面 | RDP远程桌面连接 | `remote_desktop.py` |
| 远程工具 | 串口调试 | 多会话串口终端 | `serial_debug.py` |
| 智能系统 | 关于和支持 | 软件信息、许可说明 | `about.py` |

### 3.4 关键技术选型

| 技术 | 用途 | 说明 |
|------|------|------|
| Python 3.10+ | 开发语言 | 主要运行环境 |
| PySide6 | GUI框架 | Qt官方Python绑定，LGPL授权 |
| psutil | 系统信息 | 跨平台系统/进程信息获取 |
| pyserial | 串口通信 | RS232/USB串口通信 |
| paramiko | SSH客户端 | SSH2协议Python实现 |
| dnspython | DNS解析 | 支持所有DNS记录类型 |
| requests | HTTP请求 | HTTP/HTTPS网络请求 |
| cryptography | 加密安全 | SSL证书解析、加解密 |
| scapy | 网络探测 | 数据包构造与解析 |
| PyInstaller | 打包发布 | 打包为Windows可执行文件 |

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

#### 3.5.4 多会话管理

远程终端和串口调试支持多会话（Tab多标签页管理

```
MainPage
 ├── Tab 1 (会话1)
 ├── Tab 2 (会话2)
 └── Tab N (会话N)
```

每个会话独立的独立线程独立资源，切换Tab关闭时清理对应资源

### 3.6 数据流架构

```
用户操作
    ↓
UI组件 (QWidgets)
    ↓ 信号槽
业务逻辑 (页面内方法)
    ↓
系统命令/第三方库
    ↓ subprocess/pyserial/paramiko
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

---

## 4. 接口设计

### 4.1 模块间接口

#### 4.1.1 权限检测接口

```python
class AdminChecker:
    @staticmethod
    def is_admin() -> bool:
        """检测当前进程是否以管理员身份运行"""
    
    @staticmethod
    def check_permission(feature: str) -> bool:
        """检查特定功能是否需要管理员权限"""
    
    @staticmethod
    def show_permission_warning(feature: str) -> None:
        """显示权限不足警告对话框"""
```

#### 4.1.2 日志系统接口

```python
class Logger:
    def __init__(self, name: str):
        """初始化日志记录器"""
    
    def debug(self, message: str) -> None:
        """记录调试信息"""
    
    def info(self, message: str) -> None:
        """记录普通信息"""
    
    def warning(self, message: str) -> None:
        """记录警告信息"""
    
    def error(self, message: str, exception: Exception = None) -> None:
        """记录错误信息"""
    
    def critical(self, message: str) -> None:
        """记录严重错误"""
```

#### 4.1.3 配置管理接口

```python
class ConfigManager:
    @staticmethod
    def load_config() -> dict:
        """加载配置文件"""
    
    @staticmethod
    def save_config(config: dict) -> None:
        """保存配置文件"""
    
    @staticmethod
    def get(key: str, default=None):
        """获取配置项"""
    
    @staticmethod
    def set(key: str, value) -> None:
        """设置配置项"""
```

#### 4.1.4 线程池接口

```python
class ThreadPool:
    @staticmethod
    def submit(task: callable, *args, **kwargs) -> None:
        """提交任务到线程池"""
    
    @staticmethod
    def set_max_workers(count: int) -> None:
        """设置最大线程数"""
    
    @staticmethod
    def shutdown(wait: bool = True) -> None:
        """关闭线程池"""
```

### 4.2 网络工具接口

#### 4.2.1 Ping工具

```python
class PingTool:
    def __init__(self):
        """初始化Ping工具"""
    
    def ping(self, host: str, count: int = 4, timeout: int = 1) -> dict:
        """执行Ping测试"""
    
    def ping_batch(self, hosts: list, count: int = 1, timeout: int = 1) -> list:
        """批量Ping测试"""
    
    def ping_subnet(self, subnet: str, timeout: int = 1) -> list:
        """网段Ping扫描"""
    
    def tcp_ping(self, host: str, port: int, timeout: int = 1) -> bool:
        """TCP端口Ping测试"""
```

#### 4.2.2 端口扫描工具

```python
class PortScanner:
    def __init__(self):
        """初始化端口扫描器"""
    
    def scan(self, host: str, ports: list, timeout: int = 1) -> list:
        """扫描指定端口"""
    
    def scan_range(self, host: str, start_port: int, end_port: int, timeout: int = 1) -> list:
        """扫描端口范围"""
    
    def scan_common(self, host: str, timeout: int = 1) -> list:
        """扫描常用端口"""
```

#### 4.2.3 路由追踪工具

```python
class TracerouteTool:
    def __init__(self):
        """初始化路由追踪工具"""
    
    def trace(self, host: str, max_hops: int = 30, timeout: int = 2) -> list:
        """执行路由追踪"""
```

#### 4.2.4 抓包工具

```python
class PacketCapture:
    def __init__(self):
        """初始化抓包工具"""
    
    def start_capture(self, interface: str = None, filter: str = "") -> None:
        """开始抓包"""
    
    def stop_capture(self) -> None:
        """停止抓包"""
    
    def get_packets(self) -> list:
        """获取已捕获的数据包"""
    
    def save_packets(self, filename: str) -> None:
        """保存数据包到文件"""
```

### 4.3 系统工具接口

#### 4.3.1 进程管理工具

```python
class ProcessManager:
    @staticmethod
    def get_processes() -> list:
        """获取进程列表"""
    
    @staticmethod
    def kill_process(pid: int) -> bool:
        """结束指定进程"""
    
    @staticmethod
    def get_process_info(pid: int) -> dict:
        """获取进程详细信息"""
```

#### 4.3.2 防火墙管理工具

```python
class FirewallManager:
    @staticmethod
    def get_rules() -> list:
        """获取防火墙规则"""
    
    @staticmethod
    def add_rule(name: str, protocol: str, port: int, action: str) -> bool:
        """添加防火墙规则"""
    
    @staticmethod
    def delete_rule(name: str) -> bool:
        """删除防火墙规则"""
    
    @staticmethod
    def enable_rule(name: str) -> bool:
        """启用防火墙规则"""
    
    @staticmethod
    def disable_rule(name: str) -> bool:
        """禁用防火墙规则"""
```

#### 4.3.3 日志审计工具

```python
class LogAuditor:
    @staticmethod
    def get_security_logs(count: int = 100) -> list:
        """获取安全日志"""
    
    @staticmethod
    def get_system_logs(count: int = 100) -> list:
        """获取系统日志"""
    
    @staticmethod
    def get_application_logs(count: int = 100) -> list:
        """获取应用程序日志"""
```

### 4.4 服务器模块接口

#### 4.4.1 TFTP服务器

```python
class TFTPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 69, root_dir: str = "."):
        """初始化TFTP服务器"""
    
    def start(self) -> bool:
        """启动服务器"""
    
    def stop(self) -> None:
        """停止服务器"""
    
    def is_running(self) -> bool:
        """检查服务器是否运行"""
    
    def get_status(self) -> dict:
        """获取服务器状态"""
```

#### 4.4.2 FTP服务器

```python
class FTPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 21, root_dir: str = "."):
        """初始化FTP服务器"""
    
    def start(self) -> bool:
        """启动服务器"""
    
    def stop(self) -> None:
        """停止服务器"""
    
    def is_running(self) -> bool:
        """检查服务器是否运行"""
    
    def get_status(self) -> dict:
        """获取服务器状态"""
```

#### 4.4.3 Syslog服务器

```python
class SyslogServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 514):
        """初始化Syslog服务器"""
    
    def start(self) -> bool:
        """启动服务器"""
    
    def stop(self) -> None:
        """停止服务器"""
    
    def is_running(self) -> bool:
        """检查服务器是否运行"""
    
    def get_logs(self) -> list:
        """获取接收到的日志"""
```

### 4.5 摄像头扫描接口

#### 4.5.1 摄像头扫描器（主控）

```python
class CameraScanner:
    def __init__(self):
        """初始化摄像头扫描器"""
    
    def start_scan(self, subnet: str, brands: list = None,
                   mode: str = "fast", threads: int = 50,
                   timeout: int = 2) -> None:
        """
        启动摄像头扫描
        :param subnet: 扫描网段，如 192.168.140.0/24
        :param brands: 扫描品牌列表 ["hikvision", "dahua", "uniview", "tvwall", "generic"]
        :param mode: 扫描模式 fast/deep/onvif
        :param threads: 并发线程数
        :param timeout: 超时时间(秒)
        """
    
    def stop_scan(self) -> None:
        """停止扫描"""
    
    def get_progress(self) -> dict:
        """获取扫描进度 {total: 254, scanned: 100, found: 5, progress: 39.4}"""
    
    def export_results(self, filepath: str, format: str = "csv") -> bool:
        """导出扫描结果 csv/txt"""
```

#### 4.5.2 ONVIF 探测引擎

```python
class OnvifDiscovery:
    """
    ONVIF协议发现引擎
    原理：发送UDP组播(239.255.255.250:3702)的WS-Discovery探测包
    """
    
    def __init__(self):
        """初始化ONVIF发现"""
    
    def discover(self, timeout: int = 3) -> list:
        """发送ONVIF探测，返回发现的设备列表"""
    
    def get_device_info(self, xaddr: str, timeout: int = 5) -> dict:
        """获取设备详细信息（厂商、型号、序列号等）"""
    
    def get_capabilities(self, xaddr: str, timeout: int = 5) -> dict:
        """获取设备能力集（支持的RTSP URL、媒体配置等）"""
    
    def get_rtsp_url(self, xaddr: str, profile_index: int = 0) -> str:
        """获取RTSP流媒体URL"""
```

#### 4.5.3 RTSP 探测引擎

```python
class RTSPDiscovery:
    """
    RTSP协议探测引擎
    通过TCP连接554端口发送OPTIONS请求验证RTSP服务
    """
    
    def __init__(self):
        """初始化RTSP探测"""
    
    def probe_rtsp(self, ip: str, port: int = 554, timeout: int = 2) -> dict:
        """
        探测IP的RTSP服务
        :return: {available: bool, server: str, supported_methods: list}
        """
    
    def probe_rtsp_streams(self, ip: str, port: int = 554, 
                          brand: str = "generic") -> list:
        """
        尝试常见RTSP URL路径，返回可访问的流URL列表
        海康: /Streaming/Channels/101
        大华: /cam/realmonitor
        宇视: /unicast/c1/s0/live
        """
```

#### 4.5.4 HTTP 探测引擎

```python
class HTTPCameraDiscovery:
    """
    HTTP协议探测引擎
    通过HTTP访问摄像头WEB管理页面获取设备信息
    """
    
    def __init__(self):
        """初始化HTTP探测"""
    
    def probe_http(self, ip: str, port: int = 80, timeout: int = 2) -> dict:
        """
        探测IP的HTTP服务
        :return: {available, title, server, brand, model, mac}
        """
    
    def get_brand_from_headers(self, headers: dict, content: str) -> str:
        """从HTTP响应头和内容识别品牌"""
    
    def get_brandspecific_info(self, ip: str, port: int, brand: str) -> dict:
        """
        调用品牌特定API获取设备信息
        海康 ISAPI: /ISAPI/System/deviceInfo
        大华 CGI: /cgi-bin/magicBox.cgi?action=getMachineName
        """
```

#### 4.5.5 品牌特征库

```python
# 品牌特征定义（内置）
BRAND_SIGNATURES = {
    "hikvision": {
        "name": "海康威视",
        "default_ports": [80, 554, 8080, 8000],
        "http_paths": {
            "/ISAPI/System/deviceInfo": "hikvision",
            "/doc/page/login.asp": "hikvision"
        },
        "http_keywords": ["Hikvision", "iVMS", "hik"],
        "rtsp_paths": [
            "/Streaming/Channels/101",
            "/Streaming/Channels/1",
            "/h264/ch1/main/av_stream"
        ],
        "rtsp_port": 554
    },
    "dahua": {
        "name": "大华",
        "default_ports": [80, 554, 8080, 37777],
        "http_paths": {
            "/cgi-bin/magicBox.cgi": "dahua",
            "/RPC2_Login": "dahua"
        },
        "http_keywords": ["Dahua", "DH", "大华"],
        "rtsp_paths": [
            "/cam/realmonitor",
            "/live/ch0",
            "/live/main"
        ],
        "rtsp_port": 554
    },
    "uniview": {
        "name": "宇视",
        "default_ports": [80, 554, 8080],
        "http_keywords": ["Uniview", "宇视", "uniview"],
        "rtsp_paths": [
            "/unicast/c1/s0/live",
            "/unicast/c1/s1/live"
        ]
    },
    "tvwall": {
        "name": "天地伟业",
        "default_ports": [80, 554, 8080],
        "http_keywords": ["TVT", "天地伟业", "tiandy"],
        "rtsp_paths": [
            "/rtsp/streaming/channels/101"
        ]
    },
    "generic": {
        "name": "通用",
        "default_ports": [554, 80, 8080, 8000, 8899, 34567, 34599],
        "rtsp_paths": [
            "/live/main",
            "/live/0/main",
            "/onvif/streaming/channels/101"
        ]
    }
}
```

#### 4.5.6 扫描结果数据

```python
@dataclass
class CameraDevice:
    ip: str
    port: int
    brand: str
    model: str
    rtsp_available: bool
    rtsp_url: str
    onvif_available: bool
    online: bool
    web_url: str
    mac_address: str
    firmware_version: str
    device_type: str           # 摄像头/NVR/DVR
    discovered_via: list       # ["onvif", "rtsp", "http"]
    timestamp: datetime
```

#### 4.5.7 子网计算工具

```python
class SubnetIterator:
    """用于生成扫描目标IP列表"""
    
    @staticmethod
    def parse_cidr(subnet: str) -> list:
        """解析CIDR格式网段，返回所有IP列表"""
    
    @staticmethod
    def iter_ips(subnet: str) -> Iterator[str]:
        """迭代网段内的每个IP"""
```

---

### 4.6 速度测试接口

#### 4.6.1 外网测速工具

```python
class ExternalSpeedTest:
    def __init__(self):
        """初始化外网测速工具"""
    
    def test_download_speed(self, url: str, timeout: int = 30) -> dict:
        """测试下载速度，返回速度(Mbps)、延迟(ms)、抖动(ms)"""
    
    def test_latency(self, host: str, count: int = 10) -> dict:
        """测试网络延迟和抖动"""
    
    def get_available_servers(self) -> list:
        """获取可用测速服务器列表"""
```

#### 4.6.2 内网测速工具（双引擎）

```python
class InternalSpeedTest:
    def __init__(self):
        """初始化内网测速工具"""
    
    def check_iperf3(self) -> bool:
        """检测系统是否已安装iPerf3"""
    
    def start_server(self, port: int = 5201, interface: str = None) -> bool:
        """启动内网测速服务端（iPerf3模式）"""
    
    def stop_server(self) -> None:
        """停止内网测速服务端"""
    
    def start_test(self, server_ip: str, port: int = 5201, 
                   duration: int = 10, mode: str = "download",
                   engine: str = "builtin") -> dict:
        """
        执行内网测速
        :param server_ip: 服务端IP地址
        :param port: 服务端端口
        :param duration: 测试时长(秒)
        :param mode: 测试模式 upload/download/bidirectional
        :param engine: 测试引擎 builtin/iperf3
        :return: 测速结果 dict
        """
    
    def stop_test(self) -> None:
        """停止当前测速"""
    
    def get_local_interfaces(self) -> list:
        """获取本机网卡列表"""
```

#### 4.6.3 内置测速引擎

```python
class BuiltinSpeedEngine:
    """使用纯Python socket实现的简易测速引擎"""
    
    def start_server(self, port: int = 5201) -> bool:
        """启动内置服务端"""
    
    def stop_server(self) -> None:
        """停止内置服务端"""
    
    def run_client(self, server_ip: str, port: int = 5201,
                   duration: int = 10, mode: str = "download") -> dict:
        """运行内置客户端测速"""
```

#### 4.6.4 iPerf3引擎

```python
class Iperf3Engine:
    """
    调用iPerf3命令行工具的测速引擎
    依赖：系统需安装iPerf3可执行文件，或打包时附带iperf3.exe
    """
    
    def __init__(self, iperf3_path: str = None):
        """
        初始化iPerf3引擎
        :param iperf3_path: iperf3可执行文件路径，None时自动查找
        """
    
    def find_iperf3(self) -> str:
        """自动查找iperf3可执行文件"""
    
    def start_server(self, port: int = 5201) -> subprocess.Popen:
        """启动iPerf3服务端进程"""
    
    def run_client(self, server_ip: str, port: int = 5201,
                   duration: int = 10, mode: str = "download",
                   reverse: bool = False) -> dict:
        """
        运行iPerf3客户端测速
        :param mode: download时reverse=True，upload时reverse=False
        :return: 解析后的测速结果
        """
    
    def parse_result(self, json_output: str) -> dict:
        """解析iPerf3 JSON输出"""
```

#### 4.6.5 会话数测试工具

```python
class SessionTest:
    def __init__(self):
        """初始化会话数测试工具"""
    
    def start_test(self, server_ip: str, server_port: int = 80,
                   delay_ms: int = 100, threads: int = 10,
                   max_connections: int = 10000, 
                   fail_limit: int = 100) -> None:
        """
        启动会话数压力测试
        :param server_ip: 目标服务器IP
        :param server_port: 目标端口
        :param delay_ms: 连接间隔延迟(毫秒)
        :param threads: 并发线程数
        :param max_connections: 最大连接数
        :param fail_limit: 失败上限，达到后自动停止
        """
    
    def stop_test(self) -> None:
        """停止会话数测试"""
    
    def get_statistics(self) -> dict:
        """获取实时统计信息"""
    
    def get_logs(self) -> list:
        """获取测试日志"""
```

### 4.7 连接测试接口

#### 4.7.1 DNS查询工具

```python
class DNSQuery:
    def __init__(self):
        """初始化DNS查询工具"""
    
    def query(self, domain: str, record_type: str = "A",
              dns_server: str = None, timeout: int = 5) -> dict:
        """
        查询DNS记录
        :param domain: 域名
        :param record_type: 记录类型 A/AAAA/CNAME/MX/TXT/NS/SOA/PTR
        :param dns_server: 指定DNS服务器，None使用系统默认
        :return: {records: list, ttl: int, authoritative: bool}
        """
    
    def query_all_types(self, domain: str) -> dict:
        """查询所有类型的DNS记录"""
    
    def reverse_query(self, ip: str) -> str:
        """反向DNS查询（IP转域名）"""
```

#### 4.7.2 DNS优选工具

```python
class DNSOptimizer:
    # 内置公共DNS服务器列表
    DNS_SERVERS = [
        ("114 DNS", "114.114.114.114"),
        ("阿里DNS", "223.5.5.5"),
        ("腾讯DNS", "119.29.29.29"),
        ("Google DNS", "8.8.8.8"),
        ("Cloudflare", "1.1.1.1"),
        ("百度DNS", "180.76.76.76"),
    ]
    
    def __init__(self):
        """初始化DNS优选工具"""
    
    def test_dns_speed(self, dns_server: str, test_domain: str = "www.baidu.com",
                       count: int = 5, timeout: int = 2) -> dict:
        """
        测试单个DNS服务器响应速度
        :return: {avg_time, min_time, max_time, success_rate, ip_resolved}
        """
    
    def test_all_dns(self, test_domain: str = "www.baidu.com") -> list:
        """测试所有内置DNS服务器，返回按速度排序的结果列表"""
    
    def get_recommended_dns(self) -> dict:
        """获取推荐的DNS服务器（速度最快的）"""
```

#### 4.7.3 站点测试工具

```python
class WebsiteTester:
    def __init__(self):
        """初始化站点测试工具"""
    
    def test_site(self, url: str, timeout: int = 10) -> dict:
        """
        测试单个站点可访问性
        :return: {url, status_code, response_time, title, server, available}
        """
    
    def test_sites_batch(self, urls: list, threads: int = 10) -> list:
        """批量测试站点，返回结果列表"""
    
    def check_ssl(self, url: str) -> dict:
        """检查站点SSL证书状态"""
```

#### 4.7.4 Telnet端口测试工具

```python
class TelnetTester:
    def __init__(self):
        """初始化Telnet测试工具"""
    
    def test_port(self, host: str, port: int, timeout: int = 5) -> dict:
        """
        Telnet方式测试端口连通性
        :return: {host, port, connected, response_time, banner}
        """
    
    def start_interactive(self, host: str, port: int = 23) -> None:
        """启动交互式Telnet终端"""
    
    def send_command(self, command: str) -> str:
        """在交互模式下发送命令"""
```

#### 4.7.5 MTU测试工具

```python
class MTUTester:
    def __init__(self):
        """初始化MTU测试工具"""
    
    def test_mtu(self, host: str, max_size: int = 1500,
                 min_size: int = 576, timeout: int = 2) -> dict:
        """
        通过二分法测试路径MTU
        原理：发送不同大小的ICMP包（设置DF标志），找到最大不分片大小
        :return: {mtu, tested_count, host, success}
        """
    
    def ping_with_size(self, host: str, size: int, timeout: int = 2) -> bool:
        """发送指定大小的Ping包（DF标志）"""
```

#### 4.7.6 SSL检测工具

```python
class SSLChecker:
    def __init__(self):
        """初始化SSL检测工具"""
    
    def check_certificate(self, host: str, port: int = 443,
                          timeout: int = 10) -> dict:
        """
        检测SSL证书信息
        :return: {
            subject, issuer, serial_number,
            not_before, not_after, days_remaining,
            signature_algorithm, version,
            san_list,              # 主体可选名称
            chain_info,            # 证书链
            is_valid, is_expired, is_trusted
        }
        """
    
    def get_certificate_chain(self, host: str, port: int = 443) -> list:
        """获取完整证书链"""
    
    def check_weak_ciphers(self, host: str, port: int = 443) -> list:
        """检查弱加密算法"""
```

#### 4.7.7 密码生成工具

```python
class PasswordGenerator:
    def __init__(self):
        """初始化密码生成工具"""
    
    def generate(self, length: int = 16,
                 use_upper: bool = True,
                 use_lower: bool = True,
                 use_digits: bool = True,
                 use_special: bool = True,
                 exclude_chars: str = "",
                 exclude_ambiguous: bool = False) -> str:
        """
        生成随机密码
        :param length: 密码长度
        :param use_upper/lower/digits/special: 是否包含各类字符
        :param exclude_chars: 要排除的字符
        :param exclude_ambiguous: 排除易混淆字符 (0/O/1/l/I等)
        """
    
    def generate_multiple(self, count: int = 5, **kwargs) -> list:
        """批量生成密码"""
    
    def check_strength(self, password: str) -> dict:
        """
        检查密码强度
        :return: {score: 0-100, level: 弱/中/强/很强, suggestions: list}
        """
```

#### 4.7.8 NSLookup工具

```python
class NSLookup:
    def __init__(self):
        """初始化NSLookup工具"""
    
    def lookup(self, domain: str, dns_server: str = None,
               record_type: str = "A", timeout: int = 5) -> dict:
        """
        NSLookup查询
        :return: {domain, record_type, dns_server, answers: list, authority: list}
        """
    
    def get_authoritative_ns(self, domain: str) -> list:
        """获取域名的权威DNS服务器"""
```

#### 4.7.9 Traceroute工具

```python
class TracerouteTool:
    def __init__(self):
        """初始化路由追踪工具"""
    
    def trace(self, host: str, max_hops: int = 30,
              timeout: int = 2, probe_count: int = 3) -> list:
        """
        执行路由追踪
        :return: TracerouteResult列表
        """
    
    def trace_async(self, host: str, callback: callable) -> None:
        """异步路由追踪，每跳完成后回调"""
```

#### 4.7.10 Whois查询工具

```python
class WhoisQuery:
    # 内置Whois服务器
    WHOIS_SERVERS = {
        ".com": "whois.verisign-grs.com",
        ".net": "whois.verisign-grs.com",
        ".org": "whois.publicinterestregistry.org",
        ".cn": "whois.cnnic.cn",
        ".io": "whois.nic.io",
    }
    
    def __init__(self):
        """初始化Whois查询工具"""
    
    def query(self, domain: str, timeout: int = 10) -> dict:
        """
        查询域名Whois信息
        :return: {
            domain, registrar, creation_date, expiration_date,
            updated_date, name_servers, status, registrant, raw_text
        }
        """
    
    def get_whois_server(self, domain: str) -> str:
        """根据域名后缀获取Whois服务器"""
    
    def parse_whois_response(self, response: str) -> dict:
        """解析Whois响应文本"""
```

#### 4.7.11 HTTP Headers工具

```python
class HTTPHeaders:
    def __init__(self):
        """初始化HTTP Headers工具"""
    
    def get_headers(self, url: str, timeout: int = 10,
                    follow_redirects: bool = True) -> dict:
        """
        获取HTTP响应头
        :return: {
            status_code, headers: dict, 
            redirect_chain: list, server, content_type,
            response_time, ip_address
        }
        """
    
    def analyze_security_headers(self, headers: dict) -> dict:
        """
        分析安全相关HTTP头
        检查: HSTS, CSP, X-Frame-Options, X-Content-Type-Options等
        :return: {security_score, warnings: list, recommendations: list}
        """
```

---

## 5. 数据库与数据结构设计

### 5.1 配置文件结构

```json
{
  "app": {
    "theme": "system",
    "language": "zh_CN",
    "auto_update": false,
    "window_size": [1200, 800],
    "window_position": [100, 100]
  },
  "network": {
    "ping_count": 4,
    "ping_timeout": 1,
    "scan_threads": 100,
    "scan_timeout": 1,
    "traceroute_max_hops": 30
  },
  "servers": {
    "tftp_port": 69,
    "tftp_root": "./tftp_root",
    "ftp_port": 21,
    "ftp_root": "./ftp_root",
    "syslog_port": 514
  },
  "history": {
    "recent_hosts": [],
    "recent_scans": [],
    "recent_pings": []
  }
}
```

### 5.2 数据结构定义

#### 5.2.1 Ping结果

```python
@dataclass
class PingResult:
    host: str
    ip_address: str
    avg_latency: float
    min_latency: float
    max_latency: float
    packet_loss: float
    success: bool
    timestamp: datetime
```

#### 5.2.2 端口扫描结果

```python
@dataclass
class PortScanResult:
    host: str
    port: int
    status: str
    service: str
    protocol: str
    timestamp: datetime
```

#### 5.2.3 路由追踪结果

```python
@dataclass
class TracerouteResult:
    hop: int
    ip_address: str
    hostname: str
    latency: float
    status: str
```

#### 5.2.4 进程信息

```python
@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    memory_rss: int
    create_time: datetime
    username: str
    executable: str
```

#### 5.2.5 防火墙规则

```python
@dataclass
class FirewallRule:
    name: str
    protocol: str
    local_port: str
    remote_port: str
    action: str
    direction: str
    enabled: bool
    profiles: str
```

#### 5.2.6 系统日志

```python
@dataclass
class SystemLog:
    record_id: str
    time_created: datetime
    level: str
    source: str
    event_id: int
    message: str
```

#### 5.2.7 外网测速结果

```python
@dataclass
class SpeedTestResult:
    server_name: str
    server_url: str
    download_speed: float      # Mbps
    latency: float             # ms
    jitter: float              # ms
    status: str                # 成功/失败
    timestamp: datetime
    error_message: str = ""
```

#### 5.2.8 内网测速结果

```python
@dataclass
class InternalSpeedResult:
    server_ip: str
    port: int
    mode: str                  # upload/download/bidirectional
    engine: str                # builtin/iperf3
    duration: int              # 秒
    bandwidth: float           # Mbps
    latency: float             # ms
    retransmits: int
    status: str
    timestamp: datetime
```

#### 5.2.9 会话数测试结果

```python
@dataclass
class SessionTestResult:
    server_ip: str
    server_port: int
    total_connections: int
    success_count: int
    fail_count: int
    duration: float            # 秒
    threads: int
    max_connections: int
    status: str
    timestamp: datetime
```

#### 5.2.10 DNS查询结果

```python
@dataclass
class DNSQueryResult:
    domain: str
    record_type: str           # A/AAAA/CNAME/MX/TXT/NS/SOA/PTR
    dns_server: str
    records: list              # 解析记录列表
    ttl: int
    authoritative: bool        # 是否权威应答
    response_time: float       # ms
    status: str
    timestamp: datetime
```

#### 5.2.11 DNS优选结果

```python
@dataclass
class DNSOptimizeResult:
    server_name: str           # "114 DNS"
    server_ip: str             # "114.114.114.114"
    avg_response_time: float   # ms
    min_response_time: float
    max_response_time: float
    success_rate: float        # 0-100
    resolved_ip: str           # 解析到的IP
    rank: int                  # 速度排名
```

#### 5.2.12 站点测试结果

```python
@dataclass
class WebsiteTestResult:
    url: str
    status_code: int           # HTTP状态码
    response_time: float       # ms
    title: str                 # 网页标题
    server: str                # 服务器类型
    content_type: str
    available: bool
    ssl_valid: bool
    ip_address: str
    timestamp: datetime
    error_message: str = ""
```

#### 5.2.13 SSL证书信息

```python
@dataclass
class SSLCertificateInfo:
    host: str
    port: int
    subject: str               # 证书主体
    issuer: str                # 颁发者
    serial_number: str
    not_before: datetime       # 生效时间
    not_after: datetime        # 过期时间
    days_remaining: int        # 剩余天数
    signature_algorithm: str
    version: int
    san_list: list             # 主体可选名称
    is_valid: bool
    is_expired: bool
    is_trusted: bool
```

#### 5.2.14 Whois查询结果

```python
@dataclass
class WhoisResult:
    domain: str
    registrar: str             # 注册商
    creation_date: datetime    # 注册时间
    expiration_date: datetime  # 到期时间
    updated_date: datetime     # 更新时间
    name_servers: list         # DNS服务器
    status: list               # 域名状态
    registrant: str            # 注册人
    raw_text: str              # 原始文本
    query_time: float          # 查询耗时(ms)
```

#### 5.2.15 MTU测试结果

```python
@dataclass
class MTUTestResult:
    host: str
    mtu: int                   # 探测到的MTU
    tested_count: int          # 测试次数
    success: bool
    suggestions: str           # 建议的MTU设置
    timestamp: datetime
```

---

## 6. UI设计

### 6.1 主窗口布局

```
┌─────────────────────────────────────────────────────────────┐
│  标题栏 (应用名称 + 最小化/最大化/关闭按钮)                   │
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

### 6.2 导航菜单结构

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
│   └── 路由表查看
├── 网络分析
│   ├── 数据包抓包
│   ├── 协议分析
│   ├── DHCP检测
│   ├── WiFi分析
│   └── 摄像头扫描
├── 安全模块
│   ├── 本机安全自测
│   ├── 安全日志审计
│   └── 防火墙配置
├── 速度测试
│   ├── 外网测速
│   └── 内网测速
├── 网络服务
│   ├── TFTP服务器
│   ├── FTP服务器
│   ├── HTTP文件分发
│   ├── Syslog服务器
│   └── DHCP服务器
├── 远程工具
│   ├── SSH终端
│   ├── 远程桌面
│   └── 串口调试
├── 连接测试
│   ├── DNS查询
│   ├── DNS优选
│   ├── 站点测试
│   ├── Telnet端口
│   ├── MTU测试
│   ├── SSL检测
│   ├── 密码生成
│   ├── NSLookup
│   ├── Traceroute
│   ├── Whois查询
│   └── HTTP Headers
├── 监控运维
│   ├── 链路监控
│   └── 流量监控
└── 设置
    ├── 本机设置
    └── 关于本软件
```

### 6.3 页面设计规范

#### 6.3.1 通用布局模式

```
┌─────────────────────────────────────────────────────────────┐
│  页面标题                                                   │
├─────────────────────────────────────────────────────────────┤
│  工具栏 (操作按钮/参数设置)                                   │
├─────────────────────────────────────────────────────────────┤
│  内容区域                                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                        │ │
│  │   功能组件 (表格/图表/终端/表单)                         │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  状态栏/日志输出                                            │
└─────────────────────────────────────────────────────────────┘
```

#### 6.3.2 颜色规范

| 颜色类型 | RGB值 | 用途 |
|----------|-------|------|
| 主色调 | #1E90FF | 按钮/选中状态 |
| 成功 | #00B894 | 成功状态指示 |
| 警告 | #FDCB6E | 警告状态指示 |
| 错误 | #FF6B6B | 错误状态指示 |
| 背景 | #F5F6FA | 页面背景 |
| 卡片 | #FFFFFF | 卡片背景 |
| 文字 | #2D3436 | 主要文字 |
| 次要文字 | #636E72 | 次要文字 |

#### 6.3.3 图标规范

- 使用系统图标（Windows自带）
- 图标大小：16x16 / 24x24 / 32x32
- 通过 Qt 的 `QIcon.fromTheme()` 或 `QStyle.standardIcon()` 获取

### 6.4 核心页面设计

#### 6.4.1 仪表盘页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 顶部统计卡 | CPU/内存/磁盘/网络使用率 | 进度条 + 数值 |
| 连通性状态 | 网关/DNS/互联网延迟 | 状态指示灯 + 延迟值 |
| 进程列表 | 占用资源最高的进程 | 表格 |
| 系统日志 | 最近系统事件 | 列表 |
| 快速启动栏 | 常用功能快捷入口 | 按钮组 |

#### 6.4.2 Ping测试页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 标签页 | 单个Ping/批量Ping/网段Ping/TCP Ping | QTabWidget |
| 参数设置 | 目标地址/次数/超时/间隔 | 输入框 + 下拉框 |
| 结果展示 | Ping结果表格/延迟图表 | QTableView + QChart |
| 操作按钮 | 开始/停止/导出结果 | 按钮组 |

#### 6.4.3 端口扫描页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 参数设置 | 目标地址/端口范围/线程数/超时 | 输入框 + 滑块 |
| 扫描状态 | 进度条/已发现端口数/扫描速度 | 进度条 + 标签 |
| 结果展示 | 端口列表（端口/状态/服务） | QTableView |
| 操作按钮 | 开始/停止/导出/保存配置 | 按钮组 |

#### 6.4.4 防火墙配置页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 标签页 | 快捷配置/高级规则/规则管理 | QTabWidget |
| 规则列表 | 所有防火墙规则 | QTableView |
| 规则详情 | 选中规则的详细信息 | 表单 |
| 操作按钮 | 添加/删除/启用/禁用/导入/导出 | 按钮组 |

#### 6.4.5 外网测速页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试配置 | 测速服务器选择（华为云/腾讯云/阿里云等） | QComboBox |
| 操作按钮 | 开始测试/停止 | 按钮组 |
| 实时指标 | 下载速度(Mbps)/网络延迟(ms)/网络抖动(ms) | 大字体标签 |
| 状态提示 | 准备就绪/测试中/测试完成 | 状态标签 |
| 温馨提示 | 不同运营商网络环境差异提示 | 提示标签 |
| 更多站点 | 外部在线测速链接（中科大/Speedtest.cn/Speedtest.net） | 链接按钮 |
| 结果详情 | 本次测速详细结果 | 文本区域 |

#### 6.4.6 内网测速页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 服务端模式 | 监听端口/本机网卡选择/启动停止按钮 | 输入框+下拉框+按钮 |
| 客户端模式 | 服务器IP/端口/测试时长/测试模式 | 输入框+单选按钮 |
| 测试引擎 | 内置引擎 / iPerf3（自动检测可用性） | 单选按钮+状态标签 |
| 操作按钮 | 开始测速/停止测试 | 按钮组 |
| 服务端状态 | 等待启动/运行中/已停止 | 状态区域 |
| 测试结果 | 速度/延迟/丢包率 | 结果展示区域 |

#### 6.4.7 会话数测试页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试配置 | 服务器选择（主/备）/延迟/线程数/最大连接/失败上限 | 输入框+单选按钮 |
| 操作按钮 | 开始测试/停止 | 按钮组 |
| 实时统计 | 成功连接数/失败次数/运行时间 | 大数字显示 |
| 运行日志 | 测试过程实时日志输出 | 日志文本区域 |

#### 6.4.8 摄像头扫描页面

| 区域 | 内容 | 组件 |
|------|------|------|
| 扫描参数 | 网络范围（CIDR格式） | QLineEdit |
| 扫描品牌 | 海康威视/大华/宇视/天地伟业/通用（多选） | 复选框组 |
| 扫描模式 | 快速扫描/深度扫描/ONVIF发现 | QRadioButton |
| 线程数 | 默认50 | QSpinBox |
| 超时(秒) | 默认2 | QSpinBox |
| 操作按钮 | 开始扫描/停止扫描/清空结果/导出清单 | 按钮组 |
| 统计区 | 扫描IP数/已检测/发现数/进度% | 标签+进度条 |
| 扫描结果 | 每行：[IP] [端口] [品牌] [型号] [RTSP可用] [状态] [Web URL] [MAC] | 表格 |
| 扫描说明 | 协议支持/扫描限制/扫描建议（右侧边栏） | 富文本框 |

#### 6.4.9 连接测试页面（11标签页）

**整体布局**：左侧为标签页选择，右侧为对应功能内容区。

**标签页1：DNS查询**

| 区域 | 内容 | 组件 |
|------|------|------|
| 查询参数 | 域名输入/记录类型(A/AAAA/CNAME/MX/TXT/NS/SOA/PTR)/DNS服务器 | 输入框+下拉框 |
| 操作按钮 | 查询/清空 | 按钮组 |
| 结果展示 | 记录值/TTL/类型 | 表格 |
| 详情区 | 权威应答/响应时间/原始报文 | 文本区域 |

**标签页2：DNS优选**

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试域名 | 默认 www.baidu.com | 输入框 |
| 操作按钮 | 开始测试/应用推荐DNS | 按钮组 |
| 结果列表 | [DNS名称] [IP] [平均延迟] [成功率] [排名] | 表格 |
| 推荐区 | 显示速度最快的DNS及设置建议 | 高亮卡片 |

**标签页3：站点测试**

| 区域 | 内容 | 组件 |
|------|------|------|
| 站点列表 | 多URL输入（每行一个） | 文本编辑框 |
| 线程数 | 默认10 | QSpinBox |
| 超时(秒) | 默认10 | QSpinBox |
| 操作按钮 | 开始测试/停止/清空/导入URL | 按钮组 |
| 结果列表 | [URL] [状态码] [响应时间] [标题] [服务器] [可用] [SSL] | 表格 |
| 导出按钮 | 导出CSV | 按钮 |

**标签页4：Telnet端口**

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试参数 | 目标IP/端口/超时 | 输入框 |
| 操作按钮 | 测试连通性/打开交互终端 | 按钮组 |
| 快速测试结果 | 连接状态/响应时间/Banner | 结果展示 |
| 交互终端 | Telnet交互式终端（支持发送命令） | 终端控件 |

**标签页5：MTU测试**

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试参数 | 目标IP/最大包大小(默认1500)/最小包大小(默认576) | 输入框 |
| 操作按钮 | 开始测试 | 按钮组 |
| 结果展示 | 探测到的MTU值/测试次数/建议设置 | 结果卡片 |
| 测试过程 | 实时显示每次测试的包大小和结果 | 日志区域 |

**标签页6：SSL检测**

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试参数 | 域名/端口(默认443) | 输入框 |
| 操作按钮 | 检测证书 | 按钮组 |
| 证书信息 | 主体/颁发者/序列号/有效期/算法/版本 | 表单 |
| 证书链 | 完整证书链展示 | 树形控件 |
| 安全检查 | 弱加密算法检查结果 | 检查列表 |
| 状态指示 | 有效/过期/不受信任 | 状态标签 |

**标签页7：密码生成**

| 区域 | 内容 | 组件 |
|------|------|------|
| 密码长度 | 滑块+数值(8-64) | QSpinBox+QSlider |
| 字符集 | 大写/小写/数字/特殊字符 | 复选框 |
| 排除字符 | 用户指定排除的字符 | 输入框 |
| 排除易混淆 | 排除 0/O/1/l/I 等 | 复选框 |
| 操作按钮 | 生成密码/批量生成5个/复制 | 按钮组 |
| 生成结果 | 生成的密码（大字体显示） | 显示框 |
| 强度检测 | 密码强度评分/等级/建议 | 进度条+标签 |

**标签页8：NSLookup**

| 区域 | 内容 | 组件 |
|------|------|------|
| 查询参数 | 域名/DNS服务器(可选)/记录类型 | 输入框+下拉框 |
| 操作按钮 | 查询/清空 | 按钮组 |
| 查询结果 | 应答记录/权威NS/附加记录 | 树形控件 |
| 原始输出 | 类似系统nslookup命令的原始输出 | 文本区域 |

**标签页9：Traceroute**

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试参数 | 目标主机/最大跳数(默认30)/超时(秒) | 输入框 |
| 操作按钮 | 开始追踪/停止 | 按钮组 |
| 结果列表 | [跳数] [IP] [主机名] [延迟1/2/3] [状态] | 表格 |
| 实时显示 | 每跳完成后实时更新 | 动态表格 |

**标签页10：Whois查询**

| 区域 | 内容 | 组件 |
|------|------|------|
| 查询参数 | 域名输入 | 输入框 |
| 操作按钮 | 查询 | 按钮组 |
| 解析结果 | 注册商/注册时间/到期时间/更新时间/NS/状态/注册人 | 表单 |
| 原始文本 | Whois服务器返回的原始内容 | 文本区域 |

**标签页11：HTTP Headers**

| 区域 | 内容 | 组件 |
|------|------|------|
| 测试参数 | URL输入/是否跟随重定向 | 输入框+复选框 |
| 操作按钮 | 获取Headers | 按钮组 |
| 响应头 | 所有HTTP响应头键值对 | 表格 |
| 重定向链 | 重定向路径展示 | 列表 |
| 安全分析 | HSTS/CSP/X-Frame-Options等安全头检查/安全评分 | 检查列表+评分 |

---

## 7. 安全性设计

### 7.1 权限管理

#### 7.1.1 权限检测机制

```python
import ctypes
import sys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False
```

#### 7.1.2 权限提示流程

```
用户执行需要管理员权限的功能
        ↓
检测当前权限
        ↓
┌─────────────┐
│ 是管理员？   │
└──────┬──────┘
       │
  ┌────┴────┐
  ↓         ↓
 是         否
  ↓         ↓
执行功能   弹出警告对话框
           提示用户以管理员身份运行
```

#### 7.1.3 需要管理员权限的功能清单

| 功能 | 权限要求 | 原因 |
|------|----------|------|
| 防火墙配置 | 管理员 | 修改系统防火墙规则 |
| 安全日志审计 | 管理员 | 读取安全日志需要高权限 |
| 数据包抓包 | 管理员 | npcap驱动需要管理员权限 |
| 路由表修改 | 管理员 | 修改系统路由表 |
| 进程管理（结束） | 管理员 | 结束系统进程 |
| 修改远程端口 | 管理员 | 修改注册表 |

### 7.2 输入验证

#### 7.2.1 验证规则

| 输入类型 | 验证规则 | 错误提示 |
|----------|----------|----------|
| IP地址 | 符合IPv4/IPv6格式 | "请输入有效的IP地址" |
| 端口号 | 1-65535 | "端口号必须在1-65535之间" |
| 主机名 | 符合域名格式 | "请输入有效的主机名" |
| 子网掩码 | 符合CIDR或点分十进制格式 | "请输入有效的子网掩码" |
| 超时时间 | 大于0的整数 | "超时时间必须大于0" |
| 线程数 | 1-500 | "线程数必须在1-500之间" |

#### 7.2.2 验证方式

- 使用正则表达式验证格式
- 使用范围检查验证数值
- 在UI层实现实时验证（输入时立即反馈）
- 在业务层实现二次验证（防止绕过UI）

### 7.3 命令注入防护

#### 7.3.1 风险点

- 用户输入作为系统命令参数
- 用户输入作为文件路径
- 用户输入作为网络请求参数

#### 7.3.2 防护措施

| 风险点 | 防护措施 |
|--------|----------|
| 系统命令参数 | 使用subprocess的列表形式，避免字符串拼接 |
| 文件路径 | 使用pathlib处理路径，验证路径安全性 |
| 网络请求参数 | 使用requests的参数传递，自动编码 |
| 用户输入 | 对特殊字符进行过滤和转义 |

#### 7.3.3 安全示例

```python
# 不安全方式
command = f"ping {user_input}"
subprocess.run(command, shell=True)

# 安全方式
subprocess.run(["ping", user_input], shell=False)
```

### 7.4 数据保护

#### 7.4.1 敏感数据处理

| 数据类型 | 处理方式 |
|----------|----------|
| 密码/密钥 | 不存储明文，使用加密存储 |
| 扫描结果 | 本地存储，不上传云端 |
| 配置文件 | JSON格式，无敏感信息 |

#### 7.4.2 日志安全

- 日志中不记录密码等敏感信息
- 日志文件权限设置为仅当前用户可读
- 定期清理旧日志

---

## 8. 性能设计

### 8.1 并发处理

#### 8.1.1 线程池配置

| 场景 | 线程数 | 理由 |
|------|--------|------|
| Ping测试 | 50-100 | 网络IO密集，需要高并发 |
| 端口扫描 | 100-300 | 大量连接尝试，需要高并发 |
| 主机发现 | 100-200 | 网段扫描，需要高并发 |
| 数据采集 | 4-8 | CPU密集，避免过多线程 |

#### 8.1.2 线程安全

- 使用Qt信号槽机制更新UI（跨线程安全）
- 使用锁保护共享数据
- 使用原子操作更新统计信息

### 8.2 资源优化

#### 8.2.1 内存优化

| 措施 | 说明 |
|------|------|
| 懒加载 | 按需加载模块，减少启动时间 |
| 对象复用 | 复用表格模型等大型对象 |
| 数据分页 | 大量数据时分页显示 |
| 定时清理 | 清理不再使用的对象 |

#### 8.2.2 CPU优化

| 措施 | 说明 |
|------|------|
| 批量更新UI | 减少UI刷新频率 |
| 异步处理 | 耗时操作放入线程 |
| 算法优化 | 使用高效算法 |

### 8.3 响应时间要求

| 操作 | 响应时间 | 说明 |
|------|----------|------|
| 页面切换 | <200ms | UI操作 |
| 单主机Ping | <1s | 网络操作 |
| 端口扫描(100端口) | <10s | 并发操作 |
| 进程列表刷新 | <500ms | 系统调用 |
| 日志查询 | <1s | 文件操作 |

---

## 9. 兼容性设计

### 9.1 Windows版本兼容

#### 9.1.1 版本差异处理

| 功能 | Win7 | Win10/11 | 处理方式 |
|------|------|-----------|----------|
| 防火墙命令 | `netsh advfirewall` | `netsh advfirewall` | 基本一致，部分子命令需适配 |
| 日志查询 | `wevtutil` | `wevtutil` | 完全一致 |
| 进程管理 | WMI | WMI | 完全一致 |
| 网络信息 | `ipconfig` | `ipconfig` | 完全一致 |
| TLS支持 | 有限 | 完整 | requests额外配置 |

#### 9.1.2 Python版本要求

- Windows 7：Python 3.9（最后支持Win7的版本）
- Windows 10/11：Python 3.9+

#### 9.1.3 依赖库版本限制

| 库 | Win7兼容版本 | 说明 |
|----|-------------|------|
| PySide6 | 6.5.x | 新版本可能不支持Win7 |
| scapy | 2.5.x | 新版本可能不支持Win7 |
| matplotlib | 3.5.x | 新版本可能不支持Win7 |
| requests | 2.31.x | 需要TLS配置 |

### 9.2 高DPI支持

#### 9.2.1 DPI感知配置

```python
import ctypes

ctypes.windll.shcore.SetProcessDpiAwareness(2)
```

#### 9.2.2 UI缩放策略

- 使用Qt的高DPI支持
- 使用布局管理器自适应
- 避免固定尺寸控件
- 使用矢量图标

---

## 10. 打包部署设计

### 10.1 PyInstaller配置

#### 10.1.1 spec文件结构

```python
a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets/', 'assets'),
        ('docs/', 'docs')
    ],
    hiddenimports=[
        'scapy',
        'psutil',
        'paramiko',
        'pyserial'
    ],
    excludes=[
        'matplotlib.backends',
        'matplotlib.tests',
        'scapy.layers.all'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NetworkToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico'
)
```

#### 10.1.2 打包优化策略

| 策略 | 说明 | 预期效果 |
|------|------|----------|
| 排除不必要模块 | 排除matplotlib后端、测试代码等 | 减少10-20MB |
| UPX压缩 | 使用UPX压缩可执行文件 | 减少30-40%体积 |
| 单文件模式 | 打包为单个exe文件 | 方便分发 |
| 延迟加载 | 按需加载模块 | 减少启动时间 |

#### 10.1.3 依赖处理

| 依赖 | 处理方式 |
|------|----------|
| npcap | 安装包中包含npcap安装程序，首次运行时提示安装 |
| iperf3 | 打包时附带iperf3.exe，放置于程序目录内 |
| 系统图标 | 使用Qt内置图标，无需额外资源 |
| 配置文件 | 运行时创建，存储在用户目录 |

#### 10.1.4 iPerf3 集成方案

| 方案 | 说明 | 优缺点 |
|------|------|--------|
| 打包附带 | 将iperf3.exe放入assets目录，运行时自动查找 | 体积增加约1MB，无需用户手动安装 |
| 用户自备 | 检测系统是否已安装iperf3，未安装时提示下载 | 体积无增加，需要用户手动操作 |
| **推荐** | 打包附带 + 路径自动查找 + 用户自定义路径 | 开箱即用，同时支持高级用户自定义 |

**iPerf3 调用方式**：
```python
import subprocess
import json

# 启动服务端
server_proc = subprocess.Popen(
    ["iperf3", "-s", "-p", "5201", "-J"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# 运行客户端（JSON输出便于解析）
result = subprocess.run(
    ["iperf3", "-c", "192.168.1.100", "-p", "5201",
     "-t", "10", "-J", "-R"],  # -R表示反向测试（测下载速度）
    capture_output=True,
    text=True
)
data = json.loads(result.stdout)
```

**Win7兼容性说明**：
- iperf3官方Windows版本支持Win7及以上
- 使用iperf3 3.1.3或更新版本
- 若Win7上运行异常，回退到内置引擎

### 10.2 安装包结构

```
NetworkToolkit_Setup.exe
├── NetworkToolkit.exe (主程序)
├── npcap-installer.exe (抓包驱动)
├── iperf3.exe (内网测速工具)
├── assets/ (资源文件)
│   └── icon.ico
├── docs/ (文档)
│   └── README.md
└── config/ (配置文件，运行时创建)
    └── settings.json
```

### 10.3 启动流程

```
用户双击 NetworkToolkit.exe
        ↓
检查是否以管理员身份运行
        ↓
┌─────────────┐
│ 是管理员？   │
└──────┬──────┘
       │
  ┌────┴────┐
  ↓         ↓
 是         否
  ↓         ↓
继续启动   检查是否有需要管理员权限的功能
           如有，弹出提示但继续启动
           普通功能仍可使用
        ↓
加载配置文件
        ↓
初始化主窗口
        ↓
显示仪表盘页面
        ↓
等待用户操作
```

---

## 11. 错误处理设计

### 11.1 错误分类

| 错误类型 | 说明 | 处理方式 |
|----------|------|----------|
| 网络错误 | 连接失败/超时/不可达 | 提示用户检查网络 |
| 权限错误 | 权限不足 | 提示用户以管理员身份运行 |
| 配置错误 | 配置文件损坏/缺失 | 使用默认配置 |
| 依赖错误 | 缺少必要依赖 | 提示用户安装依赖 |
| 系统错误 | 系统API调用失败 | 记录日志并提示用户 |
| 输入错误 | 用户输入无效 | 实时验证并提示 |

### 11.2 错误处理流程

```
捕获异常
        ↓
记录日志 (详细错误信息)
        ↓
确定错误类型
        ↓
生成用户友好的错误提示
        ↓
显示错误对话框
        ↓
提供解决方案建议
```

### 11.3 错误对话框设计

| 组件 | 内容 |
|------|------|
| 图标 | 根据错误类型显示不同图标（警告/错误/信息） |
| 标题 | 错误类型描述 |
| 内容 | 详细错误信息（用户友好） |
| 解决方案 | 提供解决建议 |
| 按钮 | 确定/重试/帮助 |

---

## 12. 测试计划

### 12.1 单元测试

| 模块 | 测试内容 | 测试方法 |
|------|----------|----------|
| 网络工具 | Ping/端口扫描/路由追踪 | 模拟网络环境 |
| 系统工具 | 进程管理/防火墙/日志 | 本地测试 |
| 配置管理 | 配置读写/默认值 | 单元测试 |
| 权限检测 | 管理员权限检测 | 模拟权限环境 |
| 输入验证 | 各种输入格式验证 | 参数化测试 |

### 12.2 集成测试

| 测试场景 | 测试内容 |
|----------|----------|
| 完整Ping流程 | 从UI输入到结果展示 |
| 完整扫描流程 | 从参数设置到结果导出 |
| 权限提示流程 | 非管理员运行需要权限的功能 |
| 页面切换 | 各页面间切换无卡顿 |
| 配置持久化 | 修改配置后重启验证 |

### 12.3 兼容性测试

| 测试环境 | 测试内容 |
|----------|----------|
| Windows 7 | 所有功能基本可用 |
| Windows 10 | 所有功能正常 |
| Windows 11 | 所有功能正常 |
| 不同DPI | UI显示正常 |

### 12.4 性能测试

| 测试项 | 目标 |
|--------|------|
| 启动时间 | <3秒 |
| 页面切换 | <200ms |
| 端口扫描(100端口) | <10秒 |
| 内存占用 | <100MB |

---

## 13. 代码规范

### 13.1 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块名 | 小写，下划线分隔 | `ping_tool.py` |
| 类名 | 大驼峰 | `class PingTool:` |
| 方法名 | 小写，下划线分隔 | `def ping_host(self):` |
| 变量名 | 小写，下划线分隔 | `max_threads = 100` |
| 常量名 | 大写，下划线分隔 | `TIMEOUT = 5` |

### 13.2 代码结构

```python
# 文件头部注释
"""
模块说明
"""

# 导入（标准库/第三方库/本地模块）
import os
import sys
from PySide6.QtWidgets import QWidget
from core.utils import Logger

# 类定义
class MyClass:
    """类说明"""
    
    def __init__(self):
        """初始化"""
        pass
    
    def method(self, param):
        """方法说明"""
        pass
```

### 13.3 日志规范

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| DEBUG | 调试信息 | 函数入口/参数/返回值 |
| INFO | 普通信息 | 功能启动/完成 |
| WARNING | 警告信息 | 非关键错误/异常情况 |
| ERROR | 错误信息 | 功能失败/异常 |
| CRITICAL | 严重错误 | 程序崩溃/无法恢复 |

---

## 14. 附录

### 14.1 需要管理员权限的系统命令清单

| 命令 | 用途 |
|------|------|
| `netsh advfirewall` | 防火墙配置 |
| `wevtutil` | 日志查询 |
| `route` | 路由表管理 |
| `reg` | 注册表操作 |
| `taskkill` | 结束进程 |

### 14.2 常用端口列表

| 端口 | 服务 |
|------|------|
| 21 | FTP |
| 22 | SSH |
| 23 | Telnet |
| 25 | SMTP |
| 53 | DNS |
| 80 | HTTP |
| 443 | HTTPS |
| 3389 | RDP |

### 14.3 项目目录结构

```
project_03_network-testing-toolkit/
├── src/
│   ├── main.py                    # 入口文件
│   ├── app.py                     # 主应用类
│   ├── ui/
│   │   ├── main_window.py         # 主窗口
│   │   ├── widgets/               # 自定义控件
│   │   │   ├── chart_widget.py    # 图表控件
│   │   │   ├── terminal_widget.py # 终端控件
│   │   │   └── table_widget.py    # 表格控件
│   │   └── pages/                 # 功能页面
│   │       ├── dashboard.py       # 仪表盘
│   │       ├── ping_test.py       # Ping测试
│   │       ├── port_scan.py       # 端口扫描
│   │       └── ...                # 其他页面
│   ├── core/
│   │   ├── network/               # 网络工具
│   │   │   ├── ping.py            # Ping工具
│   │   │   ├── port_scanner.py    # 端口扫描
│   │   │   ├── traceroute.py      # 路由追踪
│   │   │   └── packet_capture.py  # 抓包工具
│   │   ├── system/                # 系统工具
│   │   │   ├── process_manager.py # 进程管理
│   │   │   ├── firewall.py        # 防火墙管理
│   │   │   └── log_auditor.py     # 日志审计
│   │   ├── servers/               # 服务器模块
│   │   │   ├── tftp_server.py     # TFTP服务器
│   │   │   ├── ftp_server.py      # FTP服务器
│   │   │   └── syslog_server.py   # Syslog服务器
│   │   └── utils/                 # 通用工具
│   │       ├── logger.py          # 日志系统
│   │       ├── config.py          # 配置管理
│   │       ├── admin_checker.py   # 权限检测
│   │       └── thread_pool.py     # 线程池
│   └── resources/                 # 资源文件
├── assets/                        # 静态资源
│   └── icon.ico                   # 应用图标
├── docs/                          # 文档
│   ├── design-spec.md             # 设计说明书
│   ├── development-plan.md        # 开发规划
│   └── ui-overview.md             # UI拆解
├── tests/                         # 测试
│   ├── test_ping.py               # Ping测试
│   ├── test_port_scan.py          # 端口扫描测试
│   └── test_config.py             # 配置测试
├── requirements.txt               # 依赖列表
├── build.py                       # 构建脚本
└── network_toolkit.spec           # PyInstaller配置
```
