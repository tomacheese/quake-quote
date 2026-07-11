"""環境変数からアプリケーション設定を読み込むモジュール。"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MIN_PUSH_INTERVAL_SEC = 30
DEFAULT_ENTRY_COUNT = 3


class ConfigError(RuntimeError):
    """設定不備を表す例外。"""


@dataclass
class Config:
    """アプリケーション全体で使う設定値。"""

    api_token: str
    device_id: str
    min_push_interval_sec: int
    entry_count: int


def load_config() -> Config:
    """環境変数から設定を読み込む。

    Raises:
        ConfigError: DOT_APP_API_TOKEN または DOT_DEVICE_ID が設定されていない場合。
    """
    api_token = os.environ.get("DOT_APP_API_TOKEN")
    if not api_token:
        raise ConfigError("DOT_APP_API_TOKEN が設定されていません。")

    device_id = os.environ.get("DOT_DEVICE_ID")
    if not device_id:
        raise ConfigError("DOT_DEVICE_ID が設定されていません。")

    return Config(
        api_token=api_token,
        device_id=device_id,
        min_push_interval_sec=int(
            os.environ.get("MIN_PUSH_INTERVAL_SEC") or DEFAULT_MIN_PUSH_INTERVAL_SEC
        ),
        entry_count=int(
            os.environ.get("EARTHQUAKE_ENTRY_COUNT") or DEFAULT_ENTRY_COUNT
        ),
    )
