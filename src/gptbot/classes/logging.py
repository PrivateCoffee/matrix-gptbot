import inspect

from datetime import datetime


class Logger:
    LOG_LEVELS = ["trace", "debug", "info", "warning", "error", "critical"]

    def __init__(self, log_level: str = "warning"):
        if log_level not in self.LOG_LEVELS:
            raise ValueError(
                f"Invalid log level {log_level}. Valid levels are {', '.join(self.LOG_LEVELS)}")

        self.log_level = log_level

    def log(self, message: str, log_level: str = "info"):
        if log_level not in self.LOG_LEVELS:
            raise ValueError(
                f"Invalid log level {log_level}. Valid levels are {', '.join(self.LOG_LEVELS)}")

        if self.LOG_LEVELS.index(log_level) < self.LOG_LEVELS.index(self.log_level):
            return

        caller = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
        print(f"[{timestamp}] - {caller} - [{log_level.upper()}] {message}")
