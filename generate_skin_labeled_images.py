from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


CARA_DB_PATH = Path(os.getenv("DB_PATH", "./cara.db"))
DEFAULT_OUTPUT_DIR = Path("assets/products/skin_labeled_preview")
PRODUCTS_DIR = Path("assets/products")
LABEL_COLOR = (14, 36, 58, 255)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Avenir.ttc",
]

LABEL_TRANSLATIONS = {
    "그린티 씨드 스킨": "Green Tea",
    "시카페어 스킨": "Cicapair",
    "워터뱅크 블루 히알루로닉 스킨": "Hyaluronic",
    "토닝 스킨": "Heartleaf",
    "라이스 워터 브라이트 스킨": "Rice",
    "히알루론 스킨": "Hyaluronic",
    "1025 독도 스킨": "Dokdo 1025",
    "멀티 버텍스 UV 스킨": "Multi UV",
    "AHA BHA 클라리파잉 스킨": "AHA BHA",
    "보리지 스킨": "Borage",
    "레티놀 유스 액티베이팅 스킨": "Retinol",
    "순수 스킨": "Pure",
    "비피다 바이옴 컴플렉스 스킨": "Bifida",
    "시카 리페어 스킨": "Cica Repair",
    "퍼펙트 스킨": "Perfect",
    "스네일 96 뮤신 파워 스킨": "Snail Mucin",
    "라이트 풀 워터 스킨": "Light Water",
    "유자 C 비타민 스킨": "Yuja C",
    "나이아신아마이드 15 스킨": "Niacinamide",
    "징코 스킨": "Ginkgo",
    "어성초 스킨": "Heartleaf",
    "시카 트러블 스킨": "Cica Trouble",
    "비타민 C 20 스킨": "Vitamin C 20",
    "프로폴리스 스킨": "Propolis",
    "레드 불가리안 로즈 스킨": "Rose",
    "수분 토닝 스킨": "Moisture",
    "콜라겐 부스팅 스킨": "Collagen",
    "나이아신아마이드 스킨": "Niacinamide",
    "알란토인 수딩 스킨": "Allantoin",
    "마데카소사이드 스킨": "Madecassoside",
    "피테라 스킨": "Pitera",
    "세라마이드 스킨": "Ceramide",
    "갈락토미세스 스킨": "Galactomyces",
    "리들샷 100 스킨": "Reedle 100",
    "비타민 스킨": "Vitamin",
    "로즈힙 스킨": "Rosehip",
    "펩타이드 스킨": "Peptide",
    "아이스 스킨": "Ice",
    "순한 pH 스킨": "Mild pH",
    "레몬 비타민 스킨": "Lemon",
    "판테놀 수딩 스킨": "Panthenol",
    "리들샷 200 스킨": "Reedle 200",
    "트러블 스킨": "Trouble",
    "수분 스킨": "Moisture",
    "알로에 스킨": "Aloe",
    "판테놀 스킨": "Panthenol",
    "라이스 스킨": "Rice",
    "쿨링 스킨": "Cooling",
    "포어 스킨": "Pore",
}


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in FONT_CANDIDATES:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int) -> ImageFont.ImageFont:
    size = start_size
    while size >= 24:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return load_font(24)


def load_skin_products() -> list[tuple[int, str]]:
    with sqlite3.connect(CARA_DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT product_id, product_name
            FROM products
            WHERE subcategory = '스킨'
            ORDER BY product_id
            """
        ).fetchall()
    return [(int(product_id), str(product_name)) for product_id, product_name in rows]


def label_for_product(product_name: str) -> str:
    if product_name in LABEL_TRANSLATIONS:
        return LABEL_TRANSLATIONS[product_name]
    return product_name.replace(" 스킨", "").strip().title()


def draw_centered_label(
    image: Image.Image,
    label: str,
    box: tuple[int, int, int, int],
    patch_existing_text: bool,
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box

    if patch_existing_text:
        # Covers the original product keyword with a feathered patch sampled
        # from the surrounding paper label, so the bottle still reads as a photo.
        patch = Image.new("RGBA", image.size, (0, 0, 0, 0))
        patch_pixels = patch.load()
        image_pixels = image.load()
        sample_offset = max(10, image.width // 55)
        left_x = max(0, x1 - sample_offset)
        right_x = min(image.width - 1, x2 + sample_offset)
        for y in range(y1, y2 + 1):
            left = image_pixels[left_x, y]
            right = image_pixels[right_x, y]
            width = max(1, x2 - x1)
            for x in range(x1, x2 + 1):
                t = (x - x1) / width
                patch_pixels[x, y] = tuple(
                    round(left[channel] * (1 - t) + right[channel] * t)
                    for channel in range(4)
                )
        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rectangle((x1, y1, x2, y2), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2, image.width // 160)))
        image.paste(Image.alpha_composite(image, patch), (0, 0), mask)

    font = fit_font(draw, label, max_width=x2 - x1 - 8, start_size=max(34, image.width // 21))
    bbox = draw.textbbox((0, 0), label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = x1 + ((x2 - x1) - text_width) / 2
    text_y = y1 + ((y2 - y1) - text_height) / 2 - bbox[1]
    draw.text((text_x, text_y), label, font=font, fill=LABEL_COLOR)


def generate_images(
    template_path: Path,
    output_dir: Path,
    label_box_ratio: tuple[float, float, float, float],
    patch_existing_text: bool,
) -> None:
    if not template_path.exists():
        raise FileNotFoundError(f"Template image not found: {template_path}")

    template = Image.open(template_path).convert("RGBA")
    width, height = template.size
    label_box = (
        round(width * label_box_ratio[0]),
        round(height * label_box_ratio[1]),
        round(width * label_box_ratio[2]),
        round(height * label_box_ratio[3]),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for product_id, product_name in load_skin_products():
        image = template.copy()
        draw_centered_label(
            image=image,
            label=label_for_product(product_name),
            box=label_box,
            patch_existing_text=patch_existing_text,
        )
        image.convert("RGB").save(output_dir / f"P{product_id:04d}.png", quality=95)

    print(f"Generated 50 skin product images in {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate photorealistic CARA skin product images from one template."
    )
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Write directly to assets/products/P0001.png through P0050.png.",
    )
    parser.add_argument(
        "--patch-existing-text",
        action="store_true",
        help="Use this only for older templates that already contain a product keyword.",
    )
    parser.add_argument("--x1", type=float, default=0.386)
    parser.add_argument("--y1", type=float, default=0.518)
    parser.add_argument("--x2", type=float, default=0.614)
    parser.add_argument("--y2", type=float, default=0.570)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = PRODUCTS_DIR if args.replace else args.output_dir
    generate_images(
        template_path=args.template,
        output_dir=output_dir,
        label_box_ratio=(args.x1, args.y1, args.x2, args.y2),
        patch_existing_text=args.patch_existing_text,
    )


if __name__ == "__main__":
    main()
