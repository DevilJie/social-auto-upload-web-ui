"""
Backend logging utility.

All logs go to data/logs/{yyyy-MM-dd}/{channel}.log
"""
import json
import logging
import os
import sys
from pathlib import Path
from logging import LoggerAdapter

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root (backend/ is a subdir, go up 3 levels from util/)

CHANNELS = ["backend", "bilibili", "douyin", "kuaishou", "xiaohongshu", "iqiyi", "tencent_video", "youtube", "baijiahao", "tiktok"]

LOG_FORMAT = "%(asctime)s [backend][%(channel)s] %(levelname)-8s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
SETTINGS_FILE = BASE_DIR / "settings.json"


class ChannelLoggerAdapter(LoggerAdapter):
    """
    LoggerAdapter that injects the channel name into log records
    via the extra dict, without modifying the message.
    """

    def process(self, msg, kwargs):
        kwargs.setdefault("extra", {})["channel"] = self.extra["channel"]
        return msg, kwargs


def get_settings_log_level() -> str:
    """Read log level from settings.json."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return settings.get("logLevel", "DEBUG")
    except Exception:
        return "DEBUG"


def init_logger():
    """Initialize loggers for all channels."""
    root_logger = logging.getLogger()

    # Avoid duplicate initialization
    if root_logger.handlers:
        return

    log_level_str = get_settings_log_level()
    log_level = getattr(logging, log_level_str.upper(), logging.DEBUG)
    root_logger.setLevel(log_level)

    from datetime import datetime

    # Create logs directory
    today_str = datetime.now().strftime("%Y-%m-%d")
    today = BASE_DIR / "data" / "logs" / today_str
    today.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    for channel in CHANNELS:
        log_file = today / f"{channel}.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)


def get_channel_logger(channel_name: str) -> LoggerAdapter:
    """Return a LoggerAdapter that injects the channel name."""
    logger = logging.getLogger()
    return ChannelLoggerAdapter(logger, {"channel": channel_name})


init_logger()