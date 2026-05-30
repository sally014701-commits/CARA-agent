from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

import anthropic
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONSUMERS = Path.home() / "Downloads" / "consumer_profiles_200_final.csv"
DEFAULT_CARA_RESULTS = BASE_DIR / "cara_results.csv"
DEFAULT_DB = BASE_DIR / "cara.db"
DEFAULT_OUTPUT = BASE_DIR / "persona_scores.csv"
MODEL = "claude-sonnet-4-6"

TYPE_ORDER = [
    "Maximizer",
    "ValueSeeker",
    "LossAverse",
    "Impulsive",
    "Hedonic",
    "Utilitarian",
]

PERSONA_PROMPTS = {
    "Maximizer": """당신은 완벽주의 쇼핑객입니다.
최고 품질의 상품만 원하며 후회를 극도로 싫어합니다.
채점 기준:
- 평점 4.5 이상 상품이 있으면 높은 점수
- review_count가 많을수록 신뢰도 높아 높은 점수
- 추천 개수가 1~2개로 너무 적으면 불만족 (감점)
- 평점 4.0 미만 상품 포함 시 감점
숫자 두 개만 반환: Persona_Satisfaction Decision_Ease""",
    "ValueSeeker": """당신은 가성비를 최우선으로 생각하는 쇼핑객입니다.
예산 대비 최고의 가치를 원합니다.
채점 기준:
- 상품 가격이 예산보다 충분히 낮을수록 높은 점수
- 평점 4.0 이상이면 충분
- 예산에 거의 근접하거나 초과하는 상품 포함 시 감점
- 평점 대비 가격이 합리적이면 높은 점수
숫자 두 개만 반환: Persona_Satisfaction Decision_Ease""",
    "LossAverse": """당신은 후회를 극도로 두려워하는 쇼핑객입니다.
검증된 안전한 선택만 원합니다.
채점 기준:
- review_count 1000개 이상 상품 포함 시 높은 점수
- 평점 4.5 이상으로 안정적이면 높은 점수
- review_count 200개 미만 상품 포함 시 감점
- 검증되지 않은 낮은 리뷰 상품은 강하게 감점
숫자 두 개만 반환: Persona_Satisfaction Decision_Ease""",
    "Impulsive": """당신은 즉각적인 결정을 선호하는 충동적 쇼핑객입니다.
빠르게 결정할 수 있는 단순한 추천을 원합니다.
채점 기준:
- 추천 개수 1개: 최고 점수
- 추천 개수 2개: 높은 점수
- 추천 개수 3개 이상: 결정이 어려워 감점
- 상품 품질보다 선택의 단순함이 핵심
숫자 두 개만 반환: Persona_Satisfaction Decision_Ease""",
    "Hedonic": """당신은 감성과 브랜드를 중시하는 쇼핑객입니다.
제품의 경험, 디자인, 브랜드 가치를 중요하게 생각합니다.
채점 기준:
- brand_tier=premium 상품 포함 시 높은 점수
- preference_style=hedonic 상품 비율 높을수록 높은 점수
- keywords에 향기, 글로우, 광채, 브랜드, 감성,
  트렌디, 로맨틱, 반짝임 포함 시 가산점
- utilitarian 상품만 있으면 감점
숫자 두 개만 반환: Persona_Satisfaction Decision_Ease""",
    "Utilitarian": """당신은 기능과 효율을 최우선으로 생각하는 쇼핑객입니다.
실질적인 성능과 스펙을 중시합니다.
채점 기준:
- preference_style=utilitarian 상품 비율 높을수록 높은 점수
- 예산 내에서 평점이 높은 기능성 상품이면 높은 점수
- keywords에 성분, 기능, 효능, SPF, 세라마이드,
  히알루론산, 지속력, 커버 포함 시 가산점
- hedonic 상품만 있거나 브랜드만 강조되면 감점
숫자 두 개만 반환: Persona_Satisfaction Decision_Ease""",
}

OUTPUT_COLUMNS = [
    "consumer_id",
    "psychographic_type",
    "persona_satisfaction",
    "decision_ease",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def normalize_product_id(value: str | int | None) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return f"P{int(digits):04d}" if digits else text


def normalize_type(value: str | None) -> str:
    compact = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())
    return {
        "maximizer": "Maximizer",
        "valueseeker": "ValueSeeker",
        "lossaverse": "LossAverse",
        "impulsive": "Impulsive",
        "hedonic": "Hedonic",
        "utilitarian": "Utilitarian",
    }.get(compact, str(value or "").strip())


def load_products(db_path: Path) -> dict[str, dict]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT product_id, product_name, brand, brand_tier, price,
                   star_rating, review_count, preference_style, keywords
            FROM products
            ORDER BY product_id
            """
        ).fetchall()
    return {normalize_product_id(row["product_id"]): dict(row) for row in rows}


def group_recommendations(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(path):
        grouped[row["consumer_id"]].append(row)
    return dict(grouped)


def build_user_message(consumer: dict[str, str], recommendations: list[dict[str, str]], products: dict[str, dict]) -> str:
    product_lines = []
    for recommendation in recommendations:
        product = products.get(normalize_product_id(recommendation.get("product_id")), {})
        product_lines.append(
            f"{product.get('product_name', recommendation.get('product_name', ''))}, "
            f"브랜드:{product.get('brand', recommendation.get('brand', ''))}"
            f"({product.get('brand_tier', '')}), "
            f"가격:{product.get('price', recommendation.get('price', ''))}원, "
            f"평점:{product.get('star_rating', recommendation.get('star_rating', ''))}, "
            f"리뷰수:{product.get('review_count', '')}, "
            f"스타일:{product.get('preference_style', '')}, "
            f"키워드:{product.get('keywords', '')}"
        )
    products_text = "\n".join(f"- {line}" for line in product_lines) or "- 추천 상품 없음"
    return f"""추천 상품 목록:
{products_text}
(총 {len(recommendations)}개 추천 / 소비자 예산:{consumer['budget_amount']}원)

Persona_Satisfaction과 Decision_Ease를
각각 1~5점으로 채점해줘.
숫자 두 개만 반환 (예: 4 3)"""


def parse_scores(text: str) -> tuple[float, float]:
    numbers = re.findall(r"(?<!\d)([1-5](?:\.\d+)?)(?!\d)", text)
    if len(numbers) < 2:
        return 3.0, 3.0
    satisfaction, ease = (float(numbers[0]), float(numbers[1]))
    if not (1 <= satisfaction <= 5 and 1 <= ease <= 5):
        return 3.0, 3.0
    return satisfaction, ease


def request_scores(
    client: anthropic.Anthropic,
    persona_type: str,
    user_message: str,
    retries: int,
) -> tuple[float, float]:
    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=20,
                temperature=0,
                system=PERSONA_PROMPTS[persona_type],
                messages=[{"role": "user", "content": user_message}],
            )
            return parse_scores(response.content[0].text.strip())
        except Exception as error:
            if attempt == retries:
                print(f"  API fallback -> 3 3 ({type(error).__name__})")
                return 3.0, 3.0
            time.sleep(2 ** attempt)
    return 3.0, 3.0


def write_results(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def average(rows: list[dict], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def print_summary(rows: list[dict]) -> None:
    print("\n=== Persona Satisfaction Score ===")
    print(f"전체 평균: {average(rows, 'persona_satisfaction'):.1f}/5")
    print("\n유형별:")
    for persona_type in TYPE_ORDER:
        subset = [row for row in rows if row["psychographic_type"] == persona_type]
        print(f"{persona_type + ':':<13} {average(subset, 'persona_satisfaction'):.1f}/5")

    print("\n=== Decision Ease Score ===")
    print(f"전체 평균: {average(rows, 'decision_ease'):.1f}/5")
    print("\n유형별:")
    for persona_type in TYPE_ORDER:
        subset = [row for row in rows if row["psychographic_type"] == persona_type]
        print(f"{persona_type + ':':<13} {average(subset, 'decision_ease'):.1f}/5")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score CARA recommendations with Claude persona prompts.")
    parser.add_argument("--cara-results", type=Path, default=DEFAULT_CARA_RESULTS)
    parser.add_argument("--consumers", type=Path, default=DEFAULT_CONSUMERS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="Score only the first N consumers.")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="Print the first prompt without calling Claude.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(BASE_DIR / ".env", override=True)
    consumers = read_csv(args.consumers)
    if args.limit is not None:
        consumers = consumers[: max(0, args.limit)]
    recommendations = group_recommendations(args.cara_results)
    products = load_products(args.db)

    if args.dry_run:
        consumer = consumers[0]
        persona_type = normalize_type(consumer["psychographic_type"])
        print(f"system ({persona_type}):\n{PERSONA_PROMPTS[persona_type]}")
        print(f"\nuser:\n{build_user_message(consumer, recommendations.get(consumer['consumer_id'], []), products)}")
        return

    client = anthropic.Anthropic()
    rows = []
    for index, consumer in enumerate(consumers, start=1):
        persona_type = normalize_type(consumer["psychographic_type"])
        user_message = build_user_message(consumer, recommendations.get(consumer["consumer_id"], []), products)
        satisfaction, ease = request_scores(client, persona_type, user_message, args.retries)
        rows.append({
            "consumer_id": consumer["consumer_id"],
            "psychographic_type": persona_type,
            "persona_satisfaction": f"{satisfaction:.1f}",
            "decision_ease": f"{ease:.1f}",
        })
        write_results(args.output, rows)
        print(f"[{index}/{len(consumers)}] {consumer['consumer_id']} {persona_type}: {satisfaction:.1f} {ease:.1f}")

    print_summary(rows)
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
