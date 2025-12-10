# logger.py
import logging
from logging.handlers import RotatingFileHandler
import os

SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

def success(self, message, *args, **kwargs):
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kwargs)

logging.Logger.success = success


class VerticalFilter(logging.Filter):
    def filter(self, record):
        return 'Vertical' not in record.getMessage()


class Logger:
    LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'logs')
    LOG_FILE = os.path.join(LOGS_DIR, "Bjorn.log")

    def __init__(self, name="Logger", level=logging.DEBUG, enable_file_logging=True):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False  # ✅ Évite les logs en double
        self.enable_file_logging = enable_file_logging

        # Évite d'ajouter plusieurs fois les mêmes handlers
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            console_handler.addFilter(VerticalFilter())
            self.logger.addHandler(console_handler)

            if self.enable_file_logging:
                os.makedirs(self.LOGS_DIR, exist_ok=True)
                file_handler = RotatingFileHandler(self.LOG_FILE, maxBytes=5*1024*1024, backupCount=2)
                file_handler.setLevel(level)
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                ))
                file_handler.addFilter(VerticalFilter())
                self.logger.addHandler(file_handler)

    def set_level(self, level):
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    def debug(self, msg): self.logger.debug(msg)
    def info(self, msg): self.logger.info(msg)
    def warning(self, msg): self.logger.warning(msg)
    def error(self, msg): self.logger.error(msg)
    def critical(self, msg): self.logger.critical(msg)
    def success(self, msg): self.logger.success(msg)
    def disable_logging(self): logging.disable(logging.CRITICAL)

# Example usage
if __name__ == "__main__":
    # Change enable_file_logging to False to disable file logging
    log = Logger(name="MyLogger", level=logging.DEBUG, enable_file_logging=False)
    
    log.debug("This is a debug message")
    log.info("This is an info message")
    log.warning("This is a warning message")
    log.error("This is an error message")
    log.critical("This is a critical message")
    log.success("This is a success message")
    
    # Change log level
    log.set_level(logging.WARNING)
    
    log.debug("This debug message should not appear")
    log.info("This info message should not appear")
    log.warning("This warning message should appear")
    
    # Disable logging
    log.disable_logging()
    log.error("This error message should not appear")
