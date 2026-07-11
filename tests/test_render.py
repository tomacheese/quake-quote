"""render.py のレイアウト計算に関するテスト(実機フォント非依存)。"""
import io

from PIL import Image, ImageDraw, ImageFont

from render import HEIGHT, JAPAN_OUTLINE, WIDTH, MapProjector, draw_centered_lines, images_equal


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


def _solid_image(color: int) -> Image.Image:
    """全面が単色(0=黒 or 255=白相当)の 296x152 グレースケール画像を作る。"""
    return Image.new("L", (WIDTH, HEIGHT), color=color)


def _png_bytes(img: Image.Image) -> bytes:
    """PIL 画像を PNG バイト列に変換する(テスト用ヘルパー)。"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_images_equal_true_for_identical_content():
    """同一内容の画像同士は True を返す。"""
    img_a = _solid_image(0)
    img_b = _solid_image(0)
    assert images_equal(img_a, _png_bytes(img_b)) is True


def test_images_equal_false_for_different_content():
    """内容が異なる画像同士は False を返す。"""
    img_a = _solid_image(0)
    img_b = _solid_image(255)
    assert images_equal(img_a, _png_bytes(img_b)) is False


def test_images_equal_false_for_different_size():
    """サイズが異なる場合は False を返す。"""
    img_a = _solid_image(0)
    img_b = Image.new("L", (10, 10), color=0)
    assert images_equal(img_a, _png_bytes(img_b)) is False


def test_images_equal_false_for_undecodable_bytes():
    """デコード不能なバイト列を渡された場合は False を返す(例外は送出しない)。"""
    img_a = _solid_image(0)
    assert images_equal(img_a, b"not-a-png") is False


def test_images_equal_false_for_truncated_png_body():
    """ヘッダーは有効だが本体が壊れた PNG では False を返す(例外は送出しない)。

    Image.open() はヘッダーのみを解析する遅延評価のため、本体を
    切り詰めたバイト列でも Image.open() 自体は成功する。ピクセル本体を
    実際にデコードする経路(.convert 等)まで例外を捕捉できているかを
    このテストで検証する。
    """
    img_a = _solid_image(0)
    valid_png = _png_bytes(_solid_image(0))
    truncated_png = valid_png[: len(valid_png) // 2]
    assert images_equal(img_a, truncated_png) is False
