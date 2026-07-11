#!/usr/bin/env python3
"""
Dot. Quote/0 Open API の簡易クライアント兼調査スクリプト。

前提:
- Dot. App の「More → API Key → Create API Key」で発行した API キーを
  .env の DOT_APP_API_TOKEN に設定しておくこと。
- デバイスIDは `list-devices` サブコマンドで確認できる
  (Dot. App の「More → デバイス選択 → Device Serial Number」からも取得可能)。

参考: https://dot.mindreset.tech/docs/service/open/*
      https://github.com/MrWillCom/quote0 (TypeScript SDK, 実装ソースを一次情報として参照)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_ENDPOINT = "https://dot.mindreset.tech/api"
# Quote/0 の画面解像度 (2.66インチ e-ink)
DISPLAY_WIDTH = 296
DISPLAY_HEIGHT = 152


def get_api_key() -> str:
    """環境変数(または.env)からDOT_APP_API_TOKENを取得する。"""
    token = os.environ.get("DOT_APP_API_TOKEN")
    if not token:
        sys.exit("DOT_APP_API_TOKEN が .env にも環境変数にも見つかりません。")
    return token


class Quote0Client:
    """Quote/0 API クライアント。"""

    def __init__(self, api_key: str):
        """API キーを使用してセッションを初期化する。"""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        """パスに API エンドポイントを付加して URL を構築する。"""
        return API_ENDPOINT + path

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """HTTP リクエストを実行して応答を返す。"""
        resp = self.session.request(method, self._url(path), **kwargs)
        return resp

    # --- device ---
    def list_devices(self):
        """登録済みデバイス一覧を取得する。"""
        return self._request("GET", "/authV2/open/devices")

    def device_status(self, device_id: str):
        """デバイスのステータスを取得する。"""
        return self._request("GET", f"/authV2/open/device/{device_id}/status")

    def device_settings_get(self, device_id: str):
        """デバイスの設定を取得する。"""
        return self._request("GET", f"/authV2/open/device/{device_id}/settings")

    def device_settings_update(self, device_id: str, settings: dict):
        """デバイスの設定を更新する。"""
        return self._request(
            "POST", f"/authV2/open/device/{device_id}/settings", data=json.dumps(settings)
        )

    # --- timezone ---
    def list_timezones(self):
        """対応タイムゾーン一覧を取得する。"""
        return self._request("GET", "/authV2/open/timezones")

    # --- content ---
    def next_content(self, device_id: str):
        """次のコンテンツに切り替える。"""
        return self._request("POST", f"/authV2/open/device/{device_id}/next")

    def list_content(self, device_id: str, task_type: str = "loop"):
        """Loop/Fixed コンテンツ一覧を取得する。"""
        # task_type: "fixed" | "loop"
        return self._request("GET", f"/authV2/open/device/{device_id}/{task_type}/list")

    def push_text(self, device_id: str, **options):
        """テキストコンテンツをデバイスに送信する。"""
        return self._request(
            "POST", f"/authV2/open/device/{device_id}/text", data=json.dumps(options)
        )

    def push_image(self, device_id: str, **options):
        """画像コンテンツをデバイスに送信する。"""
        return self._request(
            "POST", f"/authV2/open/device/{device_id}/image", data=json.dumps(options)
        )

    def push_canvas(self, device_id: str, **options):
        """Canvas（自由レイアウト）コンテンツをデバイスに送信する。"""
        return self._request(
            "POST", f"/authV2/open/device/{device_id}/canvas", data=json.dumps(options)
        )


def dump(resp: requests.Response):
    """HTTP レスポンスをフォーマットして出力する。"""
    print(f"HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(resp.text)


def main():
    """Quote/0 API 操作用 CLI のエントリーポイント。"""
    parser = argparse.ArgumentParser(description="Dot. Quote/0 API 調査用CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-devices", help="登録済みデバイス一覧を取得")

    p_status = sub.add_parser("status", help="デバイスステータス取得")
    p_status.add_argument("device_id")

    p_settings = sub.add_parser("settings", help="デバイス設定取得")
    p_settings.add_argument("device_id")

    sub.add_parser("timezones", help="対応タイムゾーン一覧取得")

    p_next = sub.add_parser("next", help="次のコンテンツへ切り替え")
    p_next.add_argument("device_id")

    p_list = sub.add_parser("list-content", help="Loop/Fixed 登録コンテンツ一覧取得")
    p_list.add_argument("device_id")
    p_list.add_argument("--task-type", choices=["fixed", "loop"], default="loop")

    p_text = sub.add_parser("push-text", help="テキストを表示")
    p_text.add_argument("device_id")
    p_text.add_argument("--title", default=None)
    p_text.add_argument("--message", default=None)
    p_text.add_argument("--signature", default=None)
    p_text.add_argument("--no-refresh-now", action="store_true")

    p_image = sub.add_parser("push-image", help="画像を表示 (URLまたはBase64)")
    p_image.add_argument("device_id")
    p_image.add_argument("--image", required=True, help="画像URL or PNG Base64")
    p_image.add_argument("--border", type=int, choices=[0, 1], default=0)
    p_image.add_argument("--no-refresh-now", action="store_true")

    p_canvas = sub.add_parser(
        "push-canvas", help="Canvas(自由レイアウト)を表示"
    )
    p_canvas.add_argument("device_id")
    canvas_window = p_canvas.add_mutually_exclusive_group(required=True)
    canvas_window.add_argument(
        "--window-data", help="要素構造を表す JSON 文字列 (windowData)"
    )
    canvas_window.add_argument(
        "--window-data-file", help="windowData を読み込む JSON ファイルのパス"
    )
    p_canvas.add_argument(
        "--data", default=None, help="画面が参照する値を表す JSON 文字列 (data)"
    )
    p_canvas.add_argument(
        "--task-alias", default=None, help="デバイスタスクリスト上のラベル (taskAlias)"
    )
    p_canvas.add_argument("--link", default=None, help="タップ時のリダイレクト先URL")
    p_canvas.add_argument("--border", type=int, choices=[0, 1], default=None)
    p_canvas.add_argument("--no-refresh-now", action="store_true")

    args = parser.parse_args()
    client = Quote0Client(get_api_key())

    if args.command == "list-devices":
        dump(client.list_devices())
    elif args.command == "status":
        dump(client.device_status(args.device_id))
    elif args.command == "settings":
        dump(client.device_settings_get(args.device_id))
    elif args.command == "timezones":
        dump(client.list_timezones())
    elif args.command == "next":
        dump(client.next_content(args.device_id))
    elif args.command == "list-content":
        dump(client.list_content(args.device_id, args.task_type))
    elif args.command == "push-text":
        options = {"refreshNow": not args.no_refresh_now}
        if args.title:
            options["title"] = args.title
        if args.message:
            options["message"] = args.message
        if args.signature:
            options["signature"] = args.signature
        dump(client.push_text(args.device_id, **options))
    elif args.command == "push-image":
        options = {
            "refreshNow": not args.no_refresh_now,
            "image": args.image,
            "border": args.border,
        }
        dump(client.push_image(args.device_id, **options))
    elif args.command == "push-canvas":
        if args.window_data_file:
            window_data = json.loads(Path(args.window_data_file).read_text())
        else:
            window_data = json.loads(args.window_data)
        # taskKey は Canvas API には存在しないパラメータ(公式ドキュメント確認済み、
        # docs/quote0-api.md「Canvas API の制約」参照)。指定すると 404 になるため渡さない。
        options = {
            "refreshNow": not args.no_refresh_now,
            "windowData": window_data,
        }
        if args.data:
            options["data"] = json.loads(args.data)
        if args.task_alias:
            options["taskAlias"] = args.task_alias
        if args.link:
            options["link"] = args.link
        if args.border is not None:
            options["border"] = args.border
        dump(client.push_canvas(args.device_id, **options))


if __name__ == "__main__":
    main()
