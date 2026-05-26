"""
Backend logging utility.

All logs go to data/logs/{yyyy-MM-dd}/{channel}.log
"""
import json
import logging
import sys
from datetime import date
from pathlib import Path
from logging import LoggerAdapter

# Use conf.BASE_DIR which respects SAU_DATA_DIR in packaged mode
from conf import BASE_DIR

CHANNELS = ["backend", "bilibili", "douyin", "kuaishou", "xiaohongshu",
           "iqiyi", "tencent_video", "youtube", "baijiahao", "tiktok"]

LOG_FORMAT = "%(asctime)s [%(levelname)s][backend][%(channel)s][%(filename)s:%(lineno)d in %(funcName)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ChannelFormatter(logging.Formatter):
    """Formatter that safely handles records without a channel attribute."""

    def format(self, record):
        if not hasattr(record, "channel"):
            record.channel = "backend"
        return super().format(record)


class ChannelLoggerAdapter(LoggerAdapter):
    """
    LoggerAdapter that injects the channel name into log records
    via the extra dict, without modifying the message.
    """

    def process(self, msg, kwargs):
        kwargs.setdefault("extra", {})["channel"] = self.extra["channel"]
        return msg, kwargs


def _get_log_level() -> int:
    """Read log level from settings.json, default DEBUG."""
    try:
        with open(BASE_DIR / "settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
        return getattr(logging, settings.get("logLevel", "DEBUG").upper(), logging.DEBUG)
    except Exception:
        return logging.DEBUG


def init_logger():
    """Initialize per-channel loggers (not root logger)."""
    log_level = _get_log_level()
    today_dir = BASE_DIR / "data" / "logs" / date.today().strftime("%Y-%m-%d")
    today_dir.mkdir(parents=True, exist_ok=True)

    formatter = ChannelFormatter(LOG_FORMAT, DATE_FORMAT)

    # 第三方库 (waitress, etc.) 用 root logger + stream handler
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    # 每个渠道独立的 logger
    for channel in CHANNELS:
        channel_logger = logging.getLogger(channel)
        channel_logger.setLevel(log_level)
        channel_logger.handlers.clear()

        handler = logging.FileHandler(today_dir / f"{channel}.log", encoding="utf-8")
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        channel_logger.addHandler(handler)


def get_channel_logger(channel_name: str) -> LoggerAdapter:
    """Return a LoggerAdapter wrapping the channel-specific logger."""
    channel_logger = logging.getLogger(channel_name)
    return ChannelLoggerAdapter(channel_logger, {"channel": channel_name})


init_logger()