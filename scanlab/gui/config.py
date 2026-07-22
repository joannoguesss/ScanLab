"""Persistència de la configuració entre sessions (fitxer JSON)."""

import json
import os

CONFIG_PATH = os.path.expanduser(
    "~/Library/Application Support/ScanLab/config.json"
)


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
