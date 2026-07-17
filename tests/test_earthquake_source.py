"""earthquake_source.py の純粋関数(ネットワーク非依存部分)のテスト。"""
import asyncio
import json
import logging

import pytest

import earthquake_source
from earthquake_source import (
    EarthquakeStream,
    NormalizationError,
    format_depth,
    format_max_scale,
    next_backoff_seconds,
    normalize_p2pquake_message,
    parse_jma_coordinate,
    parse_jma_depth,
)


def test_parse_jma_coordinate_extracts_lat_lon():
    """JMAのcodフィールドから緯度・経度を取り出せる。"""
    assert parse_jma_coordinate("+37.3+139.1+0/") == (37.3, 139.1)


def test_parse_jma_coordinate_returns_none_for_unknown():
    """空文字列など座標不明の場合は None を返す。"""
    assert parse_jma_coordinate("") is None


def test_parse_jma_depth_extracts_depth_in_km():
    """JMAのcodフィールドから深さをkm単位で取り出せる(メートル→km変換、符号反転)。"""
    assert parse_jma_depth("+37.3+139.1-10000/") == 10


def test_parse_jma_depth_handles_shallow_depth():
    """深さ0(ごく浅い)は不明値ではなく0として取り出せる。"""
    assert parse_jma_depth("+37.3+139.1+0/") == 0


def test_parse_jma_depth_returns_none_when_missing():
    """深さの数値が無い(第3値欠測)場合はNoneを返す。"""
    assert parse_jma_depth("+37.3+139.1/") is None


def test_parse_jma_depth_returns_none_for_empty_string():
    """空文字列の場合はNoneを返す。"""
    assert parse_jma_depth("") is None


def test_format_jma_row_includes_depth():
    """JMAの1件データにdepthキー(km文字列)が追加される。"""
    item = {
        "at": "2026-07-11T12:34:00+09:00",
        "anm": "浦河沖",
        "mag": 5.2,
        "maxi": "5+",
        "cod": "+42.1+142.8-10000/",
    }
    row = earthquake_source._format_jma_row(item)
    assert row["depth"] == "10"


def test_format_jma_row_depth_unknown_when_cod_missing_third_value():
    """codフィールドに深さの数値が無い場合、depthは"-"になる。"""
    item = {
        "at": "2026-07-11T12:34:00+09:00",
        "anm": "浦河沖",
        "mag": 5.2,
        "maxi": "5+",
        "cod": "+42.1+142.8/",
    }
    row = earthquake_source._format_jma_row(item)
    assert row["depth"] == "-"


@pytest.mark.parametrize(
    "max_scale,expected",
    [
        (10, "1"), (40, "4"), (45, "5-"), (50, "5+"),
        (55, "6-"), (60, "6+"), (70, "7"), (-1, "-"), (999, "-"),
    ],
)
def test_format_max_scale(max_scale, expected):
    """maxScaleの数値コードが表示用文字列に変換される。"""
    assert format_max_scale(max_scale) == expected


@pytest.mark.parametrize(
    "depth_km,expected",
    [(10, "10"), (0, "0"), (50, "50"), (None, "-")],
)
def test_format_depth(depth_km, expected):
    """深さ(km)が表示用文字列に変換される。Noneは不明値として"-"になる。"""
    assert format_depth(depth_km) == expected


def test_normalize_p2pquake_message_converts_fields():
    """P2P地震情報メッセージが行データ形式に変換される。"""
    message = {
        "code": 551,
        "earthquake": {
            "time": "2026/07/11 12:34:00",
            "maxScale": 50,
            "hypocenter": {
                "name": "浦河沖",
                "latitude": 42.1,
                "longitude": 142.8,
                "magnitude": 5.2,
                "depth": 10,
            },
        },
    }

    row = normalize_p2pquake_message(message)

    assert row == {
        "time": "07/11 12:34",
        "anm": "浦河沖",
        "mag": "5.2",
        "maxi": "5+",
        "coord": (42.1, 142.8),
        "depth": "10",
    }


def test_normalize_p2pquake_message_depth_unknown_when_minus_one():
    """hypocenter.depthが-1(不明)の場合、depthは"-"になる。"""
    message = {
        "code": 551,
        "earthquake": {
            "time": "2026/07/11 12:34:00",
            "maxScale": 50,
            "hypocenter": {
                "name": "浦河沖",
                "latitude": 42.1,
                "longitude": 142.8,
                "magnitude": 5.2,
                "depth": -1,
            },
        },
    }

    row = normalize_p2pquake_message(message)

    assert row["depth"] == "-"


def test_normalize_p2pquake_message_depth_unknown_when_missing():
    """hypocenter.depthが無い場合も、depthは"-"になる。"""
    message = {
        "code": 551,
        "earthquake": {
            "time": "2026/07/11 12:34:00",
            "maxScale": 50,
            "hypocenter": {
                "name": "浦河沖",
                "latitude": 42.1,
                "longitude": 142.8,
                "magnitude": 5.2,
            },
        },
    }

    row = normalize_p2pquake_message(message)

    assert row["depth"] == "-"


def test_normalize_p2pquake_message_raises_when_name_missing():
    """震源名が欠落している場合は NormalizationError を送出する。"""
    message = {"earthquake": {"time": "2026/07/11 12:34:00", "hypocenter": {}}}
    with pytest.raises(NormalizationError):
        normalize_p2pquake_message(message)


def test_next_backoff_seconds_starts_at_one_and_doubles():
    """バックオフは1秒から始まり、倍々に増える。"""
    backoff = 0.0
    backoff = next_backoff_seconds(backoff)
    assert backoff == 1.0
    backoff = next_backoff_seconds(backoff)
    assert backoff == 2.0
    backoff = next_backoff_seconds(backoff)
    assert backoff == 4.0


def test_next_backoff_seconds_caps_at_limit():
    """上限(cap)を超えて増加しない。"""
    assert next_backoff_seconds(20.0, cap=30.0) == 30.0
    assert next_backoff_seconds(30.0, cap=30.0) == 30.0


class _FakeWebSocket:
    """websockets.connect() が返す接続オブジェクトを模したスタブ。

    async with 文(__aenter__/__aexit__)と、async for による非同期イテレーション
    (__aiter__)の両方に対応する。
    """

    def __init__(self, messages):
        self._messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self._iter_messages()

    async def _iter_messages(self):
        for message in self._messages:
            yield message


def test_listen_logs_on_successful_connect(monkeypatch, caplog):
    """WebSocket接続に成功した際にINFOログを出力する。"""
    message = json.dumps({
        "code": 551,
        "earthquake": {
            "time": "2026/07/11 12:34:00",
            "maxScale": 50,
            "hypocenter": {
                "name": "浦河沖", "latitude": 42.1, "longitude": 142.8, "magnitude": 5.2,
            },
        },
    })
    fake_ws = _FakeWebSocket([message])

    monkeypatch.setattr(earthquake_source.websockets, "connect", lambda url: fake_ws)

    stream = EarthquakeStream()
    caplog.set_level(logging.INFO)

    async def _consume_one():
        gen = stream.listen()
        return await gen.__anext__()

    row = asyncio.run(_consume_one())

    assert row["anm"] == "浦河沖"
    assert any(
        "WebSocket に接続しました" in record.message for record in caplog.records
    )
