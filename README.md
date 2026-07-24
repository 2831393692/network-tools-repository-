# Network Testing Toolkit SFTP Edition (v2.0)

网络测试工具箱 SFTP 增强版，是一款功能强大的网络测试与管理工具集。

## ✨ 主要功能

### 网络基础工具
- **Ping 测试** - 网络连通性检测
- **Traceroute** - 路由追踪
- **端口扫描** - TCP/UDP 端口探测
- **子网计算器** - IP 子网计算
- **MAC 地址查询** - 网卡信息查看
- **IP 信息查询** - 地理位置信息

### 网络诊断工具
- **主机发现** - 局域网设备扫描
- **网络连接测试** - 多协议连接检测
- **链路监控** - 网络链路状态监控
- **网络健康检查** - 综合网络状态评估

### 网络服务工具
- **DHCP 检测** - DHCP 服务器状态
- **防火墙管理** - Windows 防火墙规则
- **路由表查看** - 系统路由信息
- **网络服务管理** - 网络服务状态

### 远程管理工具
- **远程桌面** - RDP 连接管理
- **远程终端** - SSH/SFTP 连接管理
- **SFTP 文件传输** - 安全文件传输协议
- **串口调试** - 串口数据通信

### 性能测试工具
- **网速测试（内网）** - 局域网速度测试
- **网速测试（外网）** - 互联网速度测试
- **数据包捕获** - 网络流量分析
- **协议分析** - 协议流量统计
- **流量监控** - 实时流量监控

### 摄像头扫描
- **摄像头探测** - 局域网摄像头扫描

## 🚀 技术栈

- **语言**: Python 3.12
- **UI 框架**: PySide6 (Qt6)
- **网络库**: Scapy, psutil, netifaces
- **SFTP 库**: paramiko
- **串口库**: pyserial
- **打包工具**: PyInstaller

## 📦 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python main.py

# 打包
pyinstaller network-toolkit.spec
```

## 📁 项目结构

```
project_03_network-testing-toolkit-sftp/
├── app/
│   ├── core/          # 核心模块
│   ├── ui/            # UI 界面模块
│   ├── widgets/       # 自定义组件
│   ├── data/          # 数据文件
│   └── main_window.py # 主窗口
├── assets/            # 资源文件
├── docs/              # 文档
├── main.py            # 入口文件
└── requirements.txt   # 依赖列表
```

## 📄 许可证

MIT License

## 📞 联系方式

如有问题或建议，欢迎提交 Issue 或 PR。

---

**版本**: v2.0
**更新时间**: 2026-07-24
