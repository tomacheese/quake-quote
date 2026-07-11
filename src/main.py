"""P2P地震情報を受信し、Quote/0 e-inkディスプレイに反映するアプリケーションの
エントリーポイント。

起動時に JMA の地震情報リストから初期値を1回取得し、以後は
P2P地震情報 (https://www.p2pquake.net/) の WebSocket から新着イベントを
受信するたびに画像を再描画して push する。
"""
from __future__ import annotations

import asyncio
import logging
import time

from config import Config, ConfigError, load_config
from earthquake_source import EarthquakeStream, fetch_seed_earthquakes
from quote0_client import Quote0Client
from render import image_to_base64_png, images_equal, render_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def should_push(last_push_at: float | None, now: float, min_interval_sec: int) -> bool:
    """直前pushからmin_interval_sec秒以上経過していればTrueを返す。

    まだ一度もpushしていない(last_push_atがNone)場合は常にTrue。
    """
    if last_push_at is None:
        return True
    return (now - last_push_at) >= min_interval_sec


def push_rows(
    client: Quote0Client,
    config: Config,
    current_rows: list[dict],
    last_push_at: float | None,
) -> float | None:
    """current_rows を画像化し、必要であれば Quote/0 へ push する。

    現在デバイスに表示されている画像と、新しく描画しようとしている画像が
    完全に一致する場合は push 自体をスキップする(表示内容取得に失敗した
    場合は fail-open で通常通り push する)。

    Returns:
        push を実行して成功した場合は更新後の last_push_at、
        スキップした場合や失敗した場合は引数の last_push_at をそのまま返す。
    """
    img = render_image(current_rows)

    current_image_bytes = client.get_current_image(config.device_id)
    if current_image_bytes is not None and images_equal(img, current_image_bytes):
        logger.info("現在の表示内容と同一のため、画面更新をスキップしました。")
        return last_push_at

    image_b64 = image_to_base64_png(img)
    resp = client.push_image(
        config.device_id,
        refreshNow=True,
        image=f"data:image/png;base64,{image_b64}",
        border=0,
        ditherType="NONE",
    )
    if resp.status_code >= 400:
        logger.warning(
            "push-image に失敗しました: HTTP %s %s", resp.status_code, resp.text
        )
        return last_push_at

    logger.info("Quote/0 への画面更新に成功しました。")
    return time.monotonic()


async def run(config: Config) -> None:
    """初期値のロード → WebSocket 受信 → push、の一連の処理を行う。"""
    logger.info("設定を読み込みました。")
    client = Quote0Client(config.api_token)

    try:
        rows = fetch_seed_earthquakes(config.entry_count)
    except Exception as error:  # noqa: BLE001 起動時の初期値取得はどんな例外でも継続させる
        logger.warning("JMA 初期値の取得に失敗しました。空リストで続行します: %s", error)
        rows = []
    else:
        logger.info("JMA 初期値を%d件取得しました。", len(rows))

    last_push_at: float | None = None

    if rows:
        last_push_at = push_rows(client, config, rows, last_push_at)

    logger.info("WebSocket 監視を開始します。")
    stream = EarthquakeStream()
    async for new_row in stream.listen():
        rows = ([new_row] + rows)[: config.entry_count]
        if should_push(last_push_at, time.monotonic(), config.min_push_interval_sec):
            last_push_at = push_rows(client, config, rows, last_push_at)
        else:
            logger.info("push 最小間隔内のため、今回の新着は描画を保留します。")


def main() -> None:
    """設定を読み込み、asyncioイベントループを起動する。"""
    try:
        config = load_config()
    except ConfigError as error:
        logger.error("設定エラー: %s", error)
        raise SystemExit(1) from error

    asyncio.run(run(config))


if __name__ == "__main__":
    main()
