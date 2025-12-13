# app/core/logging_config.py
import logging
import sys
import structlog


def setup_logging() -> None:
    """
    Configure structlog + standaard logging.
    Logs gaan als JSON naar stdout (Cloud Run pakt dit automatisch op).
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# Globale logger die je overal kunt importeren
logger = structlog.get_logger("levelai")
