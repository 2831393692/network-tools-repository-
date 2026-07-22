import json
import os

class ConfigManager:
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), ".network-toolkit")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.config = self._get_default_config()
    
    def _get_default_config(self):
        return {
            "app": {
                "theme": "system",
                "language": "zh_CN",
                "auto_update": False,
                "last_update_check": ""
            },
            "dashboard": {
                "update_interval": 3,
                "show_cpu": True,
                "show_memory": True,
                "show_disk": True,
                "show_network": True,
                "show_process": True
            },
            "ping": {
                "default_count": 4,
                "default_timeout": 2,
                "default_size": 32,
                "history_max": 100
            },
            "port_scan": {
                "default_threads": 50,
                "default_timeout": 2,
                "common_ports": [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 8080]
            },
            "traceroute": {
                "max_hops": 30,
                "timeout": 2,
                "probe_count": 3
            },
            "speed_test": {
                "server_list": ["huawei", "tencent", "aliyun"],
                "iperf3_path": ""
            },
            "camera_scan": {
                "default_threads": 50,
                "default_timeout": 2,
                "brands": ["hikvision", "dahua", "uniview", "tvwall", "generic"]
            },
            "connection_test": {
                "dns_servers": ["114.114.114.114", "223.5.5.5", "8.8.8.8", "1.1.1.1"],
                "default_timeout": 10
            },
            "ui": {
                "sidebar_collapsed": False,
                "window_width": 1280,
                "window_height": 720,
                "splitter_position": 200
            }
        }
    
    def load(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.config = self._merge_config(self.config, loaded)
            else:
                self.save()
        except Exception as e:
            from .logger import Logger
            logger = Logger()
            logger.error(f"加载配置失败: {e}")
    
    def save(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            from .logger import Logger
            logger = Logger()
            logger.error(f"保存配置失败: {e}")
    
    def get(self, key, default=None):
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key, value):
        keys = key.split(".")
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save()
    
    def _merge_config(self, default, loaded):
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result