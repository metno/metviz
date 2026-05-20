"""Logging helpers shared by the Panel apps."""

from __future__ import annotations

import logging
import sys


def create_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a logger that writes to stdout with a consistent format.

    Using stdout (rather than the default stderr) keeps log lines interleaved
    with the ``print`` output that Panel/Bokeh emit, which matters when the
    container's logs are collected as a single stream.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid attaching duplicate handlers if the module is imported twice.
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
        logger.addHandler(handler)
    return logger
