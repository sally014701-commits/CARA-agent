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
            style_type=None,
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

        # Clean terms (conversational stop words and particles removed)
        normalized_query = query.strip().lower()
        stop_words = {
            "추천", "추천해줘", "추천해", "보여줘", "찾아줘", "알려줘", "해줘", "싶어", "원해", "구매", "살래", "검색", 
            "추천해드립니다", "추천해주세요", "있나요", "어떤게", "어떤", "원해요", "원합니다", "부탁해", "부탁해요", "부탁드립니다",
            "보여주세요", "찾아주세요", "알려주세요", "해줘요", "해주세요", "골라줘", "골라주세요", "골라"
        }
        particles = ["은", "는", "이", "가", "을", "를", "의", "에", "과", "와", "로", "으로", "에서", "보다", "부터", "까지"]
        
        terms = []
        for t in normalized_query.split():
            if not t:
                continue
            if t in stop_words:
                continue
            for p in particles:
                if t.endswith(p) and len(t) > len(p):
                    t = t[:-len(p)]
                    break
            if t:
                terms.append(t)
                
        LOCAL_SYNONYMS_MAP = {
            "랩탑": ["노트북", "울트라북", "태블릿pc", "랩탑", "laptops", "laptop"],
            "노트북": ["노트북", "울트라북", "태블릿pc", "랩탑", "laptops", "laptop", "맥북", "그램", "컴퓨터", "컴터", "pc"],
            "컴퓨터": ["컴퓨터", "컴터", "pc", "노트북", "데스크탑"],
            "핸드폰": ["스마트폰", "휴대폰", "폰", "갤럭시", "아이폰"],
            "스마트폰": ["스마트폰", "휴대폰", "폰", "갤럭시", "아이폰"],
            "폰": ["스마트폰", "휴대폰", "폰", "갤럭시", "아이폰"],
            "이어폰": ["무선 이어폰", "블루투스 이어폰", "이어버드", "에어팟", "버즈", "헤드폰", "헤드셋"],
            "무선이어폰": ["무선 이어폰", "블루투스 이어폰", "이어버드", "에어팟", "버즈", "헤드폰", "헤드셋"],
            "에어팟": ["무선 이어폰", "블루투스 이어폰", "이어버드", "에어팟", "버즈"],
            "버즈": ["무선 이어폰", "블루투스 이어폰", "이어버드", "에어팟", "버즈"],
            "태블릿": ["태블릿", "아이패드", "갤럭시탭", "패드", "tablet"],
            "패드": ["태블릿", "아이패드", "갤럭시탭", "패드"],
            "가방": ["백팩", "숄더백", "크로스백", "토트백", "메신저백", "가방", "백"],
            "백팩": ["백팩", "배낭", "가방"],
            "운동화": ["스니커즈", "로퍼", "구두", "런닝화", "운동화", "신발", "슈즈"],
            "신발": ["스니커즈", "로퍼", "구두", "런닝화", "운동화", "신발", "슈즈"],
            "블박": ["블랙박스", "대시캠", "블박", "dashcam"],
            "블랙박스": ["블랙박스", "대시캠", "블박", "dashcam"],
            "비타민": ["멀티비타민", "유산균", "영양제", "supplement"],
            "영양제": ["유산균", "오메가3", "멀티비타민", "루테인", "영양제", "supplement"],
            "사료": ["사료", "개사료", "고양이사료", "반려동물사료"],
            "강아지": ["강아지", "애견", "댕댕이", "dog"],
            "고양이": ["고양이", "반려묘", "냥이", "cat"],
            "laptop": ["노트북", "울트라북", "랩탑", "그램", "맥북"],
            "sneakers": ["스니커즈", "운동화", "신발", "슈즈"],
            "shoes": ["신발", "운동화", "스니커즈", "구두"],
            "running shoes": ["런닝화", "운동화", "신발", "스니커즈"],
            "yoga mat": ["요가매트", "요가", "매트"],
            "smartphone": ["스마트폰", "휴대폰", "폰", "갤럭시", "아이폰"],
            "earphones": ["무선이어폰", "이어폰", "에어팟", "버즈"],
            "skincare": ["스킨케어", "에센스", "크림", "화장품"],
            "dumbbells": ["덤벨", "아령"],
            "jacket": ["재킷", "점퍼", "바람막이", "아우터"],
            "coffee maker": ["커피머신", "커피메이커"],
            "smartwatch": ["스마트워치", "워치", "애플워치", "갤럭시워치"],
            "furniture": ["책상", "의자", "소파", "침대", "가구"],
            "tablet": ["태블릿", "아이패드", "갤럭시탭", "패드"],
            "bag": ["가방", "백팩", "숄더백"],
            "book": ["도서", "책", "소설", "에세이"],
            "monitor": ["모니터"],
            "pet food": ["사료", "간식", "펫푸드"],
            "fragrance": ["향수", "디퓨저"],
            "fitness equipment": ["운동기구", "덤벨", "매트"],
            "camera": ["카메라"],
        }
        
        keyword_score = 0
        if terms:
            match_all_terms = True
            for term in terms:
                target_words = {term}
                if term in LOCAL_SYNONYMS_MAP:
                    target_words.update(LOCAL_SYNONYMS_MAP[term])
                
                term_matched = False
                for word in target_words:
                    if word in product.get("name", "").lower():
                        term_matched = True
                        break
                    if product.get("description") and word in product.get("description", "").lower():
                        term_matched = True
                        break
                    if word in product.get("category", "").lower() or word in product.get("category_en", "").lower():
                        term_matched = True
                        break
                    if (product.get("subcategory") and word in product.get("subcategory", "").lower()) or (product.get("subcategory_en") and word in product.get("subcategory_en", "").lower()):
                        term_matched = True
                        break
                    if any(word in kw.lower() for kw in product.get("keywords_ko", [])):
                        term_matched = True
                        break
                    if any(word in syn.lower() for syn in product.get("synonyms_ko", [])):
                        term_matched = True
                        break
                    if product.get("brand") and word in product.get("brand", "").lower():
                        term_matched = True
                        break
                if not term_matched:
                    match_all_terms = False
                    break
            if match_all_terms:
                keyword_score = 1
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

