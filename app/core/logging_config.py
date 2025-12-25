import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Configure logging for the application.
    Logs are saved to logs/ directory with rotation.
    """
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler (simple format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)

    # File handler for all logs (rotating)
    all_logs_file = log_dir / "app.log"
    all_logs_handler = RotatingFileHandler(
        all_logs_file,
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    all_logs_handler.setLevel(logging.INFO)
    all_logs_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(all_logs_handler)

    # File handler for scraping logs specifically
    scraping_logger = logging.getLogger("scraping")
    scraping_logger.setLevel(logging.DEBUG)

    scraping_logs_file = log_dir / f"scraping_{datetime.now().strftime('%Y%m%d')}.log"
    scraping_handler = RotatingFileHandler(
        scraping_logs_file,
        maxBytes=10_000_000,  # 10MB
        backupCount=10
    )
    scraping_handler.setLevel(logging.DEBUG)
    scraping_handler.setFormatter(detailed_formatter)
    scraping_logger.addHandler(scraping_handler)

    # Error logs file
    error_logs_file = log_dir / "errors.log"
    error_handler = RotatingFileHandler(
        error_logs_file,
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)

    logging.info("Logging configured successfully")
    logging.info(f"Logs directory: {log_dir}")

    return root_logger
