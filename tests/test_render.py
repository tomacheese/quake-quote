"""render.py のレイアウト計算に関するテスト(実機フォント非依存)。"""
from PIL import Image, ImageDraw, ImageFont

from render import JAPAN_OUTLINE, MapProjector, draw_centered_lines


def test_map_projector_keeps_points_within_area():
    """投影後の座標が指定した描画エリア内に収まる。"""
    proj = MapProjector(JAPAN_OUTLINE, x0=0, y0=0, w=100, h=100, pad=3)

    xs, ys = [], []
    for ring in JAPAN_OUTLINE:
        for lon, lat in ring:
            x, y = proj.project(lon, lat)
            xs.append(x)
            ys.append(y)

    assert min(xs) >= 0
    assert max(xs) <= 100
    assert min(ys) >= 0
    assert max(ys) <= 100


def test_draw_centered_lines_vertically_centers_content():
    """総高さを実測した上で、ゾーンの中央付近から描画が始まる。"""
    img = Image.new("1", (200, 200), color=1)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [("A", font, 4), ("B", font, 0)]

    heights = [
        draw.textbbox((0, 0), text, font=f)[3] - draw.textbbox((0, 0), text, font=f)[1]
        for text, f, _ in lines
    ]
    content_height = sum(heights) + 4
    expected_top = max(0, (200 - content_height) // 2)

    draw_centered_lines(draw, lines, x=0, zone_y0=0, zone_h=200)

    # 背景が白(1、非ゼロ)のため反転しないと getbbox が黒文字ではなく
    # 背景全体を検出してしまう(mode "1" の非ゼロ = 背景側になるため)。
    img = Image.eval(img, lambda x: 1 - x)
    bbox = img.getbbox()
    assert bbox is not None
    _, top, _, _ = bbox
    assert abs(top - expected_top) <= 2
