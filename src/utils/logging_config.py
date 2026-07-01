"""
Structured logging configuration.

Provides a ``get_logger`` factory that returns a standard Python logger
pre-configured with a consistent format. Every module in the pipeline
obtains its logger through this function rather than calling
``logging.getLogger`` directly, so log format changes require editing
only this file.

``configure_logging`` is called once from ``main.py`` to override the
default level and suppress stdout output when ``--quiet`` is requested.
"""

import logging
import sys

_LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def _configure_root() -> None:
    """One-time root logger setup (INFO to stdout). Idempotent."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _configured = True


def configure_logging(
    level: int = logging.INFO,
    quiet: bool = False,
) -> None:
    """Reconfigure root logger level and suppression.

    Called once from the CLI entry point. Safe to call multiple times
    (each call replaces the previous configuration).

    Args:
        level: Logging level constant (e.g., ``logging.DEBUG``).
        quiet: If True, removes all stdout handlers — logs are suppressed.
    """
    global _configured
    root = logging.getLogger()

    # Remove any existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    _configured = False

    if not quiet:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)

    root.setLevel(level)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, ensuring the root handler is configured.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A standard :class:`logging.Logger` instance.

    Example::

        from src.utils.logging_config import get_logger
        log = get_logger(__name__)
        log.info("Pipeline started")
    """
    _configure_root()
    return logging.getLogger(name)
