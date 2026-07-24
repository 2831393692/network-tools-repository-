import ctypes
import sys

class AdminChecker:
    @staticmethod
    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    @staticmethod
    def run_as_admin():
        try:
            script = sys.argv[0]
            params = ' '.join(sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                f'"{script}" {params}',
                None,
                1
            )
            return True
        except:
            return False
    
    @staticmethod
    def require_admin(func):
        def wrapper(*args, **kwargs):
            if not AdminChecker.is_admin():
                from PySide6.QtWidgets import QMessageBox
                result = QMessageBox.warning(
                    None,
                    "需要管理员权限",
                    "此功能需要管理员权限才能运行。\n是否以管理员身份重新启动软件？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if result == QMessageBox.Yes:
                    AdminChecker.run_as_admin()
                    sys.exit(0)
                else:
                    return None
            return func(*args, **kwargs)
        return wrapper