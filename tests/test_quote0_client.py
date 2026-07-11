"""quote0_client.py の環境変数読み込みに関するテスト。"""
import pytest

import quote0_client


def test_get_api_key_reads_env_var(monkeypatch):
    """DOT_APP_API_TOKEN が設定されていればその値を返す。"""
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    assert quote0_client.get_api_key() == "dummy-token"


def test_get_api_key_exits_when_missing(monkeypatch):
    """DOT_APP_API_TOKEN が未設定なら SystemExit する。"""
    monkeypatch.delenv("DOT_APP_API_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        quote0_client.get_api_key()
