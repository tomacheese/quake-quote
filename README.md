# quake-quote

P2P地震情報を受信し、Quote/0(Dot. の 2.66インチ e-ink デバイス)に最新の地震情報を表示するアプリ。

## 前提

- Dot. App の「More → API Key → Create API Key」で発行した API キーを用意する。
- 対象デバイスの Loop タスクに「Image API」ウィジェットを事前登録しておく必要がある(未登録だと push が 404 になる)。詳細・制約は [`docs/quote0-api.md`](docs/quote0-api.md) を参照。

## 構成

```
quake-quote/
├── .github/workflows/       # docker.yml / hadolint-ci.yml / add-reviewer.yml
├── src/
│   ├── main.py               # エントリーポイント(asyncio)
│   ├── config.py              # 環境変数の読み込み
│   ├── quote0_client.py       # Quote/0 API クライアント + 調査用CLI
│   ├── earthquake_source.py   # JMA初期値取得 + P2P地震情報WS受信
│   └── render.py               # 画像描画ロジック
├── tests/                    # pytest
├── Dockerfile / entrypoint.sh / docker-compose.yml
└── requirements.txt / requirements-dev.txt
```

## Docker での実行

```bash
cp .env.example .env
# .env に DOT_APP_API_TOKEN を設定する

docker compose up --build -d
docker compose logs -f
```

### 環境変数

| 変数 | 内容 | 既定値 |
|---|---|---|
| `DOT_APP_API_TOKEN` | Quote/0 APIキー(必須) | - |
| `DOT_DEVICE_ID` | 対象デバイスID(必須) | - |
| `MIN_PUSH_INTERVAL_SEC` | push最小間隔(秒) | `30` |
| `EARTHQUAKE_ENTRY_COUNT` | 表示件数 | `3` |

## ローカルでのテスト実行

システムの Python 環境を汚さないよう、venv 経由での実行を推奨する
(Debian系はPEP 668によりシステム全体へのpip installが既定で禁止されているため)。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m flake8 . --count --select=E1,E2,E3,E4,E7,E9,W1,W2,W3,W4,W5,F63,F7,F82 --show-source --statistics
```

(`.venv/` は `.flake8` の `exclude` と `.gitignore` の両方で除外済み)

## 関連ドキュメント

- [`docs/quote0-api.md`](docs/quote0-api.md) — Quote/0 API の調査メモ(エンドポイント動作確認結果・制約・パラメータ)
- [`docs/earthquake-source.md`](docs/earthquake-source.md) — 地震情報取得元(JMA/P2P地震情報)の仕様と移行の経緯
