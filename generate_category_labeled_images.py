from __future__ import annotations

import argparse
import os
import re
import sqlite3
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CARA_DB_PATH = Path(os.getenv("DB_PATH", "./cara.db"))
TEMPLATE_DIR = Path("assets/templates/category-images")
PREVIEW_DIR = Path("assets/products/category_labeled_preview")
PRODUCTS_DIR = Path("assets/products")
CANVAS_SIZE = (900, 1200)
LABEL_COLOR = (14, 36, 58, 255)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Avenir.ttc",
]

CATEGORY_BOXES = {
    "스킨": (0.381, 0.505, 0.623, 0.580),
    "로션": (0.401, 0.574, 0.578, 0.634),
    "마스크팩": (0.310, 0.568, 0.640, 0.640),
    "립틴트": (0.434, 0.551, 0.547, 0.621),
    "하이라이터": (0.371, 0.561, 0.613, 0.631),
    "쿠션": (0.383, 0.334, 0.620, 0.369),
    "파운데이션": (0.386, 0.578, 0.559, 0.661),
    "블러셔": (0.378, 0.607, 0.615, 0.680),
    "샴푸": (0.390, 0.522, 0.587, 0.601),
    "바디워시": (0.363, 0.526, 0.585, 0.606),
}

CATEGORY_WORDS = {
    "스킨",
    "로션",
    "마스크팩",
    "립틴트",
    "하이라이터",
    "쿠션",
    "파운데이션",
    "블러셔",
    "샴푸",
    "바디워시",
    "팩",
    "씨드",
}

WORD_TRANSLATIONS = {
    "그린티": "Green Tea",
    "녹차": "Green Tea",
    "씨드": "Seed",
    "시카페어": "Cicapair",
    "시카": "Cica",
    "워터뱅크": "Water Bank",
    "워터": "Water",
    "블루": "Blue",
    "히알루로닉": "Hyaluronic",
    "히알루론": "Hyaluronic",
    "토닝": "Toning",
    "라이스": "Rice",
    "브라이트": "Bright",
    "멀티": "Multi",
    "버텍스": "Vertex",
    "클라리파잉": "Clarifying",
    "보리지": "Borage",
    "레티놀": "Retinol",
    "유스": "Youth",
    "액티베이팅": "Activating",
    "순수": "Pure",
    "비피다": "Bifida",
    "바이옴": "Biome",
    "컴플렉스": "Complex",
    "리페어": "Repair",
    "퍼펙트": "Perfect",
    "스네일": "Snail",
    "뮤신": "Mucin",
    "파워": "Power",
    "라이트": "Light",
    "풀": "Full",
    "유자": "Yuja",
    "비타민": "Vitamin",
    "나이아신아마이드": "Niacinamide",
    "징코": "Ginkgo",
    "어성초": "Heartleaf",
    "트러블": "Trouble",
    "프로폴리스": "Propolis",
    "레드": "Red",
    "불가리안": "Bulgarian",
    "로즈": "Rose",
    "수분": "Moisture",
    "촉촉": "Moisture",
    "콜라겐": "Collagen",
    "부스팅": "Boosting",
    "알란토인": "Allantoin",
    "수딩": "Soothing",
    "마데카소사이드": "Madecassoside",
    "피테라": "Pitera",
    "세라마이드": "Ceramide",
    "갈락토미세스": "Galactomyces",
    "갈락토": "Galacto",
    "리들샷": "Reedle",
    "로즈힙": "Rosehip",
    "펩타이드": "Peptide",
    "아이스": "Ice",
    "순한": "Mild",
    "레몬": "Lemon",
    "판테놀": "Panthenol",
    "알로에": "Aloe",
    "쿨링": "Cooling",
    "포어": "Pore",
    "누시바": "Nuciba",
    "슬로우": "Slow",
    "에이징": "Aging",
    "프로틴": "Protein",
    "버블": "Bubble",
    "미니마이징": "Minimizing",
    "선물": "Gift",
    "선물같은": "Gift",
    "밸런싱": "Balancing",
    "화이트닝": "Whitening",
    "나이트": "Night",
    "에어리": "Airy",
    "핏": "Fit",
    "딥": "Deep",
    "히드라": "Hydra",
    "데일리": "Daily",
    "폭탄": "Bomb",
    "진정": "Calming",
    "장벽": "Barrier",
    "복구": "Recovery",
    "리얼": "Real",
    "베리어": "Barrier",
    "클린": "Clean",
    "피부": "Skin",
    "영양": "Nutrition",
    "앰플": "Ampoule",
    "슬리핑": "Sleeping",
    "네이처": "Nature",
    "요거트": "Yogurt",
    "카밍": "Calming",
    "한방": "Herbal",
    "탄력": "Firming",
    "미백": "Brightening",
    "젤": "Gel",
    "클레이": "Clay",
    "모공": "Pore",
    "황금": "Gold",
    "골드": "Gold",
    "릴렉싱": "Relaxing",
    "라벤더": "Lavender",
    "허니": "Honey",
    "꿀": "Honey",
    "수면": "Sleeping",
    "패드": "Pad",
    "릴리프": "Relief",
    "바나나": "Banana",
    "아쿠아": "Aqua",
    "브라이트닝": "Brightening",
    "케어": "Care",
    "픽싱": "Fixing",
    "블러": "Blur",
    "퍼지": "Fudge",
    "쥬시": "Juicy",
    "래스팅": "Lasting",
    "에어": "Air",
    "무드": "Mood",
    "베젤": "Bezel",
    "슬림": "Slim",
    "데이지": "Daisy",
    "밀크": "Milk",
    "젤리": "Jelly",
    "글리터": "Glitter",
    "크림": "Cream",
    "픽스드": "Fixed",
    "비건": "Vegan",
    "시어": "Sheer",
    "아이시": "Icy",
    "제로": "Zero",
    "매트": "Matte",
    "벨벳": "Velvet",
    "글라스": "Glass",
    "코랄": "Coral",
    "코럴": "Coral",
    "내추럴": "Natural",
    "크리미": "Creamy",
    "발색": "Color",
    "글로시": "Glossy",
    "마블": "Marble",
    "오렌지": "Orange",
    "누드": "Nude",
    "픽서": "Fixer",
    "밀키": "Milky",
    "캔디": "Candy",
    "피크": "Peak",
    "새틴": "Satin",
    "오일": "Oil",
    "핑크": "Pink",
    "무광": "Matte",
    "틴티드": "Tinted",
    "코팅": "Coating",
    "프리즘": "Prism",
    "다이아몬드": "Diamond",
    "팬프레시": "Pan Fresh",
    "글로우": "Glow",
    "빔": "Beam",
    "팁": "Tip",
    "쉬머": "Shimmer",
    "루미": "Lumi",
    "스틱": "Stick",
    "크리스탈": "Crystal",
    "팔레트": "Palette",
    "선셋": "Sunset",
    "스타": "Star",
    "더스트": "Dust",
    "문빔": "Moonbeam",
    "비단결": "Silky",
    "골든": "Golden",
    "라이징": "Rising",
    "로즈골드": "Rose Gold",
    "오로라": "Aurora",
    "펄": "Pearl",
    "홀로그램": "Hologram",
    "솔라": "Solar",
    "미러": "Mirror",
    "베이지": "Beige",
    "블루밍": "Blooming",
    "샴페인": "Champagne",
    "라이팅": "Lighting",
    "코퍼": "Copper",
    "스파클": "Sparkle",
    "브론저": "Bronzer",
    "피치": "Peach",
    "화이트": "White",
    "베이스": "Base",
    "파우더": "Powder",
    "실버": "Silver",
    "피그먼트": "Pigment",
    "킬": "Kill",
    "커버": "Cover",
    "더": "The",
    "뉴": "New",
    "파운웨어": "Founwear",
    "넥타르": "Nectar",
    "드롭": "Drop",
    "프레시": "Fresh",
    "팝": "Pop",
    "어드밴스드": "Advanced",
    "리페어": "Repair",
    "인텐스": "Intense",
    "호": "Shade",
    "리미티드": "Limited",
    "리필": "Refill",
    "더마": "Derma",
    "에어핏": "Air Fit",
    "뉴트로지나": "Neutrogena",
    "롱웨어": "Longwear",
    "비비": "BB",
    "선케어": "Sun Care",
    "래스팅": "Lasting",
    "올데이": "All Day",
    "프로": "Pro",
    "스킨": "Skin",
    "롱래스팅": "Long Lasting",
    "슬림핏": "Slim Fit",
    "베이비": "Baby",
    "볼륨": "Volume",
    "빈티지": "Vintage",
    "퓨어": "Pure",
    "컬러": "Color",
    "브릭": "Brick",
    "테라코타": "Terracotta",
    "멜로우": "Mellow",
    "뮬베리": "Mulberry",
    "미니": "Mini",
    "오렌지": "Orange",
    "라즈베리": "Raspberry",
    "스트로베리": "Strawberry",
    "코코아": "Cocoa",
    "민트": "Mint",
    "밀크티": "Milk Tea",
    "버건디": "Burgundy",
    "아프리코트": "Apricot",
    "딸기": "Strawberry",
    "어시안": "Asian",
    "자두": "Plum",
    "망고": "Mango",
    "뉴트럴": "Neutral",
    "살몬": "Salmon",
    "퍼퓸드": "Perfumed",
    "헤어": "Hair",
    "스칼프": "Scalp",
    "두피": "Scalp",
    "클렌징": "Cleansing",
    "퍼밍": "Firming",
    "하이드라": "Hydra",
    "발란스": "Balance",
    "생강": "Ginger",
    "탈모": "Hair Loss",
    "비오틴": "Biotin",
    "로즈마리": "Rosemary",
    "강화": "Boost",
    "볼류마이징": "Volumizing",
    "쌀뜨물": "Rice Water",
    "모이스처": "Moisture",
    "오트밀": "Oatmeal",
    "마카다미아": "Macadamia",
    "로즈워터": "Rose Water",
}

TOKEN_PATTERN = re.compile(r"[A-Za-z]+|[0-9]+(?:\+)?|pH|SPF[0-9+]*|[가-힣]+", re.IGNORECASE)


def load_font(size: int) -> ImageFont.ImageFont:
    for font_path in FONT_CANDIDATES:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def normalize_name(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def find_template(category: str, template_dir: Path) -> Path:
    normalized_category = normalize_name(category)
    for path in template_dir.glob("*.png"):
        if normalize_name(path.stem) == normalized_category:
            return path
    raise FileNotFoundError(f"Template not found for category: {category}")


def load_products() -> list[tuple[int, str, str]]:
    with sqlite3.connect(CARA_DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT product_id, product_name, subcategory
            FROM products
            ORDER BY product_id
            """
        ).fetchall()
    return [(int(product_id), str(product_name), str(subcategory)) for product_id, product_name, subcategory in rows]


def translated_label(product_name: str, category: str) -> str:
    raw_tokens = TOKEN_PATTERN.findall(product_name)
    pieces: list[str] = []
    for token in raw_tokens:
        if token in CATEGORY_WORDS or token == category:
            continue
        if token.upper().startswith("SPF"):
            pieces.append(token.upper())
            continue
        if token.lower() == "ph":
            pieces.append("pH")
            continue
        if token.isascii():
            pieces.append(token.upper() if len(token) <= 3 else token.title())
            continue
        pieces.append(WORD_TRANSLATIONS.get(token, token))

    deduped: list[str] = []
    for piece in pieces:
        if piece and (not deduped or deduped[-1].lower() != piece.lower()):
            deduped.append(piece)

    label = " ".join(deduped).strip()
    return label or "CARA"


def standardize_template(image: Image.Image) -> tuple[Image.Image, float, int, int]:
    source = image.convert("RGBA")
    canvas_width, canvas_height = CANVAS_SIZE
    scale = min(canvas_width / source.width, canvas_height / source.height)
    scaled_size = (round(source.width * scale), round(source.height * scale))

    resized = source.resize(scaled_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", CANVAS_SIZE, (255, 255, 255, 255))
    offset_x = (canvas_width - scaled_size[0]) // 2
    offset_y = (canvas_height - scaled_size[1]) // 2
    canvas.alpha_composite(resized, (offset_x, offset_y))
    return canvas, scale, offset_x, offset_y


def transformed_box(
    source_size: tuple[int, int],
    box_ratio: tuple[float, float, float, float],
    scale: float,
    offset_x: int,
    offset_y: int,
) -> tuple[int, int, int, int]:
    source_width, source_height = source_size
    x1 = round(source_width * box_ratio[0] * scale) + offset_x
    y1 = round(source_height * box_ratio[1] * scale) + offset_y
    x2 = round(source_width * box_ratio[2] * scale) + offset_x
    y2 = round(source_height * box_ratio[3] * scale) + offset_y
    return x1, y1, x2, y2


def wrap_label(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [text]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_label(
    draw: ImageDraw.ImageDraw,
    label: str,
    box: tuple[int, int, int, int],
    start_size: int,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    x1, y1, x2, y2 = box
    max_width = max(10, x2 - x1 - 14)
    max_height = max(10, y2 - y1 - 8)

    for size in range(start_size, 13, -2):
        font = load_font(size)
        lines = wrap_label(draw, label, font, max_width)
        line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_height = max((bbox[3] - bbox[1] for bbox in line_boxes), default=size)
        spacing = max(2, round(size * 0.1))
        total_height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
        widest = max((bbox[2] - bbox[0] for bbox in line_boxes), default=0)
        if widest <= max_width and total_height <= max_height and len(lines) <= 2:
            return font, lines, spacing

    font = load_font(14)
    return font, wrap_label(draw, label, max_width), 2


def draw_label(image: Image.Image, label: str, box: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    start_size = max(24, min(46, round((y2 - y1) * 0.58)))
    font, lines, spacing = fit_label(draw, label, box, start_size)

    line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    heights = [bbox[3] - bbox[1] for bbox in line_boxes]
    total_height = sum(heights) + max(0, len(lines) - 1) * spacing
    y = y1 + ((y2 - y1) - total_height) / 2
    for line, bbox, height in zip(lines, line_boxes, heights, strict=True):
        text_width = bbox[2] - bbox[0]
        x = x1 + ((x2 - x1) - text_width) / 2
        draw.text((x, y - bbox[1]), line, font=font, fill=LABEL_COLOR)
        y += height + spacing


def generate_images(template_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    templates: dict[str, tuple[Image.Image, tuple[int, int], float, int, int]] = {}
    generated = 0

    for product_id, product_name, category in load_products():
        if category not in CATEGORY_BOXES:
            raise ValueError(f"Missing label-box config for category: {category}")

        if category not in templates:
            template_path = find_template(category, template_dir)
            source = Image.open(template_path)
            standardized, scale, offset_x, offset_y = standardize_template(source)
            templates[category] = (standardized, source.size, scale, offset_x, offset_y)

        template, source_size, scale, offset_x, offset_y = templates[category]
        label_box = transformed_box(source_size, CATEGORY_BOXES[category], scale, offset_x, offset_y)
        image = template.copy()
        draw_label(image, translated_label(product_name, category), label_box)
        image.convert("RGB").save(
            output_dir / f"P{product_id:04d}.png",
            optimize=True,
            compress_level=9,
        )
        generated += 1

    print(f"Generated {generated} product images in {output_dir}")


def make_contact_sheet(products_dir: Path, output_path: Path) -> None:
    sample_ids = [
        1, 3, 21, 51, 62, 101, 113, 151, 172, 201,
        220, 251, 258, 301, 321, 351, 380, 401, 420, 451,
    ]
    font = load_font(18)
    tiles = []
    for product_id in sample_ids:
        path = products_dir / f"P{product_id:04d}.png"
        if not path.exists():
            continue
        image = Image.open(path).convert("RGB")
        image.thumbnail((180, 240), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (200, 280), (255, 255, 255))
        tile.paste(image, ((200 - image.width) // 2, 8))
        draw = ImageDraw.Draw(tile)
        draw.text((8, 250), f"P{product_id:04d}", font=font, fill=LABEL_COLOR)
        tiles.append(tile)

    columns = 5
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 200, rows * 280), (245, 246, 247))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * 200, (index // columns) * 280))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=95)
    print(f"Saved contact sheet to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate labeled product images for every CARA category template."
    )
    parser.add_argument("--template-dir", type=Path, default=TEMPLATE_DIR)
    parser.add_argument("--output-dir", type=Path, default=PREVIEW_DIR)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Write directly to assets/products/P0001.png through P0500.png.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = PRODUCTS_DIR if args.replace else args.output_dir
    generate_images(args.template_dir, output_dir)
    make_contact_sheet(output_dir, output_dir / "contact-sheet.png")


if __name__ == "__main__":
    main()
