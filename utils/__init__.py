"""
Utilities package.
"""
import logging


def setup_logging(log_level=logging.INFO):
    """Setup logging configuration."""
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/runtime.log'),
            logging.StreamHandler()
        ]
    )


__all__ = ["setup_logging"]
