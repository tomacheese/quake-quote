"""地震情報の取得元(JMA・P2P地震情報)を扱うモジュール。

起動時の初期値は JMA の地震情報リスト (list.json) を1回だけ取得して埋め、
以後は P2P地震情報 (https://www.p2pquake.net/) の WebSocket から
リアルタイムに新着イベントを受信する。両者は入力スキーマが異なるが、
出力はどちらも同じ行データ形式 (time/anm/mag/maxi/coord/depth) に正規化する。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re

import requests
import websockets

logger = logging.getLogger(__name__)

JMA_LIST_URL = "https://www.jma.go.jp/bosai/quake/data/list.json"
P2PQUAKE_WS_URL = "wss://api.p2pquake.net/v2/ws"
EARTHQUAKE_CODE = 551
BACKOFF_CAP_SEC = 30.0

# P2P地震情報の maxScale (JMA 震度階級の10倍相当) を表示用文字列に変換する表。
# 5弱/5強/6弱/6強はJMAの表記に合わせてハイフン付きにする。
MAX_SCALE_TABLE = {
    10: "1", 20: "2", 30: "3", 40: "4",
    45: "5-", 50: "5+", 55: "6-", 60: "6+", 70: "7",
}


class NormalizationError(ValueError):
    """P2P地震情報メッセージの必須フィールド欠落を表す例外。"""


def parse_jma_coordinate(cod: str) -> tuple[float, float] | None:
    """JMAの `cod` フィールド(例: "+37.3+139.1+0/")から緯度・経度を取り出す。

    符号付き数値が先頭から緯度・経度の順で並んでいる。震源不明などで
    座標が無い場合は None を返す。
    """
    m = re.match(r"^([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", cod or "")
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    return lat, lon


def parse_jma_depth(cod: str) -> int | None:
    """JMAの `cod` フィールド(例: "+37.3+139.1-10000/")から深さを取り出す。

    緯度・経度に続く3番目の符号付き数値がメートル単位の深さで、
    符号は地下方向を表すため反転されている(例: -10000 は深さ10km)。
    第3の数値が存在しない(欠測)場合は None を返す。
    """
    m = re.match(
        r"^([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", cod or ""
    )
    if not m:
        return None
    depth_m = float(m.group(3))
    return round(abs(depth_m) / 1000)


def _format_jma_row(item: dict) -> dict:
    """JMA list.json の1件を行データ形式に整形する。"""
    at = datetime.datetime.fromisoformat(item["at"])
    time_str = f"{at.month:02d}/{at.day:02d} {at.hour:02d}:{at.minute:02d}"
    return {
        "time": time_str,
        "anm": item.get("anm", "不明"),
        "mag": item.get("mag", "-"),
        "maxi": item.get("maxi", "-"),
        "coord": parse_jma_coordinate(item.get("cod", "")),
        "depth": format_depth(parse_jma_depth(item.get("cod", ""))),
    }


def fetch_seed_earthquakes(count: int) -> list[dict]:
    """起動時の初期値として、JMAの地震情報リストから直近count件を取得する。

    リストは新しい順に並んでいるため、先頭からcount件をそのまま使う。
    取得に失敗した場合は例外をそのまま送出する(呼び出し側でログ出力して継続する)。
    """
    resp = requests.get(JMA_LIST_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [_format_jma_row(item) for item in data[:count]]


def format_max_scale(max_scale: int) -> str:
    """P2P地震情報のmaxScale数値コードを表示用文字列に変換する。

    不明な値(欠測など)の場合は "-" を返す。
    """
    return MAX_SCALE_TABLE.get(max_scale, "-")


def format_depth(depth_km: int | None) -> str:
    """震源の深さ(km)を表示用文字列に変換する。

    不明な値(欠測など)の場合は "-" を返す。
    """
    return "-" if depth_km is None else str(depth_km)


def normalize_p2pquake_message(message: dict) -> dict:
    """P2P地震情報 WS の code:551 メッセージを行データ形式に変換する。

    行データ形式は fetch_seed_earthquakes が返す形式と共通
    (time/anm/mag/maxi/coord/depth)。

    Raises:
        NormalizationError: 震源名または発生時刻が欠落している場合。
    """
    earthquake = message.get("earthquake")
    if not earthquake:
        raise NormalizationError("earthquake フィールドがありません。")

    hypocenter = earthquake.get("hypocenter") or {}
    name = hypocenter.get("name")
    time_raw = earthquake.get("time")
    if not name or not time_raw:
        raise NormalizationError("震源名または発生時刻がありません。")

    at = datetime.datetime.strptime(time_raw, "%Y/%m/%d %H:%M:%S")
    time_str = f"{at.month:02d}/{at.day:02d} {at.hour:02d}:{at.minute:02d}"

    lat = hypocenter.get("latitude")
    lon = hypocenter.get("longitude")
    coord = (
        (lat, lon)
        if lat is not None and lon is not None and lat != -200 and lon != -200
        else None
    )

    mag = hypocenter.get("magnitude", -1)
    mag_str = str(mag) if mag is not None and mag != -1 else "-"

    depth = hypocenter.get("depth", -1)
    depth = None if depth is None or depth == -1 else depth

    return {
        "time": time_str,
        "anm": name,
        "mag": mag_str,
        "maxi": format_max_scale(earthquake.get("maxScale", -1)),
        "coord": coord,
        "depth": format_depth(depth),
    }


def next_backoff_seconds(current: float, cap: float = BACKOFF_CAP_SEC) -> float:
    """指数バックオフの次の待機秒数を計算する(初期値1秒、上限capで頭打ち)。"""
    if current <= 0:
        return 1.0
    return min(current * 2, cap)


class EarthquakeStream:
    """P2P地震情報 WebSocket から code:551 メッセージを受信し続けるクラス。

    切断時は指数バックオフで再接続し、プロセスを終了させない。
    """

    def __init__(self, url: str = P2PQUAKE_WS_URL):
        self.url = url

    async def listen(self):
        """新着の地震情報メッセージ(正規化済み行データ)を非同期に生成する。"""
        backoff = 0.0
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    backoff = 0.0
                    logger.info("WebSocket に接続しました。")
                    async for raw in ws:
                        try:
                            message = json.loads(raw)
                        except json.JSONDecodeError:
                            logger.warning("不正なJSONを受信しました: %s", raw)
                            continue
                        if message.get("code") != EARTHQUAKE_CODE:
                            continue
                        try:
                            yield normalize_p2pquake_message(message)
                        except NormalizationError as error:
                            logger.warning("メッセージの変換に失敗しました: %s", error)
            except (websockets.exceptions.WebSocketException, OSError) as error:
                backoff = next_backoff_seconds(backoff)
                logger.warning(
                    "WebSocket接続が切断されました。%s秒後に再接続します: %s",
                    backoff, error,
                )
                await asyncio.sleep(backoff)
            else:
                # サーバー側の正常クローズは例外を伴わず async for が
                # 静かに終了するため、ここでもバックオフを適用しないと
                # 即時再接続のタイトループになり得る(特に P2P地震情報側の
                # 同時接続数制限に抵触した場合)。
                backoff = next_backoff_seconds(backoff)
                logger.warning(
                    "WebSocket接続が正常終了しました。%s秒後に再接続します。",
                    backoff,
                )
                await asyncio.sleep(backoff)
