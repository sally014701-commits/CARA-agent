import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import httpx


BASE_URL = "http://127.0.0.1:8000"


def _rating(product: dict) -> float:
    return float(product.get("star_rating", product.get("rating", 0)) or 0)


def build_ground_truth(products: list, preferred_style: str, budget: int, n_rec: int) -> list:
    eligible = [
        p for p in products
        if p.get("style_type") == preferred_style
        and p.get("price", 0) <= budget
        and _rating(p) > 4.0
    ]
    eligible.sort(
        key=lambda p: _rating(p) + float(p.get("sentiment_score", 0) or 0),
        reverse=True,
    )
    return [p["product_id"] for p in eligible[:n_rec]]


def compute_hit_at_n(recommended_ids: list, ground_truth_ids: list) -> int:
    return int(bool(set(recommended_ids) & set(ground_truth_ids)))


def compute_budget_compliance(recommendations: list, budget: int) -> float:
    if not recommendations:
        return 0.0
    compliant = sum(1 for p in recommendations if p.get("price", 0) <= budget)
    return round(compliant / len(recommendations), 4)


def compute_preference_alignment(recommendations: list, preferred_style: str) -> float:
    if not recommendations:
        return 0.0
    matched = sum(1 for p in recommendations if p.get("style_type") == preferred_style)
    return round(matched / len(recommendations), 4)


def estimate_brainfry_reduction(brainfry_before: float, n_rec: int) -> float:
    reduction_factor = (8 - n_rec) / 7
    return round(brainfry_before * 0.4 * reduction_factor, 4)


SCENARIOS = [
    {"consumer_id": "C0001", "query": "laptop", "budget_ceiling": 1500000, "preferred_style": "utilitarian", "psychographic_type": "utilitarian"},
    {"consumer_id": "C0002", "query": "sneakers", "budget_ceiling": 150000, "preferred_style": "hedonic", "psychographic_type": "hedonic"},
    {"consumer_id": "C0003", "query": "yoga mat", "budget_ceiling": 80000, "preferred_style": "utilitarian", "psychographic_type": "value_seeker"},
    {"consumer_id": "C0004", "query": "smartphone", "budget_ceiling": 1200000, "preferred_style": "utilitarian", "psychographic_type": "maximizer"},
    {"consumer_id": "C0005", "query": "earphones", "budget_ceiling": 200000, "preferred_style": "hedonic", "psychographic_type": "impulsive"},
    {"consumer_id": "C0006", "query": "skincare", "budget_ceiling": 100000, "preferred_style": "hedonic", "psychographic_type": "hedonic"},
    {"consumer_id": "C0007", "query": "dumbbells", "budget_ceiling": 300000, "preferred_style": "utilitarian", "psychographic_type": "utilitarian"},
    {"consumer_id": "C0008", "query": "jacket", "budget_ceiling": 200000, "preferred_style": "hedonic", "psychographic_type": "loss_averse"},
    {"consumer_id": "C0009", "query": "coffee maker", "budget_ceiling": 500000, "preferred_style": "utilitarian", "psychographic_type": "value_seeker"},
    {"consumer_id": "C0010", "query": "smartwatch", "budget_ceiling": 400000, "preferred_style": "hedonic", "psychographic_type": "impulsive"},
    {"consumer_id": "C0011", "query": "furniture", "budget_ceiling": 800000, "preferred_style": "hedonic", "psychographic_type": "hedonic"},
    {"consumer_id": "C0012", "query": "running shoes", "budget_ceiling": 180000, "preferred_style": "utilitarian", "psychographic_type": "maximizer"},
    {"consumer_id": "C0013", "query": "tablet", "budget_ceiling": 700000, "preferred_style": "utilitarian", "psychographic_type": "loss_averse"},
    {"consumer_id": "C0014", "query": "bag", "budget_ceiling": 250000, "preferred_style": "hedonic", "psychographic_type": "hedonic"},
    {"consumer_id": "C0015", "query": "book", "budget_ceiling": 30000, "preferred_style": "utilitarian", "psychographic_type": "utilitarian"},
    {"consumer_id": "C0016", "query": "monitor", "budget_ceiling": 600000, "preferred_style": "utilitarian", "psychographic_type": "maximizer"},
    {"consumer_id": "C0017", "query": "pet food", "budget_ceiling": 50000, "preferred_style": "utilitarian", "psychographic_type": "value_seeker"},
    {"consumer_id": "C0018", "query": "fragrance", "budget_ceiling": 120000, "preferred_style": "hedonic", "psychographic_type": "impulsive"},
    {"consumer_id": "C0019", "query": "fitness equipment", "budget_ceiling": 1000000, "preferred_style": "utilitarian", "psychographic_type": "loss_averse"},
    {"consumer_id": "C0020", "query": "camera", "budget_ceiling": 900000, "preferred_style": "utilitarian", "psychographic_type": "maximizer"},
]


async def run_cara(scenario: dict, client: httpx.AsyncClient) -> dict:
    resp = await client.post(f"{BASE_URL}/admin/benchmark/evaluate", json=scenario, timeout=60)
    return resp.json()


async def run_baseline_popular(scenario: dict, client: httpx.AsyncClient, products: list) -> dict:
    from persona_evaluator import PersonaEvaluator

    brainfry_score = 0.5
    n_rec = max(1, round(7 * (1 - brainfry_score)))

    resp = await client.get(f"{BASE_URL}/products/trending", params={"category": scenario.get("query", "")}, timeout=30)
    popular = resp.json().get("products", [])[:n_rec]

    evaluator = PersonaEvaluator()
    plan_ctx = {**scenario, "brainfry_level": "MID", "brainfry_score": brainfry_score, "n_rec": n_rec}
    scores = evaluator.evaluate_all(popular, plan_ctx)

    gt = build_ground_truth(products, scenario["preferred_style"], scenario["budget_ceiling"], n_rec)
    recommended_ids = [p.get("product_id", "") for p in popular]

    return {
        "recommendations": popular,
        "n_rec": n_rec,
        "persona_evaluation": scores,
        "mean_satisfaction": round(sum(v["persona_satisfaction_score"] for v in scores.values()) / 6, 2),
        "hit_at_n": compute_hit_at_n(recommended_ids, gt),
        "budget_compliance": compute_budget_compliance(popular, scenario["budget_ceiling"]),
        "preference_alignment": compute_preference_alignment(popular, scenario["preferred_style"]),
        "brainfry_reduction": 0.0,
    }


async def main():
    results = []

    async with httpx.AsyncClient() as client:
        catalog_resp = await client.get(f"{BASE_URL}/products/search", params={"query": ""}, timeout=30)
        catalog_resp.raise_for_status()
        all_products = catalog_resp.json().get("products", [])

        for i, scenario in enumerate(SCENARIOS):
            print(f"[{i+1}/20] {scenario['query']} ({scenario['psychographic_type']}) running...")

            cara = await run_cara(scenario, client)
            baseline = await run_baseline_popular(scenario, client, all_products)

            cara_recs = cara.get("recommendations", [])
            cara_n_rec = cara.get("n_rec", 5)
            cara_brainfry = cara.get("plan", {}).get("brainfry_score", 0.5)
            gt = build_ground_truth(all_products, scenario["preferred_style"], scenario["budget_ceiling"], cara_n_rec)
            cara_ids = [p.get("product_id", "") for p in cara_recs]

            results.append({
                "scenario": scenario,
                "cara": {
                    "mean_satisfaction": cara.get("mean_satisfaction"),
                    "mean_decision_ease": cara.get("mean_decision_ease"),
                    "hit_at_n": compute_hit_at_n(cara_ids, gt),
                    "budget_compliance": compute_budget_compliance(cara_recs, scenario["budget_ceiling"]),
                    "preference_alignment": compute_preference_alignment(cara_recs, scenario["preferred_style"]),
                    "brainfry_reduction": estimate_brainfry_reduction(cara_brainfry, cara_n_rec),
                    "n_rec": cara_n_rec,
                    "persona_scores": cara.get("persona_evaluation"),
                },
                "baseline": {
                    "mean_satisfaction": baseline.get("mean_satisfaction"),
                    "hit_at_n": baseline.get("hit_at_n"),
                    "budget_compliance": baseline.get("budget_compliance"),
                    "preference_alignment": baseline.get("preference_alignment"),
                    "brainfry_reduction": 0.0,
                },
                "delta_satisfaction": round(
                    (cara.get("mean_satisfaction") or 0) - (baseline.get("mean_satisfaction") or 0),
                    2,
                ),
            })

    avg_cara_sat = sum(r["cara"]["mean_satisfaction"] or 0 for r in results) / len(results)
    avg_base_sat = sum(r["baseline"]["mean_satisfaction"] or 0 for r in results) / len(results)
    avg_hit = sum(r["cara"]["hit_at_n"] for r in results) / len(results)
    avg_budget = sum(r["cara"]["budget_compliance"] for r in results) / len(results)
    avg_pref = sum(r["cara"]["preference_alignment"] for r in results) / len(results)
    avg_reduction = sum(r["cara"]["brainfry_reduction"] for r in results) / len(results)

    print("\n" + "=" * 60)
    print("CARA vs Baseline comparison")
    print("=" * 60)
    print(f"CARA mean satisfaction:    {avg_cara_sat:.2f} / 5.0")
    print(f"Baseline satisfaction:     {avg_base_sat:.2f} / 5.0")
    print(f"Improvement:               +{avg_cara_sat - avg_base_sat:.2f}")
    print(f"Hit@N:                     {avg_hit*100:.1f}%")
    print(f"Budget Compliance Rate:    {avg_budget*100:.1f}%")
    print(f"Preference Alignment:      {avg_pref:.3f}")
    print(f"BrainFry Reduction Rate:   {avg_reduction:.4f}")
    print("=" * 60)

    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved detailed results: benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())
