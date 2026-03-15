from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

DEBUG_COLUMNS = (
    ("person_present", "Человек"),
    ("sharpness", "Резкость"),
    ("exposure", "Свет"),
)


def add_score_badge(
    image: Image.Image,
    score: float | None,
    enabled: bool = True,
    score_breakdown: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    raw_score: float | None = None,
) -> Image.Image:
    if score is None or not enabled:
        return image
    if score_breakdown and weights:
        return add_score_table(image, score, score_breakdown, weights, raw_score=raw_score)

    rgba = image.convert("RGBA")
    overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(15, min(rgba.width, rgba.height) // 16)
    font = load_badge_font(font_size)
    label = f"Score {score:.1f}"

    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    text_width = right - left
    text_height = bottom - top

    padding_x = max(9, font_size // 3)
    padding_y = max(6, font_size // 4)
    badge_x1 = max(8, rgba.width // 36)
    badge_y1 = max(8, rgba.height // 36)
    badge_x2 = badge_x1 + text_width + padding_x * 2
    badge_y2 = badge_y1 + text_height + padding_y * 2
    radius = max(7, font_size // 4)

    draw.rounded_rectangle(
        (badge_x1, badge_y1, badge_x2, badge_y2),
        radius=radius,
        fill=(18, 18, 18, 220),
        outline=(255, 255, 255, 235),
        width=max(2, font_size // 14),
    )
    draw.text(
        (badge_x1 + padding_x, badge_y1 + padding_y - top),
        label,
        font=font,
        fill=(255, 255, 255, 255),
    )

    return Image.alpha_composite(rgba, overlay).convert("RGB")


def add_score_table(
    image: Image.Image,
    score: float,
    score_breakdown: dict[str, float],
    weights: dict[str, float],
    raw_score: float | None = None,
) -> Image.Image:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width <= 0 or height <= 0:
        return image

    overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    margin = max(6, width // 140)
    panel_height = max(1, min(int(height * 0.15), height))
    panel_box = (0, 0, width, panel_height)
    draw.rectangle(panel_box, fill=(10, 16, 24, 218))
    draw.line((0, panel_height - 1, width, panel_height - 1), fill=(255, 255, 255, 90), width=1)

    column_count = len(DEBUG_COLUMNS) + 1
    column_width = max(1, (width - margin * 2) // column_count)
    score_column_width = width - margin - (margin + len(DEBUG_COLUMNS) * column_width)
    header_font, value_font, minor_font, total_font, stack_height = fit_table_fonts(
        draw,
        panel_height,
        column_width,
        max(score_column_width, column_width),
    )
    line_gap = max(2, int(panel_height * 0.03))
    top_y = max(0, (panel_height - stack_height) // 2)
    title_y = top_y
    value_y = title_y + text_height(draw, "Человек", header_font) + line_gap
    points_y = value_y + text_height(draw, "n 0.00", value_font) + line_gap

    for index, (key, label) in enumerate(DEBUG_COLUMNS):
        x1 = margin + index * column_width
        x2 = x1 + column_width
        draw_table_cell(
            draw,
            (x1, top_y, x2, panel_height - margin),
            label,
            f"n {float(score_breakdown.get(key, 0.0)):.2f}",
            f"+{float(score_breakdown.get(key, 0.0)) * float(weights.get(key, 0.0)):.1f}",
            header_font,
            value_font,
            minor_font,
            title_y,
            value_y,
            points_y,
        )
        if index:
            draw.line((x1, margin, x1, panel_height - margin), fill=(255, 255, 255, 60), width=1)

    score_x1 = margin + len(DEBUG_COLUMNS) * column_width
    draw.line((score_x1, margin, score_x1, panel_height - margin), fill=(255, 255, 255, 90), width=1)
    total_hint = f"raw {raw_score:.1f}" if isinstance(raw_score, (int, float)) else "sum"
    draw_table_cell(
        draw,
        (score_x1, top_y, width - margin, panel_height - margin),
        "Итог",
        f"{score:.1f}",
        total_hint,
        header_font,
        total_font,
        minor_font,
        title_y,
        value_y,
        points_y,
        emphasize=True,
    )

    return Image.alpha_composite(rgba, overlay).convert("RGB")


def draw_table_cell(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    middle: str,
    bottom: str,
    header_font,
    value_font,
    minor_font,
    title_y: int,
    middle_y: int,
    bottom_y: int,
    emphasize: bool = False,
) -> None:
    x1, _, x2, _ = box
    center_x = x1 + (x2 - x1) / 2
    title_fill = (255, 255, 255, 235)
    value_fill = (255, 241, 187, 255) if emphasize else (255, 255, 255, 255)
    minor_fill = (202, 219, 238, 255)

    draw_centered_text(draw, center_x, title_y, title, header_font, title_fill)
    draw_centered_text(draw, center_x, middle_y, middle, value_font, value_fill)
    draw_centered_text(draw, center_x, bottom_y, bottom, minor_font, minor_fill)


def draw_centered_text(draw: ImageDraw.ImageDraw, center_x: float, top_y: int, text: str, font, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width = right - left
    draw.text((center_x - text_width / 2, top_y - top), text, font=font, fill=fill)


def fit_table_fonts(
    draw: ImageDraw.ImageDraw,
    panel_height: int,
    normal_column_width: int,
    score_column_width: int,
):
    target_height = max(1, int(panel_height * 0.8))
    low = 0.6
    high = 4.0
    best = None

    for _ in range(18):
        scale = (low + high) / 2.0
        fonts = build_table_fonts(panel_height, scale)
        stack_height = total_stack_height(draw, *fonts[:3], panel_height)
        if fonts_fit(draw, fonts, normal_column_width, score_column_width) and stack_height <= target_height:
            best = (*fonts, stack_height)
            low = scale
        else:
            high = scale

    if best is None:
        fonts = build_table_fonts(panel_height, 1.0)
        return (*fonts, total_stack_height(draw, *fonts[:3], panel_height))
    return best


def build_table_fonts(panel_height: int, scale: float):
    header_size = max(8, int(panel_height * 0.18 * scale))
    value_size = max(8, int(panel_height * 0.24 * scale))
    minor_size = max(8, int(panel_height * 0.15 * scale))
    total_size = max(9, int(panel_height * 0.28 * scale))
    return (
        load_badge_font(header_size),
        load_badge_font(value_size),
        load_badge_font(minor_size),
        load_badge_font(total_size),
    )


def total_stack_height(draw: ImageDraw.ImageDraw, header_font, value_font, minor_font, panel_height: int) -> int:
    line_gap = max(2, int(panel_height * 0.03))
    return (
        text_height(draw, "Человек", header_font)
        + text_height(draw, "n 0.00", value_font)
        + text_height(draw, "+25.0", minor_font)
        + line_gap * 2
    )


def fonts_fit(
    draw: ImageDraw.ImageDraw,
    fonts: tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, ...],
    normal_column_width: int,
    score_column_width: int,
) -> bool:
    header_font, value_font, minor_font, total_font = fonts
    normal_width_limit = max(1, normal_column_width - 6)
    score_width_limit = max(1, score_column_width - 6)

    normal_samples = [
        "Резкость",
        "Человек",
        "n 0.00",
        "+40.0",
    ]
    score_samples = [
        "Итог",
        "100.0",
        "raw 100.0",
    ]

    for sample in normal_samples[:2]:
        if text_width(draw, sample, header_font) > normal_width_limit:
            return False
    if text_width(draw, normal_samples[2], value_font) > normal_width_limit:
        return False
    if text_width(draw, normal_samples[3], minor_font) > normal_width_limit:
        return False

    if text_width(draw, score_samples[0], header_font) > score_width_limit:
        return False
    if text_width(draw, score_samples[1], total_font) > score_width_limit:
        return False
    if text_width(draw, score_samples[2], minor_font) > score_width_limit:
        return False
    return True


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def text_height(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    _, top, _, bottom = draw.textbbox((0, 0), text, font=font)
    return bottom - top


def load_badge_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_name in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            continue
    return ImageFont.load_default()
