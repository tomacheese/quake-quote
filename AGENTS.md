# AGENTS.md

## 言語ルール

- コミットの description、PR / Issue のタイトルと本文、コードコメント / docstring、ドキュメントは日本語で書く。
- 日本語と英数字の間には半角スペースを入れる。
- 例外: ログ・エラーメッセージなどの実行時文字列(現状どおり)、引用、技術的な識別子、GitHub Actions ワークフローのフォーク PR 承認コメント本文(`Environment 承認待ち`)とその `body-includes` の照合キー(両者は一致させる)。
- コミットは Conventional Commits、ブランチは Conventional Branch に従う。

## 概要

P2P地震情報(WebSocket)を受信し、Quote/0(Dot. の 2.66 インチ e-ink デバイス)に最新の地震情報を画像として表示する Python アプリ。起動時のみ JMA の `list.json` から初期値を 1 回取得する。

## 開発コマンド

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m flake8 .   # flake8 は requirements-dev.txt の開発依存。設定は .flake8 の exclude のみ(CI には flake8 のステップはない)
docker compose up --build -d   # .env に DOT_APP_API_TOKEN と DOT_DEVICE_ID が必要
```

テストは `pytest.ini` の `pythonpath = src` により `src/` 配下のモジュールを直接 import する。

## アーキテクチャ

- `src/main.py`: エントリーポイント。初期値取得 → WebSocket 受信 → 描画 → push の asyncio ループ。Sentry の初期化もここで行う。
- `src/config.py`: 環境変数の読み込み(`DOT_APP_API_TOKEN` / `DOT_DEVICE_ID` は必須)。
- `src/earthquake_source.py`: JMA 初期値取得と P2P地震情報 WebSocket 受信(指数バックオフで再接続)。両ソースを同一の行データ形式(time/anm/mag/maxi/coord/depth)に正規化する。
- `src/render.py`: Pillow で 296x152 のモノクロ画像を直接描画する。
- `src/quote0_client.py`: Quote/0 API クライアント兼調査用 CLI。
- 詳細な仕様と調査結果は `docs/` を参照する。

## 重要な不変条件

- Quote/0 へは Image API に `ditherType=NONE` で push する。Canvas API はディザリングを無効化できず、小さい文字が潰れるため使わない(`docs/quote0-api.md`)。
- 対象デバイスの Loop タスクに Image API ウィジェットを事前登録しておく必要がある(未登録だと push が 404)。
- 画面更新は `MIN_PUSH_INTERVAL_SEC` 未満の間隔では行わない。現在の表示と同一画像なら push をスキップする。
- push の同期 HTTP 処理は `asyncio.to_thread` 経由で呼び、イベントループをブロックしない。
- WebSocket は正常終了時も含めて必ずバックオフを挟んで再接続する(P2P地震情報は IP あたりの同時接続数が制限されている)。プロセスは終了させない。
- Sentry へ送る情報から API トークンや device_id を除く(`include_local_variables=False`、`_scrub_event`、`_scrub_breadcrumb`)。秘密情報をログに出力しない。
- 描画に使う日本語フォントは Dockerfile で導入する `fonts-ipafont-gothic` に依存する。
