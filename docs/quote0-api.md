# Quote/0 API 調査メモ

Dot. の Quote/0 (2.66インチ e-ink デバイス) の REST API について、実機で確認した挙動と制約をまとめたもの。実装は `src/quote0_client.py` を参照。

## 前提

- ベースURL: `https://dot.mindreset.tech/api`
- 画面解像度: 296×152 px(2.66インチ e-ink)
- 認証: `Authorization: Bearer <API_KEY>`(APIキーは Dot. App の「More → API Key → Create API Key」で発行)

一次情報源:

- 公式ドキュメント <https://dot.mindreset.tech/docs/service/open/*>
- 実装ソース(信頼度が高い一次情報として参照): TypeScript SDK
  <https://github.com/MrWillCom/quote0>

## 実機で確認できたこと

手元の検証機(edition 2)で以下を確認した。

| コマンド | エンドポイント | 結果 |
|---|---|---|
| `list-devices` | `GET /authV2/open/devices` | ✅ 200、登録デバイス1台を取得 |
| `status` | `GET /authV2/open/device/:id/status` | ✅ 200、バッテリー・Wi-Fi電波強度・現在の表示画像URL・次回更新予定時刻を取得 |
| `settings`(GET) | `GET /authV2/open/device/:id/settings` | ✅ 200、タイムゾーン(Asia/Tokyo)・電源時/バッテリー時の更新間隔・スリープ設定を取得 |
| `settings`(POST) | `POST /authV2/open/device/:id/settings` | ✅ 200、現在値をそのまま再送して同期成功を確認。`interval.powerMs`に不正値(60000の倍数以外)を送ると **400** + 具体的なバリデーションメッセージ、実機設定は変更されないことを確認 |
| `list-content --task-type fixed` | `GET /authV2/open/device/:id/fixed/list` | ✅ 200、天気ウィジェット(甲府, GENERAL type)を1件取得 |
| `list-content --task-type loop` | `GET /authV2/open/device/:id/loop/list` | ✅ 200、空配列(Loopタスク未設定) |
| `timezones` | `GET /authV2/open/timezones` | ✅ 200、対応タイムゾーン一覧を取得 |
| `next` | `POST /authV2/open/device/:id/next` | ✅ 200、コンテンツ切り替えに成功(表示中コンテンツが1件のみのため見た目の変化はなし) |
| `push-text` | `POST /authV2/open/device/:id/text` | ❌ **404** — 下記「重要な制約」参照 |
| `push-image` | `POST /authV2/open/device/:id/image` | ❌ **404**(有効なURLでも同様)。無効なURL/非画像レスポンスの場合は **400** |
| `push-canvas` | `POST /authV2/open/device/:id/canvas` | ❌ **404** — 同上 |

**AI Skill**(自然言語連携)は独自エンドポイントを持たず、上記 Text/Image/Canvas/Status/Next API を自然言語インターフェース越しに呼び出すラッパー・統合レイヤー(Codexプラグイン、OpenAI GPT Actions用OpenAPIスキーマ等)であることをドキュメントで確認した。単体の追加APIではないため実機テスト対象外。

レート制限: text/image/canvas/list系はいずれも 10 req/sec。

## 重要な制約: Text/Image/Canvas API はアプリ側の事前登録が必須

`push-text` / `push-image` / `push-canvas` はいずれも、**Dot. App の「コンテンツ工房(Content Studio)」で、対象デバイスの Loop タスクに「Text API」「Image API」「Canvas API」という“枠(プレースホルダー)”をあらかじめ追加しておかないと 404 を返す**。

> API キーは検証されましたが、デバイス XXXX のループタスクにテキスト API コンテンツが見つかりません。Dot. App のコンテンツ工房でテキスト API コンテンツをデバイスのループタスクに追加してください。

つまり運用フローは:

1. **(アプリ側・1回だけ)** Dot. App でデバイスの Loop コンテンツに「Text API」「Image API」等のウィジェットを追加する。
2. **(API側)** 以後は同じ枠に対して `POST .../text` などで内容を繰り返し書き換えられる(`taskKey` で複数枠を使い分け可能)。

## Fixed / Loop の優先関係(実機で確定)

- **Fixed タスクに何かが割り当てられている間、Loop 側のコンテンツ(Text/Image/Canvas API いずれも)は画面に一切反映されない。** `push-*` API 自体は Loop 側のキーに対して常に `200` で成功する(中身は書き換わる)が、画面(`status.renderInfo.current` / 実機表示)には出ない。
- 対処: Dot. App で Fixed タスクの割り当てを削除 → `list-content --task-type fixed` が `[]` になったことを確認 → `next` を1回呼ぶ → Loop の内容が反映される。
- **Canvas API は `taskKey` の有無に関わらず、常に Loop 側の枠を更新する。Fixed 側の中身を書き換える手段は無い。**
- Text API / Image API で `taskKey` に Fixed 側の key を渡した場合の挙動は未検証(下記「未検証項目」参照)。

## Canvas API の制約

- `taskKey` パラメータは存在しない(Text API / Image API のみが持つ)。公式ドキュメント [Control Text Content](https://dot.mindreset.tech/docs/service/open/text_api) / [Control Image Content](https://dot.mindreset.tech/docs/service/open/image_api) で確認済み。代わりに区別用ラベルの `taskAlias` のみを持つ。
- `ditherType` パラメータが存在せず(Image API のみが持つ)、ディザリングを無効化する手段が無い(`src/render.py` がモノクロ直描画+`push-image`の`ditherType=NONE`で回避している理由はこれ)。
- `windowData` 内の要素 `type` は **`div` / `span` / `img` のみ対応**。`text` を指定すると `400`(「canvas 要素 text はサポートされていません」)。

## 各 push API のパラメータ

### push-text

`refreshNow`(即時反映, デフォルトtrue) / `title` / `message`(`\n`,`\t`可) /
`signature` / `icon`(PNG Base64 or URL, 40×40px推奨・最大1MB) /
`link`(NFCタップ時のリダイレクト先) / `taskKey` / `taskAlias` /
`styles.{title,message,signature}.{fontFamily,fontSize,fontWeight}`

### push-image

`refreshNow` / `image`(PNG Base64 or 画像直リンクURL、最大3MB。**画像は
認証不要・匿名アクセス可能な `image/*` を直接返す URL でないと 400**) /
`link` / `border`(0=白枠, 1=黒枠) / `ditherType`(`DIFFUSION`/`ORDERED`/`NONE`,
デフォルト`DIFFUSION`) / `ditherKernel`(`FLOYD_STEINBERG` 等) / `taskKey` / `taskAlias`

### push-canvas

`refreshNow` / `taskAlias` / `data`(画面が参照する値) /
`windowData`(要素構造の記述) / `layoutFull` / `link` / `border`

## 検証時の注意

**HTTP 200 は「内容が画面に反映された」ことを保証しない。** 実際に別内容(デモカードや前回の内容)が表示されたままというケースが複数回あった。`status.renderInfo` のURLのkey名だけで「更新先」を判断せず、実際に画像をダウンロードして中身を目視確認するまではAPIの成否を信用しないこと。

正しい検証手順:

1. `push-*` を呼ぶ
2. `next` で表示コンテンツを切り替える
3. 数秒待ってから `status` を呼び、`renderInfo.current.image` の URL を取得する(レンダー直後は CDN アップロードが非同期のため、`NoSuchKey` の404 XML が返ることがある。数秒待って `status` を取り直す)
4. その URL 画像を実際にダウンロードして中身を目視確認する

## 未検証項目(次にやるなら)

- `settings` の POST(タイムゾーン変更・更新間隔変更・スリープ設定変更)は現状値の再送とバリデーションエラーのみ確認し、実際の値変更は行っていない。
- `taskKey` を使った複数枠の同時運用(今回は1枠のみ書き換え)。
- `image`/`canvas` の `border`・`ditherType` 等の見た目パラメータの比較。
- Loop 内の複数コンテンツ間で `next` がどう巡回するか(今回は1枠のみ有効化)。
- Text API / Image API で `taskKey` に Fixed 側の key を渡した場合の挙動(Canvas API は Fixed を一切更新できないことが確定したが、Text/Image も同様か、それとも別の結果になるのかは未確認)。
- Loop に複数の Canvas API 枠がある状態で、`taskKey`/`taskAlias` を省略した `push-canvas` がどの枠を優先して更新するかの詳細なルール(今回は常に1枠のみの状態でしか確認していない)。
