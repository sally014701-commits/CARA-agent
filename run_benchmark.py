from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONSUMERS = Path.home() / "Downloads" / "consumer_profiles_200_final.csv"
DEFAULT_GROUND_TRUTH = Path.home() / "Downloads" / "ground_truth_final.csv"
DEFAULT_DB = BASE_DIR / "cara.db"

TYPE_ORDER = ["Maximizer", "ValueSeeker", "LossAverse", "Impulsive", "Hedonic", "Utilitarian"]

CARA_COLUMNS = [
    "consumer_id", "psychographic_type", "brainfry_score", "n_recommended",
    "product_id", "product_name", "brand", "price", "star_rating", "rank_position",
    "critic_iterations",
]

BENCHMARK_COLUMNS = [
    "consumer_id", "psychographic_type", "brainfry_score", "n_recommended",
    "cara_hit", "random_hit", "popular_hit",
    "cara_budget_compliance", "random_budget_compliance", "popular_budget_compliance",
    "cara_alignment", "random_alignment", "popular_alignment",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def first_subcategory(value: str) -> str:
    return (value or "").split(",", 1)[0].strip()


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


def api_psychographic(value: str) -> str:
    return {
        "ValueSeeker": "value_seeker",
        "LossAverse": "loss_averse",
    }.get(normalize_type(value), normalize_type(value).lower())


def load_product_details(db_path: Path) -> dict[str, dict]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT product_id, product_name, brand, price, star_rating, review_count, preference_style
            FROM products
            ORDER BY product_id
            """
        ).fetchall()
    return {normalize_product_id(row["product_id"]): dict(row) for row in rows}


def call_cara(base_url: str, consumer: dict[str, str]) -> list[dict]:
    payload = {
        "session_id": f"benchmark-{consumer['consumer_id']}",
        "consumer_id": consumer["consumer_id"],
        "query": first_subcategory(consumer["subcategory"]),
        "budget_ceiling": int(float(consumer["budget_amount"])),
        "skin_type": (consumer.get("skin_type") or "").strip() or None,
        "preferred_style": consumer["preference_style"],
        "psychographic_type": api_psychographic(consumer["psychographic_type"]),
        "brainfry_score": float(consumer["brainfry_score"]),
        "use_vector_search": False,
        "style_confidence": 1.0,
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/recommend",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CARA API failed for {consumer['consumer_id']} with HTTP {error.code}: {body}") from error
    except URLError as error:
        raise RuntimeError(f"Could not connect to CARA API at {base_url}") from error


def run_cara(
    consumers: list[dict[str, str]],
    details: dict[str, dict],
    base_url: str,
) -> list[dict]:
    rows: list[dict] = []
    for index, consumer in enumerate(consumers, start=1):
        recommendations = call_cara(base_url, consumer)
        n_recommended = int(recommendations[0].get("n_rec", len(recommendations))) if recommendations else 0
        print(f"[{index}/{len(consumers)}] {consumer['consumer_id']} -> {len(recommendations)} recommendations")
        for rank, recommendation in enumerate(recommendations, start=1):
            product_id = normalize_product_id(recommendation.get("product_id") or recommendation.get("id"))
            detail = details.get(product_id, {})
            rows.append({
                "consumer_id": consumer["consumer_id"],
                "psychographic_type": consumer["psychographic_type"],
                "brainfry_score": consumer["brainfry_score"],
                "n_recommended": n_recommended,
                "product_id": product_id,
                "product_name": detail.get("product_name") or recommendation.get("name", ""),
                "brand": detail.get("brand", ""),
                "price": detail.get("price", recommendation.get("price", "")),
                "star_rating": detail.get("star_rating", recommendation.get("rating", "")),
                "rank_position": rank,
                "critic_iterations": recommendation.get("critic_iterations", 0),
            })
    return rows


def group_by_consumer(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["consumer_id"]].append(row)
    return dict(grouped)


def load_ground_truth(path: Path) -> dict[str, set[str]]:
    truth: dict[str, set[str]] = defaultdict(set)
    for row in read_csv(path):
        product_id = normalize_product_id(row.get("product_id"))
        if row.get("consumer_id") and product_id:
            truth[row["consumer_id"]].add(product_id)
    return dict(truth)


def hit(truth: set[str], rows: list[dict[str, str]]) -> int:
    return int(bool(truth & {normalize_product_id(row.get("product_id")) for row in rows}))


def budget_compliance(rows: list[dict[str, str]], budget: float) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if float(row.get("price") or 0) <= budget) / len(rows)


def alignment(rows: list[dict[str, str]], preferred_style: str, details: dict[str, dict]) -> float:
    if not rows:
        return 0.0
    matched = sum(
        1 for row in rows
        if str(details.get(normalize_product_id(row.get("product_id")), {}).get("preference_style", "")).lower()
        == preferred_style.lower()
    )
    return matched / len(rows)


def build_benchmark_rows(
    consumers: list[dict[str, str]],
    truth: dict[str, set[str]],
    cara: dict[str, list[dict[str, str]]],
    random_baseline: dict[str, list[dict[str, str]]],
    popular_baseline: dict[str, list[dict[str, str]]],
    details: dict[str, dict],
) -> list[dict]:
    rows: list[dict] = []
    for consumer in consumers:
        consumer_id = consumer["consumer_id"]
        if not truth.get(consumer_id):
            continue
        cara_rows = cara.get(consumer_id, [])
        random_rows = random_baseline.get(consumer_id, [])
        popular_rows = popular_baseline.get(consumer_id, [])
        budget = float(consumer["budget_amount"])
        preferred_style = consumer["preference_style"]
        n_recommended = cara_rows[0]["n_recommended"] if cara_rows else 0
        rows.append({
            "consumer_id": consumer_id,
            "psychographic_type": normalize_type(consumer["psychographic_type"]),
            "brainfry_score": consumer["brainfry_score"],
            "n_recommended": n_recommended,
            "cara_hit": hit(truth[consumer_id], cara_rows),
            "random_hit": hit(truth[consumer_id], random_rows),
            "popular_hit": hit(truth[consumer_id], popular_rows),
            "cara_budget_compliance": f"{budget_compliance(cara_rows, budget):.4f}",
            "random_budget_compliance": f"{budget_compliance(random_rows, budget):.4f}",
            "popular_budget_compliance": f"{budget_compliance(popular_rows, budget):.4f}",
            "cara_alignment": f"{alignment(cara_rows, preferred_style, details):.4f}",
            "random_alignment": f"{alignment(random_rows, preferred_style, details):.4f}",
            "popular_alignment": f"{alignment(popular_rows, preferred_style, details):.4f}",
        })
    return rows


def average(rows: list[dict], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def print_metric(title: str, rows: list[dict], keys: tuple[str, str, str], percent: bool = False) -> None:
    factor = 100 if percent else 1
    suffix = "%" if percent else ""
    print(f"\n=== {title} ===")
    print(f"CARA:             {average(rows, keys[0]) * factor:.1f}{suffix}" if percent else f"CARA:             {average(rows, keys[0]):.2f}")
    print(f"Baseline-Random:  {average(rows, keys[1]) * factor:.1f}{suffix}" if percent else f"Baseline-Random:  {average(rows, keys[1]):.2f}")
    print(f"Baseline-Popular: {average(rows, keys[2]) * factor:.1f}{suffix}" if percent else f"Baseline-Popular: {average(rows, keys[2]):.2f}")

    print(f"\n=== 유형별 {title} ===")
    print(f"{'유형':<14} {'CARA':>8} {'Random':>8} {'Popular':>8}")
    for psychographic_type in TYPE_ORDER:
        subset = [row for row in rows if row["psychographic_type"] == psychographic_type]
        values = [average(subset, key) * factor for key in keys]
        if percent:
            print(f"{psychographic_type:<14} {values[0]:>7.1f}% {values[1]:>7.1f}% {values[2]:>7.1f}%")
        else:
            print(f"{psychographic_type:<14} {values[0]:>8.2f} {values[1]:>8.2f} {values[2]:>8.2f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CARA for 200 consumers and calculate benchmark metrics.")
    parser.add_argument("--consumers", type=Path, default=DEFAULT_CONSUMERS)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cara-output", type=Path, default=BASE_DIR / "cara_results.csv")
    parser.add_argument("--random", type=Path, default=BASE_DIR / "baseline_random_results.csv")
    parser.add_argument("--popular", type=Path, default=BASE_DIR / "baseline_popular_results.csv")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "benchmark_results.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    consumers = read_csv(args.consumers)
    details = load_product_details(args.db)

    print("=== CARA benchmark run ===")
    cara_rows = run_cara(consumers, details, args.base_url)
    write_csv(args.cara_output, CARA_COLUMNS, cara_rows)

    benchmark_rows = build_benchmark_rows(
        consumers=consumers,
        truth=load_ground_truth(args.ground_truth),
        cara=group_by_consumer(cara_rows),
        random_baseline=group_by_consumer(read_csv(args.random)),
        popular_baseline=group_by_consumer(read_csv(args.popular)),
        details=details,
    )
    write_csv(args.output, BENCHMARK_COLUMNS, benchmark_rows)

    print_metric("Hit@N 결과", benchmark_rows, ("cara_hit", "random_hit", "popular_hit"), percent=True)
    print_metric(
        "예산 준수율",
        benchmark_rows,
        ("cara_budget_compliance", "random_budget_compliance", "popular_budget_compliance"),
        percent=True,
    )
    print_metric(
        "Preference Alignment Score",
        benchmark_rows,
        ("cara_alignment", "random_alignment", "popular_alignment"),
    )
    print(f"\n전체 유효 소비자 수: {len(benchmark_rows)}")
    print(f"Saved: {args.cara_output}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
