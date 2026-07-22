# project_03_network-testing-toolkit

## 项目目标

基于用户提供的 UI 设计稿，实现一款面向网络运维人员的桌面端「网络测试工具箱」。
工具箱覆盖网络状态监控、诊断检测、速度测试、网络分析和实用工具五大模块。

## 当前版本

v0.1.0（仅完成项目创建与 UI 设计稿归档，核心功能待开发）

## 技术栈

待定，待与用户讨论后确定。候选方案：

- 桌面端 GUI：Electron / PySide6 / Tauri
- 网络探测：系统命令调用（ping、tracert）+ 原生 Socket / Scapy
- 数据展示：Chart.js / ECharts / Qt Charts

## 目录结构

```text
project_03_network-testing-toolkit/
├── README.md              # 项目入口说明
├── docs/                  # 项目文档、需求说明、UI 分析
├── src/                   # 主要源码
├── tests/                 # 测试代码
├── data/                  # 项目数据、本地数据库、样例数据
├── assets/                # 图片、图标、媒体素材
│   └── ui-screenshots/    # UI 设计稿截图
├── scripts/               # 辅助脚本、构建脚本
└── outputs/               # 生成结果、导出文件
```

## 安装方式

待定。

## 运行方式

待定。

## 后续计划

1. 与用户确认技术栈和交互细节。
2. 将聊天中的 UI 原图保存到 `assets/ui-screenshots/`。
3. 输出详细的需求规格说明（SPEC）。
4. 分模块实现：仪表盘、诊断检测、速度测试、网络分析、实用工具。
