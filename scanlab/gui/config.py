"""Persistència de la configuració entre sessions (fitxer JSON)."""

import json
import os
import sys


def _config_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/ScanLab")
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "ScanLab")
    return os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "scanlab",
    )


CONFIG_PATH = os.path.join(_config_dir(), "config.json")
LOG_PATH = os.path.join(_config_dir(), "worker.log")


def load() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass  # no bloquegem el tancament per un error de disc
