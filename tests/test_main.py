"""main.py の push 間隔判定ロジックのテスト。"""
import base64
import logging

import pytest

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
    rows_a = [
        {"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None, "depth": "10"},
    ]
    rows_b = [
        {"time": "02/02 12:34", "anm": "テスト2", "mag": "5", "maxi": "3", "coord": None, "depth": "-"},
    ]

    img_a = main.render_image(rows_a)
    png_b64_a = main.image_to_base64_png(img_a)
    png_bytes_a = base64.b64decode(png_b64_a)

    assert main.images_equal(img_a, png_bytes_a) is True

    img_b = main.render_image(rows_b)
    png_bytes_b = base64.b64decode(main.image_to_base64_png(img_b))

    assert main.images_equal(img_a, png_bytes_b) is False


def test_main_does_not_init_sentry_when_dsn_unset(monkeypatch):
    """SENTRY_DSN が未設定の場合、sentry_sdk.init は呼ばれない。"""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")

    called = {"init": False}
    monkeypatch.setattr(main.sentry_sdk, "init", lambda **kwargs: called.__setitem__("init", True))
    monkeypatch.setattr(main.asyncio, "run", lambda coro: None)

    main.main()

    assert called["init"] is False


def test_main_inits_sentry_with_dsn_when_set(monkeypatch):
    """SENTRY_DSN 設定時、その値で sentry_sdk.init が呼ばれる。"""
    monkeypatch.setenv("SENTRY_DSN", "https://example@glitchtip.example/1")
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")

    captured = {}
    monkeypatch.setattr(
        main.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(main.asyncio, "run", lambda coro: None)

    main.main()

    assert captured["dsn"] == "https://example@glitchtip.example/1"


def test_main_inits_sentry_with_local_variables_disabled(monkeypatch):
    """スタックフレームのローカル変数(APIトークン等)を送信しないよう設定される。"""
    monkeypatch.setenv("SENTRY_DSN", "https://example@glitchtip.example/1")
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")

    captured = {}
    monkeypatch.setattr(
        main.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(main.asyncio, "run", lambda coro: None)

    main.main()

    assert captured["include_local_variables"] is False


def test_scrub_breadcrumb_truncates_long_message():
    """breadcrumb の message が長い場合、一定長に切り詰められる。"""
    long_message = "x" * 1000
    crumb = main._scrub_breadcrumb({"message": long_message}, {})

    assert len(crumb["message"]) == 200


def test_scrub_breadcrumb_keeps_short_message_unchanged():
    """breadcrumb の message が短い場合はそのまま保持される。"""
    crumb = main._scrub_breadcrumb({"message": "short"}, {})

    assert crumb["message"] == "short"


def test_main_captures_and_reraises_unhandled_exception(monkeypatch):
    """run() が送出した未捕捉例外は capture_exception した上で再送出される。"""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")

    captured_errors = []
    monkeypatch.setattr(
        main.sentry_sdk, "capture_exception", lambda error: captured_errors.append(error)
    )

    boom = RuntimeError("boom")

    def _raise_boom(coro):
        raise boom

    monkeypatch.setattr(main.asyncio, "run", _raise_boom)

    with pytest.raises(RuntimeError, match="boom"):
        main.main()

    assert captured_errors == [boom]


def test_push_retries_on_request_exception_then_succeeds(monkeypatch):
    """push_image が 2 回失敗し 3 回目で成功した場合、リトライの上で push 成功として扱う。"""
    config = _make_config()
    rows = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]

    monkeypatch.setattr(main, "render_image", lambda rows: "FAKE_IMAGE")
    monkeypatch.setattr(main, "image_to_base64_png", lambda img: "base64data")
    monkeypatch.setattr(main.time, "monotonic", lambda: 123.0)

    sleep_calls = []
    monkeypatch.setattr(main.time, "sleep", lambda sec: sleep_calls.append(sec))

    captured_errors = []
    monkeypatch.setattr(
        main.sentry_sdk, "capture_exception", lambda error: captured_errors.append(error)
    )

    class _FakeResp:
        status_code = 200
        text = ""

    call_count = {"n": 0}

    class _FakeClient:
        def get_current_image(self, device_id):
            return None

        def push_image(self, device_id, **options):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise main.requests.exceptions.ReadTimeout("timed out")
            return _FakeResp()

    result_last_push_at = main.push_rows(_FakeClient(), config, rows, last_push_at=None)

    assert call_count["n"] == 3
    assert result_last_push_at == 123.0
    assert sleep_calls == [1, 2]
    assert captured_errors == []


def test_push_gives_up_after_max_retries_and_reports_to_sentry(monkeypatch):
    """push_image が 3 回とも失敗した場合、Sentry へ送信した上で last_push_at は変更されない。"""
    config = _make_config()
    rows = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]

    monkeypatch.setattr(main, "render_image", lambda rows: "FAKE_IMAGE")
    monkeypatch.setattr(main, "image_to_base64_png", lambda img: "base64data")

    sleep_calls = []
    monkeypatch.setattr(main.time, "sleep", lambda sec: sleep_calls.append(sec))

    captured_errors = []
    monkeypatch.setattr(
        main.sentry_sdk, "capture_exception", lambda error: captured_errors.append(error)
    )

    call_count = {"n": 0}

    class _FakeClient:
        def get_current_image(self, device_id):
            return None

        def push_image(self, device_id, **options):
            call_count["n"] += 1
            raise main.requests.exceptions.ConnectTimeout("connect timed out")

    result_last_push_at = main.push_rows(_FakeClient(), config, rows, last_push_at=99.0)

    assert call_count["n"] == 3
    assert sleep_calls == [1, 2]
    assert len(captured_errors) == 1
    assert isinstance(captured_errors[0], main.requests.exceptions.ConnectTimeout)
    assert result_last_push_at == 99.0


def test_push_reports_http_error_status_to_sentry_too(monkeypatch):
    """push-image が HTTP 4xx/5xx を返した場合も、通信例外と同様に Sentry へ送信される。"""
    config = _make_config()
    rows = [{"time": "01/01 00:00", "anm": "テスト", "mag": "3", "maxi": "1", "coord": None}]

    monkeypatch.setattr(main, "render_image", lambda rows: "FAKE_IMAGE")
    monkeypatch.setattr(main, "image_to_base64_png", lambda img: "base64data")

    captured_messages = []
    monkeypatch.setattr(
        main.sentry_sdk,
        "capture_message",
        lambda message, level=None: captured_messages.append((message, level)),
    )

    class _FakeResp:
        status_code = 404
        text = "not found"

    class _FakeClient:
        def get_current_image(self, device_id):
            return None

        def push_image(self, device_id, **options):
            return _FakeResp()

    result_last_push_at = main.push_rows(_FakeClient(), config, rows, last_push_at=42.0)

    assert len(captured_messages) == 1
    message, level = captured_messages[0]
    assert "404" in message
    assert level == "warning"
    assert result_last_push_at == 42.0


def test_scrub_event_masks_device_id_in_exception_message():
    """例外メッセージ中の URL に含まれる device_id がマスクされる。"""
    event = {
        "exception": {
            "values": [
                {
                    "value": (
                        "Max retries exceeded with url: "
                        "/authV2/open/device/abc123/image"
                    )
                }
            ]
        }
    }

    result = main._scrub_event(event, {})

    scrubbed_value = result["exception"]["values"][0]["value"]
    assert "abc123" not in scrubbed_value
    assert "/device/<redacted>" in scrubbed_value


def test_scrub_event_ignores_events_without_exception():
    """exception フィールドを持たないイベントでもエラーにならない。"""
    event = {"message": "no exception here"}

    result = main._scrub_event(event, {})

    assert result == {"message": "no exception here"}


def test_main_inits_sentry_with_before_send_scrubber(monkeypatch):
    """sentry_sdk.init に device_id スクラブ用の before_send が設定される。"""
    monkeypatch.setenv("SENTRY_DSN", "https://example@glitchtip.example/1")
    monkeypatch.setenv("DOT_APP_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DOT_DEVICE_ID", "dummy-device-id")

    captured = {}
    monkeypatch.setattr(
        main.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(main.asyncio, "run", lambda coro: None)

    main.main()

    assert captured["before_send"] is main._scrub_event
