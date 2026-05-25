"""
Settings reader for the platform engine.

Reads settings from the project-level ``settings.json``.
"""

import json

from conf import BASE_DIR

SETTINGS_FILE = BASE_DIR / "settings.json"


def read_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_settings(data: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_proxy_url() -> str | None:
    return read_settings().get("proxyUrl") or None
