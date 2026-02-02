"""
Logging helper for Talkie modules: consistent logger names (talkie.modules.<name>).
"""

from __future__ import annotations

import logging


def get_logger(module_name: str) -> logging.Logger:
    """
    Return a logger with a consistent name for the given module.
    Use in modules so logs appear under talkie.modules.<module_name>.

    Args:
        module_name: Short name of the module (e.g. "speech", "rag", "browser").

    Returns:
        logging.Logger with name "talkie.modules." + module_name.
    """
    name = (module_name or "").strip() or "module"
    return logging.getLogger(f"talkie.modules.{name}")


__all__ = ["get_logger"]
