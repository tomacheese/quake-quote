"""main.py の push 間隔判定ロジックのテスト。"""
import logging

import main
from main import Config, should_push


def test_should_push_true_when_no_previous_push():
    """まだ一度もpushしていない場合は常にTrue。"""
    assert should_push(None, now=100.0, min_interval_sec=30) is True


def test_should_push_false_within_interval():
    """最小間隔に満たない場合はFalse。"""
    assert should_push(last_push_at=90.0, now=100.0, min_interval_sec=30) is False


def test_should_push_true_after_interval():
    """最小間隔以上経過していればTrue。"""
    assert should_push(last_push_at=50.0, now=100.0, min_interval_sec=30) is True


def _make_config(**overrides):
    """テスト用の Config を作る(既存デフォルト値を上書き可能)。"""
    base = dict(
        api_token="dummy-token",
        device_id="device-1",
        min_push_interval_sec=30,
        entry_count=3,
    )
    base.update(overrides)
    return Config(**base)


def test_push_skips_when_current_image_matches(monkeypatch, caplog):
    """現在の表示画像と新しく描画する画像が一致する場合、push を呼ばない。"""
    config = _make_config()
    rows = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]

    monkeypatch.setattr(main, "render_image", lambda rows: "FAKE_IMAGE")
    monkeypatch.setattr(main, "images_equal", lambda img, other: True)

    called = {"push_image": False}

    class _FakeClient:
        def get_current_image(self, device_id):
            return b"current-bytes"

        def push_image(self, *args, **kwargs):
            called["push_image"] = True
            raise AssertionError("push_imageは呼ばれないはず")

    caplog.set_level(logging.INFO)
    result_last_push_at = main.push_rows(_FakeClient(), config, rows, last_push_at=None)

    assert called["push_image"] is False
    assert result_last_push_at is None
    assert any("スキップ" in record.message for record in caplog.records)


def test_push_pushes_when_current_image_differs(monkeypatch):
    """現在の表示画像と新しく描画する画像が異なる場合、従来通りpushする。"""
    config = _make_config()
    rows = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]

    monkeypatch.setattr(main, "render_image", lambda rows: "FAKE_IMAGE")
    monkeypatch.setattr(main, "image_to_base64_png", lambda img: "base64data")
    monkeypatch.setattr(main, "images_equal", lambda img, other: False)
    monkeypatch.setattr(main.time, "monotonic", lambda: 123.0)

    called = {}

    class _FakeResp:
        status_code = 200
        text = ""

    class _FakeClient:
        def get_current_image(self, device_id):
            return b"current-bytes"

        def push_image(self, device_id, **options):
            called["push_image"] = (device_id, options)
            return _FakeResp()

    result_last_push_at = main.push_rows(_FakeClient(), config, rows, last_push_at=None)

    assert called["push_image"][0] == "device-1"
    assert result_last_push_at == 123.0


def test_push_pushes_when_current_image_unavailable(monkeypatch):
    """現在の表示画像が取得できない(None)場合はfail-openで従来通りpushする。"""
    config = _make_config()
    rows = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]

    monkeypatch.setattr(main, "render_image", lambda rows: "FAKE_IMAGE")
    monkeypatch.setattr(main, "image_to_base64_png", lambda img: "base64data")
    monkeypatch.setattr(main.time, "monotonic", lambda: 200.0)

    called = {}

    class _FakeResp:
        status_code = 200
        text = ""

    class _FakeClient:
        def get_current_image(self, device_id):
            return None

        def push_image(self, device_id, **options):
            called["push_image"] = (device_id, options)
            return _FakeResp()

    result_last_push_at = main.push_rows(_FakeClient(), config, rows, last_push_at=None)

    assert called["push_image"][0] == "device-1"
    assert result_last_push_at == 200.0
