from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class PlaceholderPage(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        icon_label = QLabel("🚧")
        icon_label.setFont(QFont("Microsoft YaHei", 64))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        title_label = QLabel(self.name)
        title_label.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("该功能正在开发中，敬请期待...")
        desc_label.setFont(QFont("Microsoft YaHei", 12))
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("color: #7f8c8d; margin-top: 10px;")
        layout.addWidget(desc_label)
