"""Render a "character speaking in a speech bubble" receipt image (384 px, 1-bit)."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

import characters
from characters import CHAR_H, CHAR_W

WIDTH = 384
SS = 4  # supersampling factor for smooth shapes

FONT_MESSAGE = "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"
FONT_NAME = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_SMALL = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

MARGIN = 6
BORDER = 3
PAD = 12
TAIL_W = 16

# Characters that must not start a line (simple kinsoku).
NO_LINE_START = set("、。，．・：；？！ー～…‥）」』】〕〉》’”ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ!?.,:;)]}")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        line = ""
        for ch in para:
            if line and font.getlength(line + ch) > max_width and ch not in NO_LINE_START:
                lines.append(line)
                line = ch.lstrip(" ")
            else:
                line += ch
        lines.append(line)
    return lines


def load_character(path: str) -> Image.Image:
    """User-supplied character image, fit into CHAR_W x CHAR_H and dithered."""
    src = ImageOps.exif_transpose(Image.open(path))
    if src.mode in ("RGBA", "LA", "P"):
        src = src.convert("RGBA")
        bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
        src = Image.alpha_composite(bg, src)
    src = ImageOps.contain(src.convert("L"), (CHAR_W, CHAR_H), Image.LANCZOS)
    canvas = Image.new("L", (CHAR_W, CHAR_H), 255)
    canvas.paste(src, ((CHAR_W - src.width) // 2, CHAR_H - src.height))
    return canvas.convert("1").convert("L")  # Floyd-Steinberg dither


def _bubble(w: int, h: int, tail_y: int) -> Image.Image:
    """Speech bubble with a tail on the left edge pointing at (0, tail_y)."""
    s = SS
    img = Image.new("L", (w * s, h * s), 255)
    d = ImageDraw.Draw(img)
    x0 = TAIL_W * s
    r = 16 * s
    b = BORDER * s
    ty = tail_y * s
    tail = [(0, ty), (x0 + b * 2, ty - 10 * s), (x0 + b * 2, ty + 6 * s)]
    d.rounded_rectangle((x0, 0, w * s - 1, h * s - 1), radius=r, fill=0)
    d.polygon(tail, fill=0)
    inner_tail = [(int(b * 2.4), ty - b // 3), (x0 + b * 3, ty - 10 * s + b), (x0 + b * 3, ty + 6 * s - b)]
    d.rounded_rectangle((x0 + b, b, w * s - 1 - b, h * s - 1 - b), radius=r - b, fill=255)
    d.polygon(inner_tail, fill=255)
    return img.resize((w, h), Image.LANCZOS)


def render(
    username: str,
    message: str,
    character: Image.Image | None = None,
    mouth_y: int = characters.CAT_MOUTH_Y,
    font_size: int = 24,
    timestamp: datetime | None = None,
) -> Image.Image:
    """character=None picks a random built-in one. mouth_y: where the tail points."""
    if character is None:
        character, mouth_y = characters.get()
    char = character
    f_msg = _font(FONT_MESSAGE, font_size)
    f_name = _font(FONT_NAME, 20)
    f_small = _font(FONT_SMALL, 16)

    bubble_x = MARGIN + CHAR_W
    bubble_w = WIDTH - MARGIN - bubble_x
    text_w = bubble_w - TAIL_W - BORDER * 2 - PAD * 2
    lines = wrap_text(message, f_msg, text_w)
    longest = max(int(f_msg.getlength(line)) for line in lines)
    bubble_w = max(min(bubble_w, longest + TAIL_W + BORDER * 2 + PAD * 2 + 2), 120)
    asc, desc = f_msg.getmetrics()
    line_h = int((asc + desc) * 1.15)
    bubble_h = max(len(lines) * line_h + PAD * 2 + BORDER * 2, 64)

    # name tag (white on black) above the bubble
    name_top = MARGIN + 2
    name_h = 30
    bubble_top = name_top + name_h + 6
    tail_y = min(36, bubble_h // 2)
    char_top = max(MARGIN, bubble_top + tail_y - mouth_y)
    body_bottom = max(bubble_top + bubble_h, char_top + CHAR_H)
    footer_top = body_bottom + 10
    height = footer_top + 30

    img = Image.new("L", (WIDTH, height), 255)
    d = ImageDraw.Draw(img)

    img.paste(char, (MARGIN, char_top))

    name = username.strip() or "ナナシさん"
    name_x = bubble_x + TAIL_W
    max_name_w = WIDTH - MARGIN - name_x - 20
    while f_name.getlength(name) > max_name_w and len(name) > 1:
        name = name[:-2] + "…"
    nw = int(f_name.getlength(name))
    d.rounded_rectangle((name_x, name_top, name_x + nw + 20, name_top + name_h), radius=name_h // 2, fill=0)
    d.text((name_x + 10, name_top + name_h // 2), name, font=f_name, fill=255, anchor="lm")

    img.paste(_bubble(bubble_w, bubble_h, tail_y), (bubble_x, bubble_top))
    tx = bubble_x + TAIL_W + BORDER + PAD
    ty = bubble_top + BORDER + PAD
    for i, line in enumerate(lines):
        d.text((tx, ty + i * line_h), line, font=f_msg, fill=0)

    # footer: dashed rule + timestamp
    for x in range(MARGIN, WIDTH - MARGIN, 10):
        d.line((x, footer_top, x + 5, footer_top), fill=0, width=2)
    ts = (timestamp or datetime.now()).strftime("%Y/%m/%d %H:%M")
    d.text((WIDTH - MARGIN, footer_top + 8), ts, font=f_small, fill=0, anchor="ra")

    return img.point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.Dither.NONE)


def add_feed(img: Image.Image, lines: int) -> Image.Image:
    """Feeding paper = printing blank rows (the protocol has no feed command)."""
    out = Image.new("1", (img.width, img.height + lines), 1)
    out.paste(img, (0, 0))
    return out
