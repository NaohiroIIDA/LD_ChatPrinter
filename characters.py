"""Built-in characters, drawn procedurally (white bg, black ink, CHAR_W x CHAR_H).

Cats share one builder: each shape (tail, body, ears, head, paws) is stamped
back-to-front as a black silhouette, then filled with that cat's fur through an
eroded copy of its mask, which leaves an outline. Fur patterns (patches, stripes,
hatching) are painted onto a full-canvas fur layer beforehand. Face lines are
drawn in ink that follows the local tone, so they show on any fur.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter

CHAR_W, CHAR_H = 120, 160
SS = 4  # supersampling factor
OUTLINE = 14  # outline thickness in supersampled pixels (~3.5 px)

TAIL = (84, 152, 102, 150, 112, 136, 112, 118, 104, 104)
EYE_X = (38, 82)
EYE_Y = 60


def P(*xy):
    return [v * SS for v in xy]


def mirror(*xy):
    return [CHAR_W - v if i % 2 == 0 else v for i, v in enumerate(xy)]


# --- fur textures ------------------------------------------------------------

@lru_cache(maxsize=None)
def hatch() -> Image.Image:
    """Diagonal lines: reads as a mid tone (brown / tabby) on thermal paper."""
    img = Image.new("L", (CHAR_W * SS, CHAR_H * SS), 255)
    d = ImageDraw.Draw(img)
    step = 5 * SS
    for x in range(-CHAR_H * SS, CHAR_W * SS, step):
        d.line((x, 0, x + CHAR_H * SS, CHAR_H * SS), fill=0, width=int(1.6 * SS))
    return img


@lru_cache(maxsize=None)
def dots() -> Image.Image:
    """Dot grid: a lighter grey tone."""
    img = Image.new("L", (CHAR_W * SS, CHAR_H * SS), 255)
    d = ImageDraw.Draw(img)
    step = 4 * SS
    for y in range(0, CHAR_H * SS, step):
        off = step // 2 if (y // step) % 2 else 0
        for x in range(off, CHAR_W * SS, step):
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=0)
    return img


def patch(fur: Image.Image, src, draw_fn: Callable[[ImageDraw.ImageDraw], None]):
    """Paint `src` (0, 255 or a texture) onto the fur layer where draw_fn draws."""
    mask = Image.new("L", fur.size, 0)
    draw_fn(ImageDraw.Draw(mask))
    fur.paste(src, mask=mask)


def scallop(d: ImageDraw.ImageDraw, box, n: int, r: float, fill=255):
    """Ellipse with a fluffy, bumpy edge (long-haired fur)."""
    x0, y0, x1, y1 = box
    cx, cy, a, b = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    d.ellipse(P(x0, y0, x1, y1), fill=fill)
    for i in range(n):
        t = 2 * math.pi * i / n
        px, py = cx + a * math.cos(t), cy + b * math.sin(t)
        d.ellipse(P(px - r, py - r, px + r, py + r), fill=fill)


def tail_line(d: ImageDraw.ImageDraw, width: float, fill=255):
    d.line(P(*TAIL), fill=fill, width=int(width * SS), joint="curve")
    for x, y in ((TAIL[0], TAIL[1]), (TAIL[-2], TAIL[-1])):
        r = width / 2
        d.ellipse(P(x - r, y - r, x + r, y + r), fill=fill)


# --- the cat builder ---------------------------------------------------------

EARS = {
    "normal": (10, 50, 20, 8, 52, 30),
    "small": (16, 44, 24, 16, 48, 30),
    "tuft": (10, 50, 18, 6, 50, 30),
}
FOLD_EAR = (18, 38, 26, 22, 46, 28, 40, 40)
PAWS = ((29, 144, 51, 158), (69, 144, 91, 158))


@dataclass
class Cat:
    fur: str = "white"  # white | black | hatch | dots
    ears: str = "normal"  # normal | small | tuft | fold
    eyes: str = "round"  # round | big | slit | happy
    fluffy: bool = False  # long-haired outline + ruff
    stripes: bool = False  # three little forehead stripes
    collar: bool = False  # collar with a bell
    paint: Callable[[Image.Image], None] | None = None  # extra fur patterns

    def fur_layer(self) -> Image.Image:
        base = {"white": None, "black": None, "hatch": hatch(), "dots": dots()}[self.fur]
        if base is None:
            fur = Image.new("L", (CHAR_W * SS, CHAR_H * SS), 0 if self.fur == "black" else 255)
        else:
            fur = base.copy()
        if self.paint:
            self.paint(fur)
        return fur

    def shapes(self):
        f = self.fluffy
        out = [lambda d: tail_line(d, 16 if f else 11)]
        if f:
            out.append(lambda d: scallop(d, (26, 90, 94, 156), 12, 8))
        else:
            out.append(lambda d: d.ellipse(P(24, 86, 96, 160), fill=255))
        if self.ears != "fold":
            ear = EARS[self.ears]
            out.append(lambda d: d.polygon(P(*ear), fill=255))
            out.append(lambda d: d.polygon(P(*mirror(*ear)), fill=255))
        if f:
            out.append(lambda d: scallop(d, (12, 28, 108, 98), 14, 9))
        else:
            out.append(lambda d: d.ellipse(P(6, 22, 114, 104), fill=255))
        if self.ears == "fold":
            out.append(lambda d: d.polygon(P(*FOLD_EAR), fill=255))
            out.append(lambda d: d.polygon(P(*mirror(*FOLD_EAR)), fill=255))
        for box in PAWS:
            out.append(lambda d, box=box: d.ellipse(P(*box), fill=255))
        return out

    def features(self, d: ImageDraw.ImageDraw):
        """Lines whose ink colour is chosen from the fur underneath."""
        w2, w3 = 2 * SS, 3 * SS
        if self.ears in ("normal", "tuft", "small"):
            x0, y0, x1, y1, x2, y2 = EARS[self.ears]
            inner = (x0 + 9, y0 - 7, x1 + 4, y1 + 10, x2 - 8, y2 + 1)
            for pts in (inner, mirror(*inner)):
                d.line(P(*pts), fill=255, width=w2)
        if self.ears == "tuft":
            for pts in ((18, 6, 15, 0), (18, 6, 21, 0)):
                d.line(P(*pts), fill=255, width=w2)
                d.line(P(*mirror(*pts)), fill=255, width=w2)
        if self.ears == "fold":
            for pts in ((24, 32, 40, 32),):
                d.line(P(*pts), fill=255, width=w2)
                d.line(P(*mirror(*pts)), fill=255, width=w2)
        if self.stripes:
            for x in (52, 60, 68):
                d.line(P(x, 28, x, 38), fill=255, width=w3)
        if self.eyes == "happy":
            for cx in EYE_X:
                d.arc(P(cx - 9, 54, cx + 9, 72), 200, 340, fill=255, width=w3)

        # nose + mouth ("ω"), open because the cat is talking
        d.polygon(P(55, 70, 65, 70, 60, 76), fill=255)
        d.line(P(60, 76, 60, 80), fill=255, width=w2)
        d.arc(P(50, 74, 60, 84), 0, 180, fill=255, width=w2)
        d.arc(P(60, 74, 70, 84), 0, 180, fill=255, width=w2)
        d.chord(P(54, 82, 66, 94), 0, 180, fill=255)

        for y0, y1 in ((70, 66), (76, 76), (82, 86)):
            d.line(P(0, y1, 22, y0), fill=255, width=w2)
            d.line(P(120, y1, 98, y0), fill=255, width=w2)

        d.line(P(50, 120, 50, 146), fill=255, width=w3)
        d.line(P(70, 120, 70, 146), fill=255, width=w3)
        for cx in (40, 80):
            d.line(P(cx - 3, 148, cx - 3, 154), fill=255, width=w2)
            d.line(P(cx + 3, 148, cx + 3, 154), fill=255, width=w2)

    def eyes_and_collar(self, d: ImageDraw.ImageDraw):
        """Drawn in absolute colours, with a white ring so they read on any fur."""
        for cx in EYE_X:
            if self.eyes in ("round", "big"):
                k = 1.2 if self.eyes == "big" else 1.0
                rx, ry = 9 * k, 10 * k
                d.ellipse(P(cx - rx - 3, EYE_Y - ry - 3, cx + rx + 3, EYE_Y + ry + 3), fill=255)
                d.ellipse(P(cx - rx, EYE_Y - ry, cx + rx, EYE_Y + ry), fill=0)
                d.ellipse(P(cx - rx * 0.55, EYE_Y - ry * 0.7, cx, EYE_Y - ry * 0.1), fill=255)
                d.ellipse(P(cx + 2 * k, EYE_Y + 2 * k, cx + 5 * k, EYE_Y + 5 * k), fill=255)
            elif self.eyes == "slit":
                d.ellipse(P(cx - 12, 50, cx + 12, 70), fill=255, outline=0, width=2 * SS)
                d.ellipse(P(cx - 3, 52, cx + 3, 68), fill=0)
                d.ellipse(P(cx - 8, 54, cx - 4, 58), fill=0)
        if self.collar:
            d.line(P(36, 102, 84, 102), fill=255, width=5 * SS)
            d.ellipse(P(53, 102, 67, 116), fill=255, outline=0, width=2 * SS)
            d.line(P(60, 109, 60, 115), fill=0, width=2 * SS)
            d.line(P(54, 108, 66, 108), fill=0, width=SS)

    def draw(self) -> Image.Image:
        size = (CHAR_W * SS, CHAR_H * SS)
        img = Image.new("L", size, 255)
        fur = self.fur_layer()
        for shape in self.shapes():
            mask = Image.new("L", size, 0)
            shape(ImageDraw.Draw(mask))
            img.paste(0, mask=mask)
            for _ in range(OUTLINE):
                mask = mask.filter(ImageFilter.MinFilter(3))
            img.paste(fur, mask=mask)

        # Ink follows the local tone: white over dark fur, black elsewhere.
        feat = Image.new("L", size, 0)
        self.features(ImageDraw.Draw(feat))
        tone = img.filter(ImageFilter.BoxBlur(3 * SS))
        ink = tone.point(lambda v: 255 if v < 90 else 0)
        img.paste(ink, mask=feat)

        self.eyes_and_collar(ImageDraw.Draw(img))
        return img.resize((CHAR_W, CHAR_H), Image.LANCZOS)


# --- per-cat fur patterns ----------------------------------------------------

def paint_mike(fur):
    patch(fur, 0, lambda d: d.ellipse(P(-12, -8, 50, 48), fill=255))
    patch(fur, 0, lambda d: d.ellipse(P(22, 118, 46, 146), fill=255))
    patch(fur, hatch(), lambda d: (
        d.ellipse(P(72, -2, 130, 46), fill=255),
        d.ellipse(P(66, 94, 104, 136), fill=255),
        tail_line(d, 20),
    ))


def paint_kijitora(fur):
    patch(fur, 255, lambda d: (
        d.ellipse(P(36, 64, 84, 100), fill=255),
        d.ellipse(P(42, 100, 78, 142), fill=255),
        *[d.ellipse(P(*box), fill=255) for box in PAWS],
    ))
    patch(fur, 0, lambda d: (
        *[d.line(P(x, 24, x, 40), fill=255, width=4 * SS) for x in (52, 60, 68)],
        *[d.line(P(*pts), fill=255, width=4 * SS) for pts in (
            (6, 56, 22, 58), (6, 66, 20, 66), *[mirror(6, 56, 22, 58)], *[mirror(6, 66, 20, 66)],
            (26, 108, 38, 112), (24, 122, 36, 124), *[mirror(26, 108, 38, 112)], *[mirror(24, 122, 36, 124)],
            (104, 112, 120, 108), (104, 126, 120, 124), (92, 150, 96, 142),
        )],
    ))


def paint_hachiware(fur):
    patch(fur, 0, lambda d: (
        d.ellipse(P(-14, -24, 134, 78), fill=255),
        d.ellipse(P(62, 90, 104, 134), fill=255),
        tail_line(d, 20),
    ))
    patch(fur, 255, lambda d: d.polygon(P(60, 30, -4, 92, 124, 92), fill=255))


def paint_siamese(fur):
    patch(fur, 0, lambda d: (
        d.polygon(P(*EARS["normal"]), fill=255),
        d.polygon(P(*mirror(*EARS["normal"])), fill=255),
        d.ellipse(P(36, 58, 84, 100), fill=255),
        *[d.ellipse(P(*box), fill=255) for box in PAWS],
        tail_line(d, 20),
    ))


def paint_mainecoon(fur):
    patch(fur, 255, lambda d: (
        d.ellipse(P(26, 78, 94, 120), fill=255),
        d.ellipse(P(38, 66, 82, 100), fill=255),
        *[d.ellipse(P(*box), fill=255) for box in PAWS],
    ))
    patch(fur, 0, lambda d: [d.line(P(x, 26, x, 42), fill=255, width=4 * SS) for x in (52, 60, 68)])


# --- the robot (original design from the first version) ----------------------

def draw_robo() -> Image.Image:
    s = SS
    img = Image.new("L", (CHAR_W * s, CHAR_H * s), 255)
    d = ImageDraw.Draw(img)
    lw = 4 * s

    d.line(P(60, 26, 60, 10), fill=0, width=lw)
    d.ellipse(P(53, 2, 67, 16), fill=0)
    d.ellipse(P(57, 6, 61, 10), fill=255)

    d.polygon(P(14, 44, 22, 10, 50, 30), fill=0)
    d.polygon(P(106, 44, 98, 10, 70, 30), fill=0)
    d.polygon(P(22, 36, 25, 20, 40, 31), fill=255)
    d.polygon(P(98, 36, 95, 20, 80, 31), fill=255)

    d.rounded_rectangle(P(10, 24, 110, 96), radius=22 * s, fill=255, outline=0, width=lw)
    d.rounded_rectangle(P(20, 36, 100, 88), radius=14 * s, outline=0, width=2 * s)

    for cx in (42, 78):
        d.ellipse(P(cx - 9, 46, cx + 9, 66), fill=0)
        d.ellipse(P(cx - 5, 49, cx, 55), fill=255)

    for y0, y1 in ((66, 62), (72, 72), (78, 82)):
        d.line(P(2, y0, 18, y1), fill=0, width=2 * s)
        d.line(P(118, y0, 102, y1), fill=0, width=2 * s)

    d.arc(P(50, 64, 60, 74), 0, 180, fill=0, width=2 * s)
    d.arc(P(60, 64, 70, 74), 0, 180, fill=0, width=2 * s)
    d.chord(P(53, 72, 67, 84), 0, 180, fill=0)
    d.polygon(P(57, 63, 63, 63, 60, 67), fill=0)

    d.rectangle(P(50, 96, 70, 104), fill=0)
    d.rounded_rectangle(P(26, 102, 94, 150), radius=12 * s, fill=255, outline=0, width=lw)
    d.rounded_rectangle(P(44, 112, 76, 138), radius=6 * s, outline=0, width=2 * s)
    d.ellipse(P(50, 118, 60, 128), fill=0)
    d.ellipse(P(60, 118, 70, 128), fill=0)
    d.polygon(P(50, 124, 70, 124, 60, 134), fill=0)

    d.line(P(26, 112, 12, 138), fill=0, width=lw)
    d.ellipse(P(5, 132, 19, 146), fill=0)
    d.line(P(94, 112, 110, 96), fill=0, width=lw)
    d.ellipse(P(104, 86, 118, 100), fill=0)

    d.rounded_rectangle(P(32, 148, 54, 158), radius=4 * s, fill=0)
    d.rounded_rectangle(P(66, 148, 88, 158), radius=4 * s, fill=0)

    return img.resize((CHAR_W, CHAR_H), Image.LANCZOS)


# --- registry ----------------------------------------------------------------

CAT_MOUTH_Y = 82
ROBO_MOUTH_Y = 72

# key: (display name, drawing function, mouth y for the bubble tail)
CHARACTERS: dict[str, tuple[str, Callable[[], Image.Image], int]] = {
    "robo": ("ネコロボ", draw_robo, ROBO_MOUTH_Y),
    "shiro": ("白猫", Cat(stripes=True).draw, CAT_MOUTH_Y),
    "kuro": ("黒猫", Cat(fur="black", eyes="slit", collar=True).draw, CAT_MOUTH_Y),
    "mike": ("三毛猫", Cat(paint=paint_mike).draw, CAT_MOUTH_Y),
    "kijitora": ("キジトラ", Cat(fur="hatch", paint=paint_kijitora).draw, CAT_MOUTH_Y),
    "hachiware": ("ハチワレ", Cat(paint=paint_hachiware).draw, CAT_MOUTH_Y),
    "siamese": ("シャム猫", Cat(eyes="slit", paint=paint_siamese).draw, CAT_MOUTH_Y),
    "fold": ("スコティッシュフォールド", Cat(fur="dots", ears="fold", eyes="big").draw, CAT_MOUTH_Y),
    "persian": ("ペルシャ（長毛）", Cat(fluffy=True, ears="small", eyes="happy").draw, CAT_MOUTH_Y),
    "mainecoon": ("メインクーン（長毛）", Cat(fur="hatch", fluffy=True, ears="tuft", paint=paint_mainecoon).draw,
                  CAT_MOUTH_Y),
}


def get(key: str | None = None) -> tuple[Image.Image, int]:
    """Character image and its mouth y. key=None picks one at random."""
    if key is None:
        key = random.choice(list(CHARACTERS))
    _, draw, mouth_y = CHARACTERS[key]
    return draw(), mouth_y
