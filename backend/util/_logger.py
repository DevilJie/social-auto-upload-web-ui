"""
Backend logging utility.

All logs go to {BASE_DIR}/logs/{yyyy-MM-dd}/{channel}.log
"""
import contextvars
import json
import logging
from contextlib import contextmanager
import sys
from datetime import date
from pathlib import Path
from logging import LoggerAdapter

# Use conf.BASE_DIR which respects SAU_DATA_DIR in packaged mode
from conf import BASE_DIR

CHANNELS = ["backend", "bilibili", "douyin", "kuaishou", "xiaohongshu",
           "iqiyi", "tencent_video", "youtube", "baijiahao", "tiktok",
           "channels", "weibo", "alipay", "toutiao", "zhihu"]

# 发布账号昵称的上下文变量。每条日志会自动带上当前上下文中的昵称，
# 这样在并发发布多个账号时，深层助手日志也能正确归属到对应账号。
# contextvar 会随 asyncio 任务 / run_in_executor 线程自动复制，多账号互不干扰。
account_name_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "account_name", default="-"
)

LOG_FORMAT = "%(asctime)s [%(levelname)s][backend][%(channel)s][%(account_name)s][%(filename)s:%(lineno)d in %(funcName)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ChannelFormatter(logging.Formatter):
    """Formatter that safely handles records without a channel / account_name attribute."""

    def format(self, record):
        if not hasattr(record, "channel"):
            record.channel = "backend"
        # 注入当前上下文的账号昵称（深层 @staticmethod 助手日志也能带上）
        record.account_name = account_name_var.get()
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
    """Read log level from SQLite settings, default DEBUG."""
    try:
        from impl.settings import read_settings
        settings = read_settings()
        return getattr(logging, settings.get("logLevel", "DEBUG").upper(), logging.DEBUG)
    except Exception:
        return logging.DEBUG


def init_logger():
    """Initialize per-channel loggers (not root logger)."""
    log_level = _get_log_level()
    today_dir = BASE_DIR / "logs" / date.today().strftime("%Y-%m-%d")
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


@contextmanager
def bind_account_name(name: str):
    """临时绑定发布账号昵称到当前上下文。

    在 ``with bind_account_name(nick):`` 块内，该账号相关的所有日志（含深层
    助手函数）都会自动带上 ``nick``，块退出后自动还原，确保多账号并发发布互不影响。
    """
    token = account_name_var.set(name or "-")
    try:
        yield
    finally:
        account_name_var.reset(token)


init_logger()