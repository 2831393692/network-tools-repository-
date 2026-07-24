"""关于页面 - 软件信息和许可说明

本页面展示软件版本信息、开源依赖和许可协议。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.core.logger import Logger

logger = Logger("About")


class AboutPage(QWidget):
    """关于页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #1e3a5f;
                border: none;
                border-bottom: 1px solid #0d2137;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 12, 15, 12)

        title = QLabel("❓ 关于和支持")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #f5f6fa; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # 软件信息
        self._add_section(content_layout, "软件信息", [
            "软件名称：网络工具箱 V1.0",
            "",
            "功能简介：",
            "网络测试与诊断工具"
        ])

        # 许可说明
        self._add_section(content_layout, "许可说明", [
            "本软件核心代码为原创开发。",
            "",
            "☑ 使用范围：",
            "• 个人学习和研究使用",
            "• 在遵守相关法律法规的前提下使用",
            "",
            "⚠ 使用限制：",
            "• 不得用于任何非法用途",
            "• 不得去除或修改软件中的版权信息",
            "",
            "📋 免责声明：",
            "• 本软件按'现状'提供，不提供任何明示或暗示的保证",
            "• 使用本软件产生的任何后果由使用者自行承担",
            "• 作者不对使用本软件造成的任何损失负责",
            "• 使用者需自行承担使用本软件的法律责任",
            "",
            "法律提示：",
            "• 严禁反编译、逆向工程、反汇编、破解或绕过本软件授权机制",
            "• 严禁篡改、删除或伪造版权信息、授权信息及完整性校验逻辑",
            "• 若违反上述条款，作者保留依法追究民事及刑事责任的权利"
        ])

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _add_section(self, parent_layout, title, lines):
        """添加一个带标题的内容区块"""
        section = QFrame()
        section.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title_label = QLabel(f"🔹 {title}")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #1e3a5f;")
        layout.addWidget(title_label)

        line_label = QFrame()
        line_label.setStyleSheet("background-color: #e0e0e0;")
        line_label.setFixedHeight(1)
        layout.addWidget(line_label)

        for line in lines:
            if not line:
                spacer = QWidget()
                spacer.setFixedHeight(8)
                layout.addWidget(spacer)
            else:
                label = QLabel(line)
                label.setWordWrap(True)
                label.setStyleSheet("color: #2c3e50; font-size: 13px;")
                layout.addWidget(label)

        parent_layout.addWidget(section)

    def cleanup(self):
        """页面清理"""
        pass
