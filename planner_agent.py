"""
CARA Planner Agent.

The Planner Agent calls the FastAPI Tool Use Module, infers the user's current
cognitive load and preference constraints, then returns a recommendation plan
dictionary for the downstream Executor Agent.

Example:
  python planner_agent.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


BrainFryLevel = Literal["HIGH", "MID", "LOW"]
StyleType = Literal["practical", "design"]

DEFAULT_BUDGET_CEILING = 200_000
DEFAULT_STYLE: StyleType = "practical"


@dataclass(frozen=True)
class SessionInput:
    """Current session parameters observed by CARA before planning."""

    page_visits: int
    dwell_time_variance: float
    ctr: float
    scroll_depth: float = 0.5
    query_reformulations: int = 0
    self_report_score: float = 0.0
    text_brainfry_score: float = 0.0


@dataclass(frozen=True)
class UserIntent:
    """Explicit user constraints extracted from conversation, if present."""

    query: str = ""
    explicit_budget: int | None = None
    explicit_style: StyleType | None = None


class ToolUseClient:
    """HTTP client for CARA's FastAPI Tool Use Module."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def get_consumer_history(self, consumer_id: str) -> dict[str, Any]:
        """
        Call the get_consumer_history tool.

        Returns the consumer's purchase history, session behavior, and
        preference vector. Raises ValueError if the tool returns 404.
        """
        encoded_consumer_id = quote(consumer_id, safe="")
        url = f"{self.base_url}/consumers/{encoded_consumer_id}/history"

        try:
            with urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 404:
                raise ValueError(f"Consumer not found: {consumer_id}") from error
            raise RuntimeError(f"Tool call failed with HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(
                "Could not connect to the CARA Tool Use Module. "
                "Start the API server with: python main.py"
            ) from error

    def get_price_distributions(self) -> dict:
        url = f"{self.base_url}/products/price-distributions"
        try:
            with urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return {}


class PlannerAgent:
    """
    First CARA agent that creates an Executor-ready recommendation plan.

    The agent follows the four-step reasoning protocol:
    1. Retrieve consumer profile through the FastAPI tool.
    2. Compute conservative BrainFry status from current and previous sessions.
    3. Infer budget ceiling from explicit input, historical spend, or default.
    4. Infer preferred style from explicit input, historical top style, or default.
    """

    def __init__(self, tool_client: ToolUseClient | None = None) -> None:
        self.tool_client = tool_client or ToolUseClient()

    def create_plan(
        self,
        consumer_id: str,
        session_input: SessionInput,
        user_intent: UserIntent | None = None,
    ) -> dict[str, Any]:
        """
        Build a recommendation plan dictionary for the Executor Agent.

        Args:
            consumer_id: Target consumer ID, such as C0001.
            session_input: Current page visits, dwell-time variance, and CTR.
            user_intent: Optional explicit budget/style constraints extracted
                from the conversation.

        Returns:
            A Python dictionary containing budget_ceiling, preferred_style,
            brainfry_level, brainfry_score, query, top_category, avg_spend,
            and lightweight trace metadata.
        """
        intent = user_intent or UserIntent()

        consumer_profile = self.tool_client.get_consumer_history(consumer_id)
        preference_vector = consumer_profile.get("preference_vector", {})
        price_distributions = self.tool_client.get_price_distributions()
        target_category = self.infer_target_category(
            query=intent.query,
            preference_vector=preference_vector,
            price_distributions=price_distributions,
        )
        psychographic_type = self.classify_psychographic_type(
            session_input=session_input,
            preference_vector=preference_vector,
        )

        current_brainfry_score = self.compute_brainfry_score(session_input)
        previous_brainfry_score = preference_vector.get("brainfry_score")
        brainfry_score = self.choose_conservative_brainfry_score(
            current_brainfry_score=current_brainfry_score,
            previous_brainfry_score=previous_brainfry_score,
        )
        brainfry_level = self.classify_brainfry_level(brainfry_score)

        budget_ceiling, budget_source = self.infer_budget_ceiling(
            explicit_budget=intent.explicit_budget,
            preference_vector=preference_vector,
            target_category=target_category,
            price_distributions=price_distributions,
        )
        preferred_style, style_source = self.infer_preferred_style(
            explicit_style=intent.explicit_style,
            preference_vector=preference_vector,
        )

        return {
            "consumer_id": consumer_id,
            "query": intent.query,
            "budget_ceiling": budget_ceiling,
            "preferred_style": preferred_style,
            "top_category": target_category,
            "avg_spend": preference_vector.get("average_historical_spend"),
            "psychographic_type": psychographic_type,
            "brainfry_level": brainfry_level,
            "brainfry_score": round(brainfry_score, 4),
            "trace": {
                "budget_source": budget_source,
                "style_source": style_source,
                "current_brainfry_score": round(current_brainfry_score, 4),
                "previous_brainfry_score": previous_brainfry_score,
            },
        }

    @staticmethod
    def compute_brainfry_score(session_input: SessionInput) -> float:
        # 논문 Section IV.A: 5-signal BrainFry 공식
        N_norm = min(session_input.page_visits / 50, 1.0)
        sigma2_norm = min(session_input.dwell_time_variance / 10_000, 1.0)
        ctr_clipped = min(max(session_input.ctr, 0.0), 1.0)
        SR_inv = 1.0 - min(max(session_input.scroll_depth, 0.0), 1.0)
        Q_norm = min(session_input.query_reformulations / 10, 1.0)

        B_behavioral = (
            0.25 * N_norm
            + 0.25 * sigma2_norm
            + 0.20 * (1 - ctr_clipped)
            + 0.15 * SR_inv
            + 0.15 * Q_norm
        )

        # B_final = 0.7*B_behavioral + 0.2*B_self_report + 0.1*B_text
        B_final = (
            0.7 * B_behavioral
            + 0.2 * min(max(session_input.self_report_score, 0.0), 1.0)
            + 0.1 * min(max(session_input.text_brainfry_score, 0.0), 1.0)
        )
        return round(min(B_final, 1.0), 4)

    @staticmethod
    def classify_psychographic_type(session_input: SessionInput, preference_vector: dict) -> str:
        """
        논문 Section IV.D 기반 규칙 분류기.
        consumers.json에 psychographic_type이 있으면 그것을 우선 사용.
        신규 사용자(구매 이력 없음)에게는 세션 행동 기반으로 추론.
        """
        stored_type = preference_vector.get("psychographic_type")
        if stored_type:
            return stored_type

        n = session_input.page_visits
        ctr = session_input.ctr
        dwell_var = session_input.dwell_time_variance
        scroll = session_input.scroll_depth

        if n >= 25 and scroll >= 0.7 and dwell_var > 1000:
            return "maximizer"
        if ctr >= 0.65 and n <= 12:
            return "impulsive"
        if n >= 20 and dwell_var > 800 and ctr < 0.4:
            return "hedonic"
        if n <= 18 and ctr >= 0.5 and dwell_var < 500:
            return "utilitarian"
        if ctr < 0.35 and n >= 15:
            return "loss_averse"
        return "value_seeker"

    @staticmethod
    def choose_conservative_brainfry_score(
        current_brainfry_score: float,
        previous_brainfry_score: Any,
    ) -> float:
        """Use the maximum of current and previous BrainFry scores."""
        if previous_brainfry_score is None:
            return current_brainfry_score

        try:
            previous_score = float(previous_brainfry_score)
        except (TypeError, ValueError):
            return current_brainfry_score

        return max(current_brainfry_score, previous_score)

    @staticmethod
    def classify_brainfry_level(brainfry_score: float) -> BrainFryLevel:
        """Classify BrainFry score into HIGH, MID, or LOW."""
        if brainfry_score > 0.65:
            return "HIGH"
        if brainfry_score > 0.35:
            return "MID"
        return "LOW"

    @staticmethod
    def infer_budget_ceiling(
        explicit_budget: int | None,
        preference_vector: dict,
        target_category: str | None,
        price_distributions: dict,
    ) -> tuple[int, str]:
        """
        논문 Section IV.B: 카테고리 상대적 퍼센타일 예산 추론.
        우선순위:
        1. 사용자가 직접 입력한 예산
        2. 구매 이력 기반 카테고리 퍼센타일 → target_category에 적용
        3. 플랫폼 기본값 200,000원
        """
        if explicit_budget is not None:
            return int(explicit_budget), "explicit_user_input"

        if target_category and price_distributions:
            historical_spend = preference_vector.get("average_historical_spend")
            source_category = preference_vector.get("top_category")
            if historical_spend and source_category and source_category in price_distributions:
                source_prices = price_distributions[source_category]
                percentile = sum(1 for p in source_prices if p <= historical_spend) / len(source_prices)
                if target_category in price_distributions:
                    target_prices = price_distributions[target_category]
                    idx = percentile * (len(target_prices) - 1)
                    lo, hi = int(idx), min(int(idx) + 1, len(target_prices) - 1)
                    frac = idx - lo
                    inferred = target_prices[lo] * (1 - frac) + target_prices[hi] * frac
                    return int(inferred), "category_relative_percentile"

        fallback = preference_vector.get("maximum_historical_spend")
        if fallback is not None:
            return int(fallback), "maximum_historical_spend"

        return DEFAULT_BUDGET_CEILING, "platform_default"

    @staticmethod
    def infer_target_category(
        query: str,
        preference_vector: dict[str, Any],
        price_distributions: dict,
    ) -> str | None:
        """Use a query category match first, then fall back to historical top category."""
        normalized_query = query.strip().lower()
        for category in price_distributions:
            if category.lower() == normalized_query:
                return category

        top_category = preference_vector.get("top_category")
        if top_category:
            return top_category

        return None

    @staticmethod
    def infer_preferred_style(
        explicit_style: StyleType | None,
        preference_vector: dict[str, Any],
    ) -> tuple[StyleType, str]:
        """
        Infer preferred style by priority.

        Priority:
        1. Explicit style from user conversation.
        2. Top purchased style from consumer profile.
        3. Practical default for overloaded consumers.
        """
        if explicit_style is not None:
            return explicit_style, "explicit_user_input"

        top_style = preference_vector.get("top_style")
        if top_style in ("practical", "design"):
            return top_style, "top_style"

        return DEFAULT_STYLE, "overload_practical_default"


def main() -> None:
    """Run a small Planner Agent example against the local FastAPI server."""
    planner = PlannerAgent()
    plan = planner.create_plan(
        consumer_id="C0001",
        session_input=SessionInput(
            page_visits=24,
            dwell_time_variance=1800.0,
            ctr=0.28,
        ),
        user_intent=UserIntent(
            query="dumbbells",
            explicit_budget=None,
            explicit_style=None,
        ),
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
