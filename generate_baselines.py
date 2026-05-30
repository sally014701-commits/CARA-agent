from __future__ import annotations

import argparse
import csv
import os
import random
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONSUMERS = BASE_DIR / "consumer_profiles_200_final.csv"
DEFAULT_DB = Path(os.environ.get("DB_PATH", os.path.join(BASE_DIR, "cara.db")))
RANDOM_SEED = 20260530

OUTPUT_COLUMNS = [
    "consumer_id",
    "psychographic_type",
    "brainfry_score",
    "n_recommended",
    "product_id",
    "product_name",
    "brand",
    "price",
    "star_rating",
    "review_count",
    "baseline_type",
]


def recommendation_count(brainfry_score: str) -> int:
    score = Decimal(str(brainfry_score).strip())
    raw = Decimal("7") * (Decimal("1") - score)
    return max(1, int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def first_subcategory(value: str) -> str:
    return (value or "").split(",", 1)[0].strip()


def product_code(product_id: int) -> str:
    return f"P{int(product_id):04d}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_products(db_path: Path) -> dict[str, list[dict]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT product_id, subcategory, product_name, brand, price, star_rating, review_count
            FROM products
            ORDER BY product_id
            """
        ).fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        product = dict(row)
        product["product_id"] = product_code(product["product_id"])
        grouped.setdefault(product["subcategory"], []).append(product)
    return grouped


def result_row(consumer: dict[str, str], product: dict, n_recommended: int, baseline_type: str) -> dict:
    return {
        "consumer_id": consumer["consumer_id"],
        "psychographic_type": consumer["psychographic_type"],
        "brainfry_score": consumer["brainfry_score"],
        "n_recommended": n_recommended,
        "product_id": product["product_id"],
        "product_name": product["product_name"],
        "brand": product["brand"],
        "price": product["price"],
        "star_rating": product["star_rating"],
        "review_count": product["review_count"],
        "baseline_type": baseline_type,
    }


def build_random(consumers: list[dict[str, str]], products: dict[str, list[dict]]) -> list[dict]:
    rng = random.Random(RANDOM_SEED)
    rows: list[dict] = []
    for consumer in consumers:
        candidates = products[first_subcategory(consumer["subcategory"])]
        n_recommended = min(recommendation_count(consumer["brainfry_score"]), len(candidates))
        rows.extend(result_row(consumer, product, n_recommended, "random") for product in rng.sample(candidates, n_recommended))
    return rows


def build_popular(consumers: list[dict[str, str]], products: dict[str, list[dict]]) -> list[dict]:
    ranked = {
        subcategory: sorted(items, key=lambda product: (-int(product["review_count"] or 0), product["product_id"]))
        for subcategory, items in products.items()
    }
    rows: list[dict] = []
    for consumer in consumers:
        candidates = ranked[first_subcategory(consumer["subcategory"])]
        n_recommended = min(recommendation_count(consumer["brainfry_score"]), len(candidates))
        rows.extend(result_row(consumer, product, n_recommended, "popular") for product in candidates[:n_recommended])
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fixed random and popular baseline CSVs.")
    parser.add_argument("--consumers", type=Path, default=DEFAULT_CONSUMERS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--random-output", type=Path, default=BASE_DIR / "baseline_random_results.csv")
    parser.add_argument("--popular-output", type=Path, default=BASE_DIR / "baseline_popular_results.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    consumers = read_csv(args.consumers)
    products = load_products(args.db)
    random_rows = build_random(consumers, products)
    popular_rows = build_popular(consumers, products)
    write_csv(args.random_output, random_rows)
    write_csv(args.popular_output, popular_rows)
    print(f"Baseline-Random total recommendations: {len(random_rows)}")
    print(f"Baseline-Popular total recommendations: {len(popular_rows)}")
    print(f"Average recommendations per consumer: {len(random_rows) / len(consumers):.2f}")
    print("Baseline CSV files generated. Re-run only when baseline inputs change.")


if __name__ == "__main__":
    main()
