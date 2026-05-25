"""
CARA Executor Agent.

The Executor Agent receives a plan dictionary from the Planner Agent, calls the
FastAPI product tools, reranks candidate products with a RAG-style score, and
returns Top-5 items for the downstream Critic Agent.

Example:
  python executor_agent.py
"""

from __future__ import annotations

import json
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


PSYCHOGRAPHIC_RAG_WEIGHTS = {
    "maximizer":    {"rating_w": 5.0, "review_w": 3.0, "price_w": 10.0},
    "value_seeker": {"rating_w": 3.0, "review_w": 1.0, "price_w": 20.0},
    "loss_averse":  {"rating_w": 4.0, "review_w": 5.0, "price_w": 10.0},
    "impulsive":    {"rating_w": 4.0, "review_w": 4.0, "price_w": 10.0},
    "hedonic":      {"rating_w": 3.0, "review_w": 2.0, "price_w": 10.0},
    "utilitarian":  {"rating_w": 4.0, "review_w": 2.0, "price_w": 10.0},
}


class ProductToolClient:
    """HTTP client for product search tools exposed by the FastAPI module."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def search_products(
        self,
        query: str,
        max_price: float | None = None,
        style_type: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Call the search_products tool to create first-stage candidates.

        Args:
            query: Keyword from the Planner plan.
            max_price: Budget ceiling inferred by the Planner.
            style_type: Preferred style inferred by the Planner.
            category: Optional category constraint.

        Returns:
            A list of candidate product dictionaries from the FastAPI tool.
        """
        params: dict[str, str | float] = {"query": query}
        if max_price is not None:
            params["max_price"] = max_price
        if style_type is not None:
            params["style_type"] = style_type
        if category is not None:
            params["category"] = category

        payload = self._get_json("/products/search", params)
        return list(payload.get("products", []))

    def get_trending_products(
        self,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Call the get_trending_products fallback tool.

        Args:
            category: Optional category used to restrict fallback candidates.

        Returns:
            Top products sorted by review_count from the FastAPI tool.
        """
        params: dict[str, str] = {}
        if category is not None:
            params["category"] = category

        payload = self._get_json("/products/trending", params)
        return list(payload.get("products", []))

    def _get_json(
        self,
        path: str,
        params: dict[str, str | float],
    ) -> dict[str, Any]:
        """Perform a GET request against the Tool Use Module."""
        query_string = urlencode(params)
        url = f"{self.base_url}{path}"
        if query_string:
            url = f"{url}?{query_string}"

        try:
            with urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError(f"Tool call failed with HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(
                "Could not connect to the CARA Tool Use Module. "
                "Start the API server with: python main.py"
            ) from error


class ExecutorAgent:
    """
    Second CARA agent that searches and reranks products for recommendation.

    Protocol:
    1. Candidate Generation using search_products and fallback trending items.
    2. RAG Re-ranking using the score formula defined in the CARA benchmark.
    """

    def __init__(self, product_client: ProductToolClient | None = None) -> None:
        self.product_client = product_client or ProductToolClient()

    def execute_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a Planner-generated recommendation plan.

        Expected plan fields:
            query, budget_ceiling, preferred_style, top_category, avg_spend.

        Returns:
            A dictionary containing the sorted Top-5 product recommendations
            with product ID, name, price, style, rating, and RAG_score.
        """
        query = str(plan.get("query") or "")
        budget_ceiling = self._optional_float(plan.get("budget_ceiling"))
        preferred_style = plan.get("preferred_style")
        top_category = plan.get("top_category")
        psychographic_type = str(plan.get("psychographic_type") or "utilitarian")
        avg_price = self._safe_avg_price(
            plan.get("category_avg_price", plan.get("avg_spend")),
        )

        candidates = self.product_client.search_products(
            query=query,
            max_price=budget_ceiling,
            style_type=preferred_style,
            category=None,
        )
        fallback_used = False

        if len(candidates) < 3:
            fallback_used = True
            fallback_candidates = self.product_client.get_trending_products(
                category=top_category,
            )
            candidates = self._merge_candidates(candidates, fallback_candidates)

        reranked_products = [
            self._format_scored_product(
                product=product,
                rag_score=self.compute_rag_score(
                    product=product,
                    query=query,
                    preferred_style=preferred_style,
                    top_category=top_category,
                    avg_price=avg_price,
                    psychographic_type=psychographic_type,
                ),
            )
            for product in candidates
        ]
        reranked_products.sort(
            key=lambda product: product["RAG_score"],
            reverse=True,
        )

        return {
            "consumer_id": plan.get("consumer_id"),
            "query": query,
            "fallback_used": fallback_used,
            "candidate_count": len(candidates),
            "top_n": reranked_products[:5],
            "ranked_candidates": reranked_products,
        }

    @staticmethod
    def compute_rag_score(
        product: dict,
        query: str,
        preferred_style: str | None,
        top_category: str | None,
        avg_price: float,
        psychographic_type: str = "utilitarian",
    ) -> float:
        """
        Compute RAG score for a single product.

        RAG_score = 10*S + 20*delta_cat + 15*delta_style
                    + 10*exp(-abs(delta_price)/avg_price)
                    + 3*rating + 5*sentiment_score
        """
        weights = PSYCHOGRAPHIC_RAG_WEIGHTS.get(psychographic_type, PSYCHOGRAPHIC_RAG_WEIGHTS["utilitarian"])

        keyword_score = 1 if query.strip().lower() in f"{product.get('name','')} {product.get('description') or ''}".lower() else 0
        category_match = 1 if product.get("category") == top_category else 0
        style_match = 1 if product.get("style_type") == preferred_style else 0
        price_delta = abs(float(product.get("price", 0)) - avg_price)
        rating_value = product.get("rating")
        if rating_value is None:
            rating_value = product.get("star_rating", 0.0)
        rating = float(rating_value)
        sentiment = float(product.get("sentiment_score") or 0.0)
        review_norm = math.log1p(product.get("review_count", 0)) / math.log1p(5000)

        rag_score = (
            10 * keyword_score
            + 20 * category_match
            + 15 * style_match
            + weights["price_w"] * math.exp(-price_delta / max(avg_price, 1.0))
            + weights["rating_w"] * rating
            + 5 * sentiment
            + weights["review_w"] * review_norm
        )
        return round(rag_score, 4)

    @staticmethod
    def _format_scored_product(
        product: dict[str, Any],
        rag_score: float,
    ) -> dict[str, Any]:
        """Return only Critic-facing fields plus the computed RAG score."""
        return {
            "product_id": product.get("product_id"),
            "name": product.get("name"),
            "price": product.get("price"),
            "style_type": product.get("style_type"),
            "rating": product.get("rating") if product.get("rating") is not None else product.get("star_rating"),
            "RAG_score": rag_score,
        }

    @staticmethod
    def _merge_candidates(
        primary: list[dict[str, Any]],
        fallback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge candidate lists while preserving first occurrence by product_id."""
        merged: list[dict[str, Any]] = []
        seen_product_ids: set[str] = set()

        for product in primary + fallback:
            product_id = str(product.get("product_id"))
            if product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            merged.append(product)

        return merged

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        """Convert optional numeric values to float."""
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _safe_avg_price(value: Any) -> float:
        """Return avg_price with a non-zero denominator fallback."""
        if value is None:
            return 1.0

        avg_price = float(value)
        if avg_price == 0:
            return 1.0
        return avg_price


def main() -> None:
    """Run a small Executor Agent example against the local FastAPI server."""
    example_plan = {
        "consumer_id": "C0001",
        "query": "dumbbells",
        "budget_ceiling": 1_414_000,
        "preferred_style": "hedonic",
        "top_category": "electronics",
        "avg_spend": 752_666.67,
        "psychographic_type": "maximizer",
    }
    executor = ExecutorAgent()
    result = executor.execute_plan(example_plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

