import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

_scrape_run_id_ctx: ContextVar[Optional[str]] = ContextVar("scrape_run_id", default=None)


def set_current_scrape_run_id(scrape_run_id: Optional[str]):
    return _scrape_run_id_ctx.set(scrape_run_id)


def reset_current_scrape_run_id(token) -> None:
    _scrape_run_id_ctx.reset(token)


def get_current_scrape_run_id() -> Optional[str]:
    return _scrape_run_id_ctx.get()


class _SpecificRunFilter(logging.Filter):
    def __init__(self, scrape_run_id: str):
        super().__init__()
        self.scrape_run_id = scrape_run_id

    def filter(self, record: logging.LogRecord) -> bool:
        return get_current_scrape_run_id() == self.scrape_run_id


def _get_logs_dir() -> Path:
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir


def _detailed_formatter() -> logging.Formatter:
    return logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def add_scrape_run_file_handler(scrape_run_id: str) -> tuple[RotatingFileHandler, Path]:
    runs_dir = _get_logs_dir() / "runs"
    runs_dir.mkdir(exist_ok=True)
    run_log_path = runs_dir / f"scrape_{scrape_run_id}.log"

    handler = RotatingFileHandler(
        run_log_path,
        maxBytes=5_000_000,  # 5MB per run
        backupCount=2
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_detailed_formatter())
    handler.addFilter(_SpecificRunFilter(scrape_run_id))

    scraping_logger = logging.getLogger("scraping")
    scraping_logger.addHandler(handler)
    return handler, run_log_path


def remove_scrape_run_file_handler(handler: logging.Handler) -> None:
    scraping_logger = logging.getLogger("scraping")
    scraping_logger.removeHandler(handler)
    handler.close()

def setup_logging():
    """
    Configure logging for the application.
    Logs are saved to logs/ directory with rotation.
    """
    # Create logs directory if it doesn't exist
    log_dir = _get_logs_dir()

    # Create formatters
    detailed_formatter = _detailed_formatter()

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

    # Enable DEBUG logging for AI and HTTP libraries
    logging.getLogger('httpx').setLevel(logging.DEBUG)
    logging.getLogger('httpcore').setLevel(logging.DEBUG)
    logging.getLogger('pydantic_ai').setLevel(logging.DEBUG)
    logging.getLogger('openai').setLevel(logging.DEBUG)

    logging.info("Logging configured successfully")
    logging.info(f"Logs directory: {log_dir}")

    return root_logger
