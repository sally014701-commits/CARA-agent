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
            "top_category": preference_vector.get("top_category"),
            "avg_spend": preference_vector.get("average_historical_spend"),
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
        """
        Compute BrainFry score from current session events.

        Formula:
        B = 0.4 * (n / 30) + 0.3 * (sigma_squared / 10000) + 0.3 * (1 - CTR)
        """
        clipped_ctr = min(max(session_input.ctr, 0.0), 1.0)
        return (
            0.4 * (session_input.page_visits / 30)
            + 0.3 * (session_input.dwell_time_variance / 10_000)
            + 0.3 * (1 - clipped_ctr)
        )

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
        preference_vector: dict[str, Any],
    ) -> tuple[int, str]:
        """
        Infer budget ceiling by priority.

        Priority:
        1. Explicit budget from user conversation.
        2. Maximum historical spend from consumer profile.
        3. Platform default of KRW 200,000.
        """
        if explicit_budget is not None:
            return int(explicit_budget), "explicit_user_input"

        historical_spend = preference_vector.get("maximum_historical_spend")
        if historical_spend is not None:
            return int(historical_spend), "maximum_historical_spend"

        return DEFAULT_BUDGET_CEILING, "platform_default"

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
