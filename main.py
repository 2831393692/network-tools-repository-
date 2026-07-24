import sys
import os
import traceback

# PyInstaller 打包后，_MEIPASS 指向临时解压目录
# 注意：不 chdir 到 _MEIPASS，避免相对路径的文件保存到临时目录（程序退出后被删除）
# 如需访问打包在 exe 内的资源文件，使用 os.path.join(sys._MEIPASS, 'resource_path')

from app.main_window import MainWindow
from app.core.permission import AdminChecker
from app.core.logger import Logger
from app.core.config import ConfigManager

def handle_exception(exc_type, exc_value, exc_traceback):
    logger = Logger()
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.error(f"未捕获的异常: {exc_type.__name__}: {exc_value}")
    logger.error("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    
    try:
        from PySide6.QtWidgets import QMessageBox, QApplication
        app = QApplication.instance()
        if app:
            QMessageBox.critical(None, "程序异常", f"程序发生未捕获的异常:\n\n{exc_type.__name__}: {exc_value}\n\n请查看日志获取详细信息。")
    except:
        pass

sys.excepthook = handle_exception

def main():
    logger = Logger()
    logger.info("网络测试工具箱启动...")
    
    config = ConfigManager()
    config.load()
    
    if not AdminChecker.is_admin():
        logger.warning("当前非管理员权限运行，部分功能可能受限")
    
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    
    app = QApplication(sys.argv)
    
    font = QFont()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(10)
    app.setFont(font)
    
    main_window = MainWindow()
    main_window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()