import logging
import os
from datetime import datetime
from typing import Optional
from weakref import WeakKeyDictionary
import sys
from textual.app import App

class TUIHandler(logging.Handler):
    """Custom logging handler that sends logs to the TUI notifications."""
    
    _app: Optional[App] = None

    @classmethod
    def set_app(cls, app: App) -> None:
        """Set the app instance for notifications."""
        cls._app = app

    @classmethod
    def remove_app(cls, app: App) -> None:
        """Remove the app instance."""
        if cls._app is app:
            cls._app = None

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the TUI notifications."""
        if self._app is None:
            return

        # Map logging levels to notification severities
        severity_map = {
            logging.ERROR: "error",
            logging.WARNING: "warning",
            logging.INFO: "information",
            logging.DEBUG: "information"
        }
        
        severity = severity_map.get(record.levelno, "information")
        
        try:
            self._app.notify(record.getMessage(), severity=severity)
        except Exception:
            pass

class DualHandler(logging.Handler):
    """Handler that ensures logs go to both file and TUI when appropriate."""
    
    def __init__(self, file_handler: logging.FileHandler, tui_handler: TUIHandler):
        super().__init__()
        self.file_handler = file_handler
        self.tui_handler = tui_handler
        
    def emit(self, record):
        """Emit a log record to both handlers."""
        try:
            # Always emit to file
            self.file_handler.emit(record)
            
            # Emit to TUI only if it's appropriate level and has apps registered
            if record.levelno >= self.tui_handler.level and self.tui_handler._apps:
                self.tui_handler.emit(record)
                
        except Exception as e:
            self.handleError(record)

def setup_logging(name: str = None) -> logging.Logger:
    """Configure logging for the application
    
    Args:
        name: Optional name for the logger. If None, returns root logger
        
    Returns:
        logging.Logger: Configured logger instance
    """
    try:
        log_directory = "logs"
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_directory, f"temperature_alarm_{current_time}.log")

        # Configure root logger first if not already configured
        root_logger = logging.getLogger()
        
        # Clear any existing handlers
        if root_logger.handlers:
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
                
        root_logger.setLevel(logging.INFO)
        
        # Create and configure file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # File gets everything
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        
        # Create and configure TUI handler
        tui_handler = TUIHandler()
        tui_handler.setLevel(logging.WARNING)  # Set to WARNING to match intended behavior
        tui_formatter = logging.Formatter('%(levelname)s: %(message)s')
        tui_handler.setFormatter(tui_formatter)
        
        # Create and add the dual handler
        dual_handler = DualHandler(file_handler, tui_handler)
        root_logger.addHandler(dual_handler)
        
        # Set third-party loggers to WARNING level
        for module in ['bleak', 'bleak.backends.bluezdbus.client', 
                      'bleak.backends.bluezdbus.manager',
                      'bleak.backends.bluezdbus.scanner', 'gtts.tts']:
            logging.getLogger(module).setLevel(logging.WARNING)

        # Log setup completion
        logger = logging.getLogger(name) if name else root_logger
        logger.info(f"Logging setup completed for {name if name else 'root'}")
        return logger
        
    except Exception as e:
        # If logging setup fails, ensure we at least see the error
        print(f"Failed to setup logging: {e}", file=sys.stderr)
        raise
