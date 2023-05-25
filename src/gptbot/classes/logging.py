import inspect

from datetime import datetime


class Logger:
    def log(self, message: str, log_level: str = "info"):
        caller = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
        print(f"[{timestamp}] - {caller} - [{log_level.upper()}] {message}")
