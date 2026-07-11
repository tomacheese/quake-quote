"""地震情報を Quote/0 表示用の296x152モノクロ画像に描画するモジュール。

Canvas API はサーバー側でHTML風レイアウトをレンダリングした後、e-ink 用に
グレースケール→1bit へディザリング変換される。この変換は fontSize が小さい
と細線が潰れて読めなくなるため、本モジュールでは Pillow でモノクロ("1")
モードの画像を直接描画し(アンチエイリアス無し)、Image API に
`ditherType=NONE` を付けて送信する前提のデータを作る。
"""
from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageDraw, ImageFont

WIDTH = 296
HEIGHT = 152
FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"

# 日本の簡易輪郭(Natural Earth 110m admin0 boundaries より抽出、経度/緯度の点列)。
# 本州+四国+九州が1つのリング、北海道、四国の一部離島がそれぞれ別リングになっている。
JAPAN_OUTLINE = [
    [[141.884601, 39.180865], [140.959489, 38.174001], [140.976388, 37.142074],
     [140.59977, 36.343983], [140.774074, 35.842877], [140.253279, 35.138114],
     [138.975528, 34.6676], [137.217599, 34.606286], [135.792983, 33.464805],
     [135.120983, 33.849071], [135.079435, 34.596545], [133.340316, 34.375938],
     [132.156771, 33.904933], [130.986145, 33.885761], [132.000036, 33.149992],
     [131.33279, 31.450355], [130.686318, 31.029579], [130.20242, 31.418238],
     [130.447676, 32.319475], [129.814692, 32.61031], [129.408463, 33.296056],
     [130.353935, 33.604151], [130.878451, 34.232743], [131.884229, 34.749714],
     [132.617673, 35.433393], [134.608301, 35.731618], [135.677538, 35.527134],
     [136.723831, 37.304984], [137.390612, 36.827391], [138.857602, 37.827485],
     [139.426405, 38.215962], [140.05479, 39.438807], [139.883379, 40.563312],
     [140.305783, 41.195005], [141.368973, 41.37856], [141.914263, 39.991616],
     [141.884601, 39.180865]],
    [[144.613427, 43.960883], [145.320825, 44.384733], [145.543137, 43.262088],
     [144.059662, 42.988358], [143.18385, 41.995215], [141.611491, 42.678791],
     [141.067286, 41.584594], [139.955106, 41.569556], [139.817544, 42.563759],
     [140.312087, 43.333273], [141.380549, 43.388825], [141.671952, 44.772125],
     [141.967645, 45.551483], [143.14287, 44.510358], [143.910162, 44.1741],
     [144.613427, 43.960883]],
    [[132.371176, 33.463642], [132.924373, 34.060299], [133.492968, 33.944621],
     [133.904106, 34.364931], [134.638428, 34.149234], [134.766379, 33.806335],
     [134.203416, 33.201178], [133.79295, 33.521985], [133.280268, 33.28957],
     [133.014858, 32.704567], [132.363115, 32.989382], [132.371176, 33.463642]],
]

# 地図描画エリア(上段右側の正方形に配置)
MAP_W, MAP_H = 100, 100
MAP_X0, MAP_Y0 = WIDTH - 8 - MAP_W, 8

# 上段/下段の区切り(下段は全幅で過去の地震情報を表示する)
TOP_ZONE_Y0, TOP_ZONE_H = 8, MAP_H
BOTTOM_ZONE_Y0 = TOP_ZONE_Y0 + TOP_ZONE_H + 4


class MapProjector:
    """緯度経度を地図描画エリア内のピクセル座標へ変換するクラス。

    日本の輪郭全体を基準に、経度方向へ cos(平均緯度) 補正をかけた上で
    アスペクト比を保ったまま w x h に収まるよう縮尺を決める。
    """

    def __init__(self, outline: list[list[list[float]]], x0: int, y0: int, w: int, h: int, pad: int = 3):
        lons = [pt[0] for ring in outline for pt in ring]
        lats = [pt[1] for ring in outline for pt in ring]
        self.lon_min, self.lon_max = min(lons), max(lons)
        self.lat_min, self.lat_max = min(lats), max(lats)
        self.mean_lat_rad = math.radians((self.lat_min + self.lat_max) / 2)

        xs, ys = zip(*(self._raw_xy(lon, lat) for lon, lat in zip(lons, lats)))
        self.x_min, self.x_max = min(xs), max(xs)
        self.y_min, self.y_max = min(ys), max(ys)

        scale_x = (w - 2 * pad) / (self.x_max - self.x_min)
        scale_y = (h - 2 * pad) / (self.y_max - self.y_min)
        self.scale = min(scale_x, scale_y)
        self.x0, self.y0, self.pad = x0, y0, pad

        # 縦横比を保ったままスケールを決めているため、幅基準/高さ基準の
        # どちらで決まったかにより余りが片側(縦 or 横)にだけ生まれる。
        # 余りの半分をオフセットとして加え、描画エリア内で中央揃えにする。
        used_w = (self.x_max - self.x_min) * self.scale
        used_h = (self.y_max - self.y_min) * self.scale
        self.center_offset_x = ((w - 2 * pad) - used_w) / 2
        self.center_offset_y = ((h - 2 * pad) - used_h) / 2

    def _raw_xy(self, lon: float, lat: float) -> tuple[float, float]:
        """経度は cos(平均緯度) 補正、緯度は北を上にするため反転する。"""
        x = (lon - self.lon_min) * math.cos(self.mean_lat_rad)
        y = self.lat_max - lat
        return x, y

    def project(self, lon: float, lat: float) -> tuple[float, float]:
        """緯度経度を画面上のピクセル座標(px, py)へ変換する。"""
        x, y = self._raw_xy(lon, lat)
        px = self.x0 + self.pad + self.center_offset_x + (x - self.x_min) * self.scale
        py = self.y0 + self.pad + self.center_offset_y + (y - self.y_min) * self.scale
        return px, py


def draw_map(draw: ImageDraw.ImageDraw, rows: list[dict]) -> None:
    """右側エリアに簡易日本地図と最新の震源マーカーを描画する。

    表示が煩雑になるため、マーカーは最新(rows[0])の1件のみ表示する。
    """
    proj = MapProjector(JAPAN_OUTLINE, MAP_X0, MAP_Y0, MAP_W, MAP_H)

    for ring in JAPAN_OUTLINE:
        pts = [proj.project(lon, lat) for lon, lat in ring]
        draw.polygon(pts, fill=0)

    latest = rows[0]

    if latest.get("coord"):
        lat, lon = latest["coord"]
        px, py = proj.project(lon, lat)
        r = 5
        draw.ellipse((px - r, py - r, px + r, py + r), outline=1, fill=1, width=1)
        draw.ellipse((px - r, py - r, px + r, py + r), outline=0, width=2)


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[tuple[str, ImageFont.FreeTypeFont, int]],
    x: int,
    zone_y0: int,
    zone_h: int,
) -> None:
    """指定エリア内で、行の総高さを実測して縦方向中央揃えに文字を描画する。

    `lines` は (テキスト, フォント, 描画後に空ける行間) のリスト。
    固定の余白値を決め打ちすると内容の変更に追従できないため、
    実際のグリフ高さを都度測って中央揃えの開始Y座標を求める。
    """
    line_heights = []
    for text, font, _ in lines:
        bbox = draw.textbbox((0, 0), text, font=font)
        line_heights.append(bbox[3] - bbox[1])
    content_height = sum(line_heights) + sum(gap for _, _, gap in lines[:-1])

    y = zone_y0 + max(0, (zone_h - content_height) // 2)
    for (text, font, gap), h in zip(lines, line_heights):
        draw.text((x, y), text, font=font, fill=0)
        y += h + gap


def render_image(rows: list[dict]) -> Image.Image:
    """地震情報をモノクロ("1")モードの296x152画像に直接描画する。

    Canvas API 経由のディザリングによる文字潰れを避けるため、ここでは
    グレースケールを一切使わず、白 or 黒のみで文字を描く。

    上段: 左に最新1件を「日時→震源地→震度(大)→マグニチュード」の
    順で強調表示し、右に小さめの簡易日本地図と震源マーカーを描く。
    下段: 地図の下に空く余白も活用するため全幅を使い、過去分を
    「震源地名 日時 M# 震度#」の1行で表示する。
    """
    latest, past = rows[0], rows[1:]

    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # 1 = 白
    draw = ImageDraw.Draw(img)

    font_date = ImageFont.truetype(FONT_PATH, 13)
    font_anm = ImageFont.truetype(FONT_PATH, 16)
    font_maxi = ImageFont.truetype(FONT_PATH, 28)
    font_mag = ImageFont.truetype(FONT_PATH, 16)
    font_past = ImageFont.truetype(FONT_PATH, 12)

    # 上段左: 最新情報(地図と同じ上段ゾーン内で縦中央揃え)
    latest_lines: list[tuple[str, ImageFont.FreeTypeFont, int]] = [
        (latest["time"], font_date, 4),
        (latest["anm"], font_anm, 6),
        (f"震度{latest['maxi']}", font_maxi, 6),
        (f"M{latest['mag']}", font_mag, 0),
    ]
    draw_centered_lines(draw, latest_lines, x=8, zone_y0=TOP_ZONE_Y0, zone_h=TOP_ZONE_H)

    # 上段右: 簡易日本地図 + 最新の震源マーカー
    draw_map(draw, rows)

    # 下段: 全幅を使って過去分を1行ずつ表示
    past_lines: list[tuple[str, ImageFont.FreeTypeFont, int]] = [
        (f"{item['anm']} {item['time']} M{item['mag']} 震度{item['maxi']}", font_past, 4)
        for item in past
    ]
    bottom_zone_h = HEIGHT - BOTTOM_ZONE_Y0
    draw_centered_lines(draw, past_lines, x=8, zone_y0=BOTTOM_ZONE_Y0, zone_h=bottom_zone_h)

    return img


def image_to_base64_png(img: Image.Image) -> str:
    """PIL画像をPNGのBase64文字列に変換する(push-image APIへの送信用)。"""
    buf = io.BytesIO()
    img.convert("L").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
