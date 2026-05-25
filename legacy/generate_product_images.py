"""
Generate consistent catalog-ready product PNG assets for CARA.

Design rules:
  - pure white background
  - centered isolated product
  - consistent camera angle, object scale, lighting, and soft floor shadow
  - no decorative backgrounds, cards, gradients, text, UI, or fake environments
  - variants keep the same base geometry and only vary color/material details

Output:
  assets/products/{product_id}.png
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter


CANVAS_SIZE = 1024
PRODUCT_BOX = (188, 164, 836, 760)
OUTPUT_DIR = Path("assets/products")
PRODUCTS_PATH = Path("products.json")

Color = tuple[int, int, int, int]
DrawFn = Callable[[ImageDraw.ImageDraw, "Palette"], None]


@dataclass(frozen=True)
class Palette:
    body: Color
    body_dark: Color
    body_light: Color
    accent: Color
    metal: Color
    rubber: Color
    glass: Color


BASE_PALETTES: list[Palette] = [
    Palette((238, 239, 236, 255), (38, 42, 48, 255), (252, 252, 250, 255), (135, 42, 38, 255), (176, 179, 181, 255), (28, 29, 32, 255), (218, 232, 240, 160)),
    Palette((35, 38, 43, 255), (10, 12, 15, 255), (92, 96, 103, 255), (195, 38, 50, 255), (156, 159, 162, 255), (16, 17, 20, 255), (214, 228, 236, 150)),
    Palette((218, 210, 196, 255), (84, 65, 48, 255), (244, 238, 226, 255), (78, 94, 77, 255), (166, 158, 146, 255), (49, 43, 38, 255), (220, 232, 236, 140)),
    Palette((220, 227, 235, 255), (31, 48, 76, 255), (247, 249, 252, 255), (45, 113, 83, 255), (170, 178, 186, 255), (23, 28, 38, 255), (214, 230, 240, 150)),
    Palette((246, 246, 244, 255), (74, 76, 80, 255), (255, 255, 255, 255), (54, 61, 172, 255), (186, 188, 190, 255), (28, 28, 30, 255), (220, 235, 242, 150)),
]


def palette_for(product_id: str) -> Palette:
    """Select a deterministic variant palette while preserving shape geometry."""
    index = int(product_id[1:]) if product_id[1:].isdigit() else 1
    return BASE_PALETTES[index % len(BASE_PALETTES)]


def add_floor_shadow(img: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Add the only allowed background effect: a subtle product floor shadow."""
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.ellipse(box, fill=(0, 0, 0, 34))
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    img.alpha_composite(shadow)


def line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: Color, width: int = 10) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: Color, outline: Color | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def ellipse(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: Color, outline: Color | None = None, width: int = 1) -> None:
    draw.ellipse(box, fill=fill, outline=outline, width=width)


def draw_smartphone(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (386, 170, 638, 714), 48, p.body_dark)
    rounded(draw, (408, 210, 616, 664), 24, p.body_light)
    rounded(draw, (470, 188, 554, 202), 7, p.rubber)
    ellipse(draw, (493, 676, 531, 714), p.accent)


def draw_laptop(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (248, 238, 776, 568), 28, p.body_dark)
    rounded(draw, (280, 270, 744, 532), 14, p.body_light)
    draw.polygon([(184, 640), (840, 640), (914, 724), (110, 724)], fill=p.metal)
    rounded(draw, (390, 664, 636, 686), 10, p.body_light)


def draw_earbuds(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (340, 486, 684, 690), 68, p.body_light, p.metal, 5)
    ellipse(draw, (302, 250, 440, 388), p.body)
    ellipse(draw, (584, 250, 722, 388), p.body)
    rounded(draw, (356, 346, 408, 542), 26, p.body)
    rounded(draw, (616, 346, 668, 542), 26, p.body)


def draw_tablet(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (298, 164, 726, 740), 46, p.body_dark)
    rounded(draw, (326, 204, 698, 700), 20, p.body_light)
    ellipse(draw, (492, 712, 532, 752), p.accent)


def draw_smartwatch(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (446, 118, 578, 300), 52, p.rubber)
    rounded(draw, (344, 286, 680, 620), 82, p.body_dark)
    rounded(draw, (392, 334, 632, 572), 52, p.body_light)
    rounded(draw, (446, 606, 578, 790), 52, p.rubber)


def draw_sneaker(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    draw.polygon([(180, 568), (312, 440), (562, 478), (792, 602), (742, 690), (226, 682)], fill=p.body)
    draw.polygon([(298, 454), (456, 384), (604, 492), (370, 506)], fill=p.body_light)
    rounded(draw, (188, 642, 798, 724), 34, p.rubber)
    line(draw, [(420, 492), (520, 532), (608, 514)], (255, 255, 255, 255), 11)
    line(draw, [(454, 514), (560, 552), (636, 542)], p.accent, 7)


def draw_jacket(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    draw.polygon([(410, 174), (614, 174), (768, 724), (256, 724)], fill=p.body)
    draw.polygon([(410, 174), (512, 332), (614, 174)], fill=p.body_light)
    line(draw, [(512, 332), (512, 720)], p.body_dark, 10)
    line(draw, [(346, 382), (214, 692)], p.body, 54)
    line(draw, [(678, 382), (810, 692)], p.body, 54)


def draw_jeans(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (352, 166, 672, 290), 26, p.body)
    draw.polygon([(366, 288), (506, 288), (466, 746), (312, 746)], fill=p.body)
    draw.polygon([(518, 288), (658, 288), (710, 746), (556, 746)], fill=p.body)
    line(draw, [(512, 298), (512, 660)], p.body_dark, 8)


def draw_dress(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    draw.polygon([(410, 166), (614, 166), (816, 744), (208, 744)], fill=p.body)
    draw.polygon([(410, 166), (512, 318), (614, 166)], fill=p.body_light)
    line(draw, [(332, 454), (692, 454)], p.accent, 8)


def draw_bag(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (248, 332, 776, 744), 70, p.body)
    line(draw, [(360, 346), (360, 220), (664, 220), (664, 346)], p.body_dark, 26)
    rounded(draw, (302, 386, 722, 710), 36, p.body_light)
    rounded(draw, (476, 476, 548, 528), 14, p.accent)


def draw_lamp(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    draw.polygon([(358, 156), (666, 156), (752, 410), (272, 410)], fill=p.body)
    rounded(draw, (480, 406, 544, 704), 24, p.metal)
    rounded(draw, (310, 704, 714, 768), 30, p.body_dark)


def draw_air_purifier(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (314, 170, 710, 750), 60, p.body_light, p.metal, 4)
    rounded(draw, (388, 236, 636, 292), 28, p.body)
    for y in range(382, 632, 38):
        line(draw, [(380, y), (644, y)], p.metal, 8)


def draw_coffee_maker(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (314, 142, 664, 540), 42, p.body_dark)
    rounded(draw, (386, 214, 592, 318), 18, p.body_light)
    rounded(draw, (406, 540, 638, 744), 34, p.glass, p.metal, 5)
    rounded(draw, (444, 596, 600, 704), 18, p.body)


def draw_pillow(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (232, 260, 792, 660), 120, p.body_light, p.metal, 4)
    line(draw, [(310, 330), (714, 590)], p.body, 6)


def draw_storage_box(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (220, 298, 804, 704), 42, p.body_light, p.metal, 4)
    rounded(draw, (190, 244, 834, 340), 36, p.body)
    rounded(draw, (448, 428, 576, 472), 16, p.accent)


def draw_bottle_product(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (394, 196, 630, 746), 82, p.body)
    rounded(draw, (434, 118, 590, 220), 34, p.body_dark)
    rounded(draw, (430, 386, 594, 572), 28, p.body_light)


def draw_lip_balm(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (424, 162, 600, 742), 70, p.body)
    rounded(draw, (402, 118, 622, 230), 38, p.body_dark)
    rounded(draw, (450, 404, 574, 560), 20, p.body_light)


def draw_yoga_mat(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (188, 390, 720, 592), 96, p.body)
    ellipse(draw, (610, 346, 830, 636), p.body_dark)
    ellipse(draw, (660, 402, 780, 580), (255, 255, 255, 255))


def draw_dumbbells(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    rounded(draw, (210, 438, 814, 520), 22, p.body_dark)
    rounded(draw, (126, 382, 232, 576), 28, p.body)
    rounded(draw, (792, 382, 898, 576), 28, p.body)
    rounded(draw, (86, 420, 146, 538), 20, p.body_dark)
    rounded(draw, (878, 420, 938, 538), 20, p.body_dark)


def draw_resistance_bands(draw: ImageDraw.ImageDraw, p: Palette) -> None:
    ellipse(draw, (206, 206, 818, 706), (0, 0, 0, 0), p.body, 38)
    ellipse(draw, (314, 298, 710, 614), (0, 0, 0, 0), p.accent, 20)
    rounded(draw, (158, 422, 292, 504), 24, p.body_dark)
    rounded(draw, (732, 422, 866, 504), 24, p.body_dark)


DRAWERS: dict[str, DrawFn] = {
    "smartphones": draw_smartphone,
    "laptops": draw_laptop,
    "earbuds": draw_earbuds,
    "tablets": draw_tablet,
    "smartwatches": draw_smartwatch,
    "sneakers": draw_sneaker,
    "jackets": draw_jacket,
    "jeans": draw_jeans,
    "dresses": draw_dress,
    "bags": draw_bag,
    "desk lamps": draw_lamp,
    "air purifiers": draw_air_purifier,
    "coffee makers": draw_coffee_maker,
    "pillows": draw_pillow,
    "storage boxes": draw_storage_box,
    "moisturizers": draw_bottle_product,
    "sunscreens": draw_bottle_product,
    "serums": draw_bottle_product,
    "lip balms": draw_lip_balm,
    "shampoos": draw_bottle_product,
    "yoga mats": draw_yoga_mat,
    "dumbbells": draw_dumbbells,
    "running shoes": draw_sneaker,
    "water bottles": draw_bottle_product,
    "resistance bands": draw_resistance_bands,
}


def render_product(product: dict[str, object]) -> Image.Image:
    """Render one isolated product in the shared catalog style."""
    img = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    add_floor_shadow(img, (260, 708, 764, 812))
    item_type = str(product["item_type"])
    drawer = DRAWERS.get(item_type, draw_bottle_product)
    drawer(draw, palette_for(str(product["product_id"])))
    return img


def main() -> None:
    products = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for product in products:
        image = render_product(product)
        image.save(OUTPUT_DIR / f"{product['product_id']}.png")
    print(f"Generated {len(products)} product images in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
