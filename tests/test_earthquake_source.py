"""earthquake_source.py の純粋関数(ネットワーク非依存部分)のテスト。"""
import pytest

from earthquake_source import (
    NormalizationError,
    format_max_scale,
    next_backoff_seconds,
    normalize_p2pquake_message,
    parse_jma_coordinate,
)


def test_parse_jma_coordinate_extracts_lat_lon():
    """JMAのcodフィールドから緯度・経度を取り出せる。"""
    assert parse_jma_coordinate("+37.3+139.1+0/") == (37.3, 139.1)


def test_parse_jma_coordinate_returns_none_for_unknown():
    """空文字列など座標不明の場合は None を返す。"""
    assert parse_jma_coordinate("") is None


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
    }


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
