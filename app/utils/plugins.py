"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _plugins_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins"))


def _iter_plugin_modules():
    from importlib import import_module

    plugins_dir = _plugins_dir()
    if not os.path.exists(plugins_dir):
        return

    try:
        plugin_entries = os.listdir(plugins_dir)
    except PermissionError as e:
        logging.warning("Skipping plugin loading: cannot read '%s' (%s)", plugins_dir, e)
        return

    for plugin in plugin_entries:
        if not os.path.isdir(os.path.join(plugins_dir, plugin)):
            continue
        if plugin.startswith(("_", ".")):
            continue
        try:
            yield plugin, import_module(f"plugins.{plugin}")
        except Exception:
            logger.exception("Failed to load plugin '%s'", plugin)


def load_plugins(app: FastAPI):
    """
    Load plugins from the plugins directory for a specific app instance.

    Args:
        app: FastAPI app instance to register plugins to
    """
    for plugin, module in _iter_plugin_modules():
        try:
            register = getattr(module, "register_plugin", None)
            if callable(register):
                register(app, plugin)
        except Exception:
            logger.exception("Failed to register plugin routers for '%s'", plugin)


def register_plugin_jobs() -> None:
    """Register job handlers from plugins (API and Celery worker)."""
    for plugin, module in _iter_plugin_modules():
        try:
            register_jobs = getattr(module, "register_plugin_jobs", None)
            if callable(register_jobs):
                register_jobs()
        except Exception:
            logger.exception("Failed to register plugin jobs for '%s'", plugin)
