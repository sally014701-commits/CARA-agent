"""
Generate the CARA backend synthetic dataset.

Outputs:
  - products.json
  - consumers.json

Python: 3.11+
Dependency: numpy
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


RANDOM_SEED = 42
PRODUCT_COUNT = 200
CONSUMER_COUNT = 50

MIN_PRICE = 5_000
MAX_PRICE = 1_500_000
PRICE_ROUND_UNIT = 1_000

MIN_RATING = 3.5
MAX_RATING = 5.0

MIN_REVIEWS = 10
MAX_REVIEWS = 5_000

CATEGORY_ITEMS = {
    "electronics": ["smartphones", "laptops", "earbuds", "tablets", "smartwatches"],
    "fashion": ["sneakers", "jackets", "jeans", "dresses", "bags"],
    "home living": [
        "desk lamps",
        "air purifiers",
        "coffee makers",
        "pillows",
        "storage boxes",
    ],
    "beauty": ["moisturizers", "sunscreens", "serums", "lip balms", "shampoos"],
    "sports equipment": [
        "yoga mats",
        "dumbbells",
        "running shoes",
        "water bottles",
        "resistance bands",
    ],
}

STYLE_TYPES = ("practical", "design")


def rounded_uniform_price(rng: np.random.Generator) -> int:
    """Sample uniformly from the price interval and round to KRW 1,000."""
    raw_price = rng.uniform(MIN_PRICE, MAX_PRICE)
    rounded_price = int(round(raw_price / PRICE_ROUND_UNIT) * PRICE_ROUND_UNIT)
    return int(np.clip(rounded_price, MIN_PRICE, MAX_PRICE))


def one_decimal_uniform_rating(rng: np.random.Generator) -> float:
    """Sample a rating uniformly from [3.5, 5.0] and keep one decimal place."""
    return float(np.round(rng.uniform(MIN_RATING, MAX_RATING), 1))


def sample_long_tail_review_counts(
    rng: np.random.Generator,
    count: int,
) -> list[int]:
    """
    Generate long-tail review counts with numpy.random.pareto semantics.

    The rejection loop keeps the catalog shape close to the paper-style rule:
    most products have 10-200 reviews, while only a very small number approach
    the 5,000-review ceiling.
    """
    for _ in range(10_000):
        pareto_samples = rng.pareto(a=1.55, size=count)
        review_counts = MIN_REVIEWS + np.rint(pareto_samples * 28).astype(int)
        review_counts = np.clip(review_counts, MIN_REVIEWS, MAX_REVIEWS)

        low_review_share = np.mean(review_counts <= 200)
        high_review_count = int(np.sum(review_counts >= 4_000))

        if low_review_share >= 0.90 and 1 <= high_review_count <= 4:
            return review_counts.astype(int).tolist()

    raise RuntimeError("Could not generate a valid long-tail review distribution.")


def build_products(rng: np.random.Generator) -> list[dict[str, Any]]:
    products_per_subitem = PRODUCT_COUNT // sum(
        len(items) for items in CATEGORY_ITEMS.values()
    )
    review_counts = sample_long_tail_review_counts(rng, PRODUCT_COUNT)

    products: list[dict[str, Any]] = []
    product_index = 0

    for category, subitems in CATEGORY_ITEMS.items():
        for subitem in subitems:
            for _ in range(products_per_subitem):
                product_index += 1
                products.append(
                    {
                        "product_id": f"P{product_index:04d}",
                        "category": category,
                        "item_type": subitem,
                        "name": f"{subitem.title()} {product_index:04d}",
                        "price": rounded_uniform_price(rng),
                        "style_type": str(rng.choice(STYLE_TYPES, p=[0.5, 0.5])),
                        "rating": one_decimal_uniform_rating(rng),
                        "review_count": review_counts[product_index - 1],
                    }
                )

    rng.shuffle(products)
    return products


def biased_purchase_history(
    rng: np.random.Generator,
    products: list[dict[str, Any]],
    preference_style: str,
) -> list[str]:
    """Sample purchase history with higher probability for matching styles."""
    history_size = int(rng.integers(3, 21))
    weights = np.array(
        [0.75 if product["style_type"] == preference_style else 0.25 for product in products],
        dtype=float,
    )
    probabilities = weights / weights.sum()
    selected_indexes = rng.choice(
        len(products),
        size=history_size,
        replace=False,
        p=probabilities,
    )
    return [products[index]["product_id"] for index in selected_indexes]


def simulate_session_behavior(
    rng: np.random.Generator,
    preference_style: str,
) -> dict[str, Any]:
    """
    Create temporary session behavior and CTR with inverse correlation.

    CTR decreases as page visits and dwell-time variance increase, modeling
    overloaded passive scanning behavior for benchmark mocks.
    """
    if preference_style == "design":
        page_visits = int(rng.integers(20, 31))
        dwell_times = rng.uniform(30, 180, size=page_visits)
        scroll_depths = rng.uniform(0.6, 1.0, size=page_visits)
    else:
        page_visits = int(rng.integers(5, 16))
        dwell_times = rng.uniform(15, 90, size=page_visits)
        scroll_depths = rng.uniform(0.3, 0.8, size=page_visits)

    dwell_time_variance = float(np.var(dwell_times))
    normalized_visits = page_visits / 30
    normalized_variance = np.clip(dwell_time_variance / 10_000, 0.0, 1.0)

    inverse_load = 0.55 * normalized_visits + 0.45 * normalized_variance
    ctr_noise = rng.normal(0.0, 0.04)
    ctr = float(np.clip(0.82 - inverse_load + ctr_noise, 0.0, 1.0))

    brainfry_score = (
        0.4 * (page_visits / 30)
        + 0.3 * (dwell_time_variance / 10_000)
        + 0.3 * (1 - ctr)
    )

    return {
        "page_visits": page_visits,
        "dwell_times": [float(np.round(value, 2)) for value in dwell_times],
        "dwell_time_variance": float(np.round(dwell_time_variance, 2)),
        "scroll_depths": [float(np.round(value, 3)) for value in scroll_depths],
        "average_scroll_depth": float(np.round(np.mean(scroll_depths), 3)),
        "ctr": float(np.round(ctr, 4)),
        "brainfry_score": float(np.round(brainfry_score, 4)),
    }


def build_consumers(
    rng: np.random.Generator,
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    consumers: list[dict[str, Any]] = []

    for consumer_index in range(1, CONSUMER_COUNT + 1):
        preference_style = str(rng.choice(STYLE_TYPES, p=[0.5, 0.5]))
        session_behavior = simulate_session_behavior(rng, preference_style)

        consumers.append(
            {
                "consumer_id": f"C{consumer_index:04d}",
                "preference_style": preference_style,
                "budget_level": str(rng.choice(("low", "mid", "high"), p=[1 / 3, 1 / 3, 1 / 3])),
                "purchase_history": biased_purchase_history(
                    rng,
                    products,
                    preference_style,
                ),
                "session_behavior": session_behavior,
                "ctr": session_behavior["ctr"],
                "brainfry_score": session_behavior["brainfry_score"],
            }
        )

    return consumers


def write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    output_dir = Path(__file__).resolve().parent

    products = build_products(rng)
    consumers = build_consumers(rng, products)

    write_json(output_dir / "products.json", products)
    write_json(output_dir / "consumers.json", consumers)

    low_review_count = sum(product["review_count"] <= 200 for product in products)
    high_review_count = sum(product["review_count"] >= 4_000 for product in products)

    print(f"Generated {len(products)} products -> products.json")
    print(f"Generated {len(consumers)} consumers -> consumers.json")
    print(
        "Review distribution: "
        f"{low_review_count}/{len(products)} products have 10-200 reviews, "
        f"{high_review_count} products have 4,000+ reviews."
    )


if __name__ == "__main__":
    main()
