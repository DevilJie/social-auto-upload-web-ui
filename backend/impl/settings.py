"""
Settings reader for the platform engine.

Reads the ``engineMode`` key from the project-level ``settings.json``
that is also managed by ``vendor/upstream/sau_backend.py`` via its
``/api/v2/settings`` endpoints.
"""

import json

# conf is backend/conf.py (sys.path entry added by app.py)
from conf import BASE_DIR

SETTINGS_FILE = BASE_DIR / "settings.json"


def get_engine_mode() -> str:
    """Return the engine mode: ``"new"`` or ``"old"`` (default)."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("engineMode", "old")
    except (FileNotFoundError, json.JSONDecodeError):
        return "old"
