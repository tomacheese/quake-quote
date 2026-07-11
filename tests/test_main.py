"""main.py の push 間隔判定ロジックのテスト。"""
import base64
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


def test_render_encode_compare_roundtrip_is_consistent():
    """render_image → image_to_base64_png → images_equal を実物同士で通す統合テスト。

    push_rows の他のテストは render_image / images_equal をすべてモックしているため、
    実際のレンダリング結果が base64 エンコード→デコードを経ても画素単位で
    一致する(= Issue #3 の「同一表示ならpushしない」判定が成立する)ことを
    検証できていない。このテストでは実装をモックせず、実画像同士で一致/不一致の
    両方を確認する。
    """
    rows_a = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]
    rows_b = [{"time": "02/02 12:34", "anm": "テスト2", "mag": "5", "maxi": "3", "coord": None}]

    img_a = main.render_image(rows_a)
    png_b64_a = main.image_to_base64_png(img_a)
    png_bytes_a = base64.b64decode(png_b64_a)

    assert main.images_equal(img_a, png_bytes_a) is True

    img_b = main.render_image(rows_b)
    png_bytes_b = base64.b64decode(main.image_to_base64_png(img_b))

    assert main.images_equal(img_a, png_bytes_b) is False
