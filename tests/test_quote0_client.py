"""quote0_client.py の環境変数読み込みに関するテスト。"""
import pytest

import quote0_client
from quote0_client import Quote0Client


def test_get_api_key_reads_env_var(monkeypatch):
    """DOT_APP_API_TOKEN が設定されていればその値を返す。"""
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    assert quote0_client.get_api_key() == "dummy-token"


def test_get_api_key_exits_when_missing(monkeypatch):
    """DOT_APP_API_TOKEN が未設定なら SystemExit する。"""
    monkeypatch.delenv("DOT_APP_API_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        quote0_client.get_api_key()


class _FakeResponse:
    """requests の Response を模した簡易スタブ。"""

    def __init__(self, status_code=200, json_data=None, content=b"", raise_json=False):
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.text = "" if not raise_json else "not-json"
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("invalid json")
        return self._json_data


def test_get_current_image_returns_bytes_on_success(monkeypatch):
    """device_status とダウンロードが両方成功した場合、画像バイト列を返す。"""
    client = Quote0Client("dummy-token")

    status_resp = _FakeResponse(
        status_code=200,
        json_data={"renderInfo": {"current": {"image": "https://example.com/current.png"}}},
    )
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp)

    download_resp = _FakeResponse(status_code=200, content=b"png-bytes")
    monkeypatch.setattr(
        quote0_client.requests, "get", lambda url, timeout=10: download_resp
    )

    assert client.get_current_image("device-1") == b"png-bytes"


def test_get_current_image_returns_none_when_status_fails(monkeypatch):
    """device_status がエラーを返した場合は None を返す。"""
    client = Quote0Client("dummy-token")

    status_resp = _FakeResponse(status_code=404)
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp)

    assert client.get_current_image("device-1") is None


def test_get_current_image_returns_none_when_json_malformed(monkeypatch):
    """device_status のレスポンス JSON が不正な場合は None を返す。"""
    client = Quote0Client("dummy-token")

    status_resp = _FakeResponse(status_code=200, raise_json=True)
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp)

    assert client.get_current_image("device-1") is None


def test_get_current_image_returns_none_when_url_missing(monkeypatch):
    """renderInfo.current.image の URL が欠落している場合は None を返す。"""
    client = Quote0Client("dummy-token")

    status_resp = _FakeResponse(status_code=200, json_data={"renderInfo": {"current": {}}})
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp)

    assert client.get_current_image("device-1") is None


def test_get_current_image_returns_none_when_json_not_dict(monkeypatch):
    """device_status の JSON が dict 以外(null やリスト等)の場合は None を返す。"""
    client = Quote0Client("dummy-token")

    status_resp = _FakeResponse(status_code=200, json_data=None)
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp)

    assert client.get_current_image("device-1") is None

    status_resp_list = _FakeResponse(status_code=200, json_data=["unexpected", "list"])
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp_list)

    assert client.get_current_image("device-1") is None


def test_get_current_image_returns_none_when_download_fails(monkeypatch):
    """画像ダウンロードが失敗した場合は None を返す。"""
    client = Quote0Client("dummy-token")

    status_resp = _FakeResponse(
        status_code=200,
        json_data={"renderInfo": {"current": {"image": "https://example.com/current.png"}}},
    )
    monkeypatch.setattr(client, "device_status", lambda device_id: status_resp)

    download_resp = _FakeResponse(status_code=404)
    monkeypatch.setattr(
        quote0_client.requests, "get", lambda url, timeout=10: download_resp
    )

    assert client.get_current_image("device-1") is None
