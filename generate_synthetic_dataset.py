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
PRODUCT_COUNT = 20000
CONSUMER_COUNT = 200

PSYCHOGRAPHIC_TYPES = ["maximizer", "value_seeker", "loss_averse", "impulsive", "hedonic", "utilitarian"]
PSYCHOGRAPHIC_COUNTS = [34, 34, 33, 33, 33, 33]
STYLE_TYPES = ("utilitarian", "hedonic")

CATEGORY_ITEMS = {
    "electronics":     ["smartphones", "laptops", "earphones", "tablets",
                        "smartwatches", "cameras", "monitors", "keyboards",
                        "mice", "chargers"],
    "fashion":         ["mens_apparel", "womens_apparel", "footwear", "bags",
                        "accessories", "watches", "hats", "scarves", "belts"],
    "home_living":     ["furniture", "lighting", "kitchenware", "bedding",
                        "storage", "cleaning_supplies", "candles", "rugs"],
    "beauty":          ["skincare", "haircare", "fragrance", "mens_grooming",
                        "body_care", "makeup", "nail_care"],
    "sports_outdoors": ["fitness_equipment", "outdoor_gear", "cycling",
                        "swimming", "yoga_pilates", "hiking", "team_sports"],
    "food_grocery":    ["health_foods", "beverages", "snacks",
                        "fresh_produce", "condiments", "supplements"],
    "baby_kids":       ["infant_products", "toys", "childrens_apparel",
                        "school_supplies", "baby_care"],
    "books_media":     ["books", "music", "film", "games", "stationery"],
    "automotive":      ["car_accessories", "car_care", "dash_cameras",
                        "car_electronics"],
    "pet_supplies":    ["dog_supplies", "cat_supplies", "pet_food",
                        "treats", "pet_accessories", "pet_grooming"],
}

CATEGORY_PRICE_RANGES = {
    "electronics":     (30_000,  1_500_000),
    "fashion":         (10_000,    500_000),
    "home_living":     (5_000,     800_000),
    "beauty":          (5_000,     200_000),
    "sports_outdoors": (10_000,    600_000),
    "food_grocery":    (1_000,      80_000),
    "baby_kids":       (5_000,     300_000),
    "books_media":     (3_000,     100_000),
    "automotive":      (5_000,     500_000),
    "pet_supplies":    (3_000,     150_000),
}

PSYCHOGRAPHIC_SESSION_PARAMS = {
    "maximizer":    {"page_visits_range": (25, 40), "dwell_range": (60, 200), "scroll_range": (0.7, 1.0), "ctr_base": 0.35, "query_ref_range": (3, 8)},
    "value_seeker": {"page_visits_range": (10, 25), "dwell_range": (30, 120), "scroll_range": (0.4, 0.8), "ctr_base": 0.50, "query_ref_range": (2, 6)},
    "loss_averse":  {"page_visits_range": (15, 35), "dwell_range": (45, 150), "scroll_range": (0.5, 0.9), "ctr_base": 0.40, "query_ref_range": (2, 7)},
    "impulsive":    {"page_visits_range": (3,  12), "dwell_range": (10, 60), "scroll_range": (0.2, 0.6), "ctr_base": 0.70, "query_ref_range": (0, 3)},
    "hedonic":      {"page_visits_range": (20, 35), "dwell_range": (60, 180), "scroll_range": (0.6, 1.0), "ctr_base": 0.45, "query_ref_range": (2, 6)},
    "utilitarian":  {"page_visits_range": (5,  18), "dwell_range": (20, 90), "scroll_range": (0.3, 0.7), "ctr_base": 0.55, "query_ref_range": (0, 3)},
}

MIN_RATING = 3.5
MAX_RATING = 5.0
MIN_REVIEWS = 10
MAX_REVIEWS = 5_000


def category_price(rng, category: str) -> int:
    lo, hi = CATEGORY_PRICE_RANGES.get(category, (5_000, 1_500_000))
    raw = rng.uniform(lo, hi)
    return int(round(raw / 1_000) * 1_000)


def one_decimal_uniform_rating(rng: np.random.Generator) -> float:
    return float(np.round(rng.uniform(MIN_RATING, MAX_RATING), 1))


def sample_long_tail_review_counts(rng: np.random.Generator, count: int) -> list[int]:
    pareto_samples = rng.pareto(a=1.55, size=count)
    review_counts = MIN_REVIEWS + np.rint(pareto_samples * 28).astype(int)
    review_counts = np.clip(review_counts, MIN_REVIEWS, MAX_REVIEWS)
    return review_counts.astype(int).tolist()


def biased_purchase_history(
    rng: np.random.Generator,
    products: list[dict[str, Any]],
    preference_style: str,
) -> list[str]:
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


def simulate_session_behavior(rng, psychographic_type: str) -> dict:
    params = PSYCHOGRAPHIC_SESSION_PARAMS[psychographic_type]
    page_visits = int(rng.integers(*params["page_visits_range"]))
    dwell_times = rng.uniform(*params["dwell_range"], size=page_visits)
    scroll_depths = rng.uniform(*params["scroll_range"], size=page_visits)
    query_reformulations = int(rng.integers(*params["query_ref_range"]))

    dwell_time_variance = float(np.var(dwell_times))
    average_scroll_depth = float(np.mean(scroll_depths))

    ctr_base = params["ctr_base"]
    ctr_noise = rng.normal(0.0, 0.04)
    ctr = float(np.clip(ctr_base + ctr_noise, 0.0, 1.0))

    N_norm = min(page_visits / 50, 1.0)
    sigma2_norm = min(dwell_time_variance / 10000, 1.0)
    SR_inv = 1.0 - average_scroll_depth
    Q_norm = min(query_reformulations / 10, 1.0)

    B_behavioral = (
        0.25 * N_norm
        + 0.25 * sigma2_norm
        + 0.20 * (1 - ctr)
        + 0.15 * SR_inv
        + 0.15 * Q_norm
    )
    brainfry_score = round(min(0.7 * B_behavioral, 1.0), 4)

    return {
        "page_visits": page_visits,
        "dwell_times": [float(round(v, 2)) for v in dwell_times],
        "dwell_time_variance": round(dwell_time_variance, 2),
        "scroll_depths": [float(round(v, 3)) for v in scroll_depths],
        "average_scroll_depth": round(average_scroll_depth, 3),
        "query_reformulations": query_reformulations,
        "ctr": round(ctr, 4),
        "brainfry_score": brainfry_score,
    }


def build_products(rng) -> list:
    total_subitems = sum(len(v) for v in CATEGORY_ITEMS.values())
    base = PRODUCT_COUNT // total_subitems
    remainder = PRODUCT_COUNT % total_subitems

    review_counts = sample_long_tail_review_counts(rng, PRODUCT_COUNT)
    products = []
    product_index = 0
    subitem_index = 0

    for category, subitems in CATEGORY_ITEMS.items():
        for subitem in subitems:
            count = base + (1 if subitem_index < remainder else 0)
            subitem_index += 1
            for _ in range(count):
                product_index += 1
                price = category_price(rng, category)

                if price >= 1_000_000:
                    brand = "premium"
                elif price >= 300_000:
                    brand = "mid"
                else:
                    brand = "budget"

                sentiment_score = float(round(rng.beta(5, 2), 2))
                stock_status = bool(rng.random() < 0.95)

                templates = [
                    f"Great {subitem}, highly recommend.",
                    f"Good value for the price. Solid {subitem}.",
                    f"Excellent quality {subitem}. Very satisfied.",
                    f"Decent {subitem} but could be better.",
                    f"Best {subitem} I have bought. Worth every penny.",
                ]
                review_text = str(rng.choice(templates))

                products.append({
                    "product_id": f"P{product_index:05d}",
                    "category": category,
                    "subcategory": subitem,
                    "name": f"{subitem.replace('_', ' ').title()} {product_index:05d}",
                    "price": price,
                    "brand": brand,
                    "style_type": str(rng.choice(["utilitarian", "hedonic"], p=[0.5, 0.5])),
                    "star_rating": one_decimal_uniform_rating(rng),
                    "review_count": review_counts[product_index - 1],
                    "review_text": review_text,
                    "sentiment_score": sentiment_score,
                    "stock_status": stock_status,
                })

    rng.shuffle(products)
    return products


def build_consumers(rng, products: list) -> list:
    consumers = []
    consumer_index = 0

    for type_idx, psychographic_type in enumerate(PSYCHOGRAPHIC_TYPES):
        count = PSYCHOGRAPHIC_COUNTS[type_idx]
        for _ in range(count):
            consumer_index += 1

            if psychographic_type == "hedonic":
                preference_style = "hedonic"
            elif psychographic_type == "utilitarian":
                preference_style = "utilitarian"
            else:
                preference_style = str(rng.choice(["utilitarian", "hedonic"]))

            session_behavior = simulate_session_behavior(rng, psychographic_type)

            consumers.append({
                "consumer_id": f"C{consumer_index:04d}",
                "psychographic_type": psychographic_type,
                "preference_style": preference_style,
                "budget_level": str(rng.choice(["low", "mid", "high"], p=[1/3, 1/3, 1/3])),
                "purchase_history": biased_purchase_history(rng, products, preference_style),
                "session_behavior": session_behavior,
                "ctr": session_behavior["ctr"],
                "brainfry_score": session_behavior["brainfry_score"],
            })

    return consumers


def write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    output_dir = Path(__file__).resolve().parent

    products = build_products(rng)
    consumers = build_consumers(rng, products)

    write_json(output_dir / "products.json", products)
    write_json(output_dir / "consumers.json", consumers)

    print(f"Generated {len(products)} products -> products.json")
    print(f"Generated {len(consumers)} consumers -> consumers.json")


if __name__ == "__main__":
    main()
