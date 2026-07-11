"""config.py の環境変数読み込みに関するテスト。"""
import pytest

from config import ConfigError, load_config


def test_load_config_raises_when_token_missing(monkeypatch):
    """DOT_APP_API_TOKEN が未設定なら ConfigError を送出する。"""
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")
    monkeypatch.delenv("DOT_APP_API_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_raises_when_device_id_missing(monkeypatch):
    """DOT_DEVICE_ID が未設定なら ConfigError を送出する。"""
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.delenv("DOT_DEVICE_ID", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_uses_defaults(monkeypatch):
    """任意項目を省略した場合は既定値が使われる。"""
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")
    monkeypatch.delenv("MIN_PUSH_INTERVAL_SEC", raising=False)
    monkeypatch.delenv("EARTHQUAKE_ENTRY_COUNT", raising=False)

    config = load_config()

    assert config.api_token == "dummy-token"
    assert config.device_id == "dummy-device-id"
    assert config.min_push_interval_sec == 30
    assert config.entry_count == 3


def test_load_config_reads_overrides(monkeypatch):
    """環境変数を指定した場合はその値が使われる。"""
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "ABCDEF")
    monkeypatch.setenv("MIN_PUSH_INTERVAL_SEC", "60")
    monkeypatch.setenv("EARTHQUAKE_ENTRY_COUNT", "5")

    config = load_config()

    assert config.device_id == "ABCDEF"
    assert config.min_push_interval_sec == 60
    assert config.entry_count == 5
