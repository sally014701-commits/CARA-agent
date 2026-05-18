"""
CARA Critic Agent.

The Critic Agent receives the Planner plan and Executor candidates, then runs
deterministic rule-based Reflexion to produce a final recommendation set.

Example:
  python critic_agent.py
"""

from __future__ import annotations

import json
from statistics import mean
from typing import Any


MIN_RATING = 3.8
MAX_ITERATIONS = 2
MIN_RECOMMENDATIONS = 3
MAX_RECOMMENDATIONS = 5
BUDGET_RELAXATION_FACTOR = 1.2


class CriticAgent:
    """
    Final quality-control agent for CARA recommendations.

    The agent applies deterministic checks for budget compliance, style
    diversity, rating quality, and minimum recommendation count. When the
    candidate list becomes too small, it relaxes the budget once per iteration
    and restores eligible candidates from the Executor's reserve pool.
    """

    def __init__(
        self,
        min_rating: float = MIN_RATING,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self.min_rating = min_rating
        self.max_iterations = max_iterations

    def critique(
        self,
        plan: dict[str, Any],
        executor_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate and self-correct Executor recommendations.

        Args:
            plan: Planner dictionary containing at least budget_ceiling and
                preferred_style.
            executor_result: Executor dictionary containing top_5 and,
                preferably, ranked_candidates as the reserve pool.

        Returns:
            Final recommendation set with 3-5 products, mean rating,
            critique issue logs, and correction iteration count.
        """
        original_budget = float(plan.get("budget_ceiling") or 0)
        active_budget = original_budget
        ranked_pool = self._dedupe_products(
            list(executor_result.get("ranked_candidates") or [])
            or list(executor_result.get("top_5") or [])
        )
        recommendations = self._dedupe_products(
            list(executor_result.get("top_5") or [])
        )[:MAX_RECOMMENDATIONS]
        critique_issues: list[dict[str, Any]] = []
        correction_iterations = 0

        for iteration in range(1, self.max_iterations + 1):
            correction_iterations = iteration
            before_iteration = [item.get("product_id") for item in recommendations]

            recommendations, budget_removed = self._apply_budget_compliance(
                recommendations=recommendations,
                budget_ceiling=active_budget,
                critique_issues=critique_issues,
                iteration=iteration,
            )
            recommendations = self._apply_style_diversity(
                recommendations=recommendations,
                ranked_pool=ranked_pool,
                preferred_style=plan.get("preferred_style"),
                budget_ceiling=active_budget,
                critique_issues=critique_issues,
                iteration=iteration,
            )
            recommendations = self._apply_rating_quality(
                recommendations=recommendations,
                critique_issues=critique_issues,
                iteration=iteration,
            )

            if len(recommendations) < MIN_RECOMMENDATIONS:
                active_budget *= BUDGET_RELAXATION_FACTOR
                recommendations = self._restore_after_budget_relaxation(
                    recommendations=recommendations,
                    ranked_pool=ranked_pool,
                    budget_removed=budget_removed,
                    relaxed_budget=active_budget,
                    critique_issues=critique_issues,
                    iteration=iteration,
                )

            recommendations = recommendations[:MAX_RECOMMENDATIONS]
            after_iteration = [item.get("product_id") for item in recommendations]

            if (
                len(recommendations) >= MIN_RECOMMENDATIONS
                and before_iteration == after_iteration
            ):
                break

        if len(recommendations) < MIN_RECOMMENDATIONS:
            recommendations = self._force_minimum_backfill(
                recommendations=recommendations,
                ranked_pool=ranked_pool,
                critique_issues=critique_issues,
            )

        final_recommendations = recommendations[:MAX_RECOMMENDATIONS]
        mean_rating_score = (
            round(mean(float(item.get("rating", 0.0)) for item in final_recommendations), 4)
            if final_recommendations
            else 0.0
        )

        return {
            "consumer_id": plan.get("consumer_id"),
            "final_recommendations": final_recommendations,
            "mean_rating_score": mean_rating_score,
            "critique_issues": critique_issues,
            "correction_iterations": correction_iterations,
            "final_budget_ceiling": int(active_budget),
        }

    def _apply_budget_compliance(
        self,
        recommendations: list[dict[str, Any]],
        budget_ceiling: float,
        critique_issues: list[dict[str, Any]],
        iteration: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Remove products above the active budget ceiling."""
        kept: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []

        for product in recommendations:
            if float(product.get("price", 0)) > budget_ceiling:
                removed.append(product)
            else:
                kept.append(product)

        if removed:
            critique_issues.append(
                {
                    "iteration": iteration,
                    "check": "Budget Compliance",
                    "violations": len(removed),
                    "action": "removed_over_budget_products",
                    "product_ids": [item.get("product_id") for item in removed],
                    "budget_ceiling": int(budget_ceiling),
                }
            )

        return kept, removed

    def _apply_style_diversity(
        self,
        recommendations: list[dict[str, Any]],
        ranked_pool: list[dict[str, Any]],
        preferred_style: Any,
        budget_ceiling: float,
        critique_issues: list[dict[str, Any]],
        iteration: int,
    ) -> list[dict[str, Any]]:
        """Inject one opposite-style candidate if the list is fully homogeneous."""
        if len(recommendations) < 2:
            return recommendations

        styles = {item.get("style_type") for item in recommendations}
        if len(styles) != 1:
            return recommendations

        current_style = next(iter(styles))
        opposite_style = self._opposite_style(current_style)
        if opposite_style is None:
            return recommendations

        existing_ids = {item.get("product_id") for item in recommendations}
        replacement = next(
            (
                product
                for product in ranked_pool
                if product.get("product_id") not in existing_ids
                and product.get("style_type") == opposite_style
                and float(product.get("price", 0)) <= budget_ceiling
                and float(product.get("rating", 0.0)) >= self.min_rating
            ),
            None,
        )
        if replacement is None:
            return recommendations

        replaced = recommendations[-1]
        adjusted = recommendations[:-1] + [replacement]
        adjusted.sort(key=lambda item: float(item.get("RAG_score", 0.0)), reverse=True)

        critique_issues.append(
            {
                "iteration": iteration,
                "check": "Style Diversity",
                "violations": 1,
                "action": "injected_opposite_style_product",
                "removed_product_id": replaced.get("product_id"),
                "injected_product_id": replacement.get("product_id"),
                "preferred_style": preferred_style,
            }
        )
        return adjusted

    def _apply_rating_quality(
        self,
        recommendations: list[dict[str, Any]],
        critique_issues: list[dict[str, Any]],
        iteration: int,
    ) -> list[dict[str, Any]]:
        """Remove products below the minimum rating threshold."""
        kept = [
            product
            for product in recommendations
            if float(product.get("rating", 0.0)) >= self.min_rating
        ]
        removed = [
            product
            for product in recommendations
            if float(product.get("rating", 0.0)) < self.min_rating
        ]

        if removed:
            critique_issues.append(
                {
                    "iteration": iteration,
                    "check": "Rating Quality",
                    "violations": len(removed),
                    "action": "removed_low_rating_products",
                    "product_ids": [item.get("product_id") for item in removed],
                    "minimum_rating": self.min_rating,
                }
            )

        return kept

    def _restore_after_budget_relaxation(
        self,
        recommendations: list[dict[str, Any]],
        ranked_pool: list[dict[str, Any]],
        budget_removed: list[dict[str, Any]],
        relaxed_budget: float,
        critique_issues: list[dict[str, Any]],
        iteration: int,
    ) -> list[dict[str, Any]]:
        """Restore eligible candidates after relaxing the budget by 20%."""
        existing_ids = {item.get("product_id") for item in recommendations}
        restoration_pool = self._dedupe_products(budget_removed + ranked_pool)
        restored: list[dict[str, Any]] = []

        for product in restoration_pool:
            if len(recommendations) + len(restored) >= MIN_RECOMMENDATIONS:
                break
            if product.get("product_id") in existing_ids:
                continue
            if float(product.get("price", 0)) > relaxed_budget:
                continue
            if float(product.get("rating", 0.0)) < self.min_rating:
                continue
            restored.append(product)
            existing_ids.add(product.get("product_id"))

        critique_issues.append(
            {
                "iteration": iteration,
                "check": "Minimum Count Guarantee",
                "violations": max(0, MIN_RECOMMENDATIONS - len(recommendations)),
                "action": "relaxed_budget_and_restored_candidates",
                "relaxed_budget_ceiling": int(relaxed_budget),
                "restored_product_ids": [item.get("product_id") for item in restored],
            }
        )

        adjusted = recommendations + restored
        adjusted.sort(key=lambda item: float(item.get("RAG_score", 0.0)), reverse=True)
        return adjusted

    def _force_minimum_backfill(
        self,
        recommendations: list[dict[str, Any]],
        ranked_pool: list[dict[str, Any]],
        critique_issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Guarantee at least three recommendations after max Reflexion iterations.

        This deterministic fallback keeps the rating threshold intact and uses
        the highest-ranked remaining reserve candidates, logging that the final
        minimum-count guarantee required backfill beyond normal relaxation.
        """
        existing_ids = {item.get("product_id") for item in recommendations}
        backfilled: list[dict[str, Any]] = []

        for product in ranked_pool:
            if len(recommendations) + len(backfilled) >= MIN_RECOMMENDATIONS:
                break
            if product.get("product_id") in existing_ids:
                continue
            if float(product.get("rating", 0.0)) < self.min_rating:
                continue
            backfilled.append(product)
            existing_ids.add(product.get("product_id"))

        if backfilled:
            critique_issues.append(
                {
                    "iteration": self.max_iterations,
                    "check": "Minimum Count Guarantee",
                    "violations": max(0, MIN_RECOMMENDATIONS - len(recommendations)),
                    "action": "forced_minimum_backfill_after_max_iterations",
                    "restored_product_ids": [
                        item.get("product_id") for item in backfilled
                    ],
                }
            )

        adjusted = recommendations + backfilled
        adjusted.sort(key=lambda item: float(item.get("RAG_score", 0.0)), reverse=True)
        return adjusted

    @staticmethod
    def _dedupe_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate products by product_id while preserving order."""
        deduped: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()

        for product in products:
            product_id = product.get("product_id")
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)
            deduped.append(product)

        return deduped

    @staticmethod
    def _opposite_style(style_type: Any) -> str | None:
        """Return the opposite CARA style label."""
        if style_type == "practical":
            return "design"
        if style_type == "design":
            return "practical"
        return None


def main() -> None:
    """Run a small Critic Agent example with synthetic Executor output."""
    plan = {
        "consumer_id": "C0001",
        "budget_ceiling": 500_000,
        "preferred_style": "design",
    }
    executor_result = {
        "top_5": [
            {
                "product_id": "P1",
                "name": "A",
                "price": 450_000,
                "style_type": "design",
                "rating": 4.4,
                "RAG_score": 60.0,
            },
            {
                "product_id": "P2",
                "name": "B",
                "price": 650_000,
                "style_type": "design",
                "rating": 4.2,
                "RAG_score": 58.0,
            },
            {
                "product_id": "P3",
                "name": "C",
                "price": 320_000,
                "style_type": "design",
                "rating": 3.4,
                "RAG_score": 57.0,
            },
        ],
        "ranked_candidates": [
            {
                "product_id": "P1",
                "name": "A",
                "price": 450_000,
                "style_type": "design",
                "rating": 4.4,
                "RAG_score": 60.0,
            },
            {
                "product_id": "P4",
                "name": "D",
                "price": 470_000,
                "style_type": "practical",
                "rating": 4.0,
                "RAG_score": 54.0,
            },
            {
                "product_id": "P2",
                "name": "B",
                "price": 650_000,
                "style_type": "design",
                "rating": 4.2,
                "RAG_score": 58.0,
            },
        ],
    }
    critic = CriticAgent()
    result = critic.critique(plan=plan, executor_result=executor_result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
