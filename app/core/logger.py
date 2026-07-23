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
        log_dir = os.path.join(os.path.expanduser("~"), ".network-toolkit", "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        log_filename = datetime.now().strftime("%Y-%m-%d.log")
        log_path = os.path.join(log_dir, log_filename)
        
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        try:
            sys.stdout.fileno()
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        except (AttributeError, ValueError, OSError):
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