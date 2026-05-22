"""Centralised logging setup.

A single configured logger keeps research, backtest and (future) live runs
consistent. In a live deployment this is where structured/JSON output and alert
sinks would be wired in.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def get_logger(name: str = "quant_tool", level: int = logging.INFO) -> logging.Logger:
    """Return a process-wide logger, configuring the root handler once."""
    global _CONFIGURED
    if not _CONFIGURED:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        _CONFIGURED = True
    return logging.getLogger(name)
