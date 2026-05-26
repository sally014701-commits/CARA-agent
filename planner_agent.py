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
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
from dotenv import load_dotenv
import openai as _openai

load_dotenv(Path(__file__).parent / ".env", override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


def is_price_constraint_term(term: str) -> bool:
    normalized = term.strip().lower().replace(",", "")
    if normalized in {"이하", "이상", "미만", "초과", "under", "below", "over"}:
        return True
    return bool(re.fullmatch(r"[$₩]?\d+(\.\d+)?(원|만원|천원|만|k|krw)?", normalized))


def clean_query_with_llm_and_fallback(query: str) -> str:
    """Use GPT-4o-mini to extract clean search keywords from natural language query, with a rule-based fallback."""
    if not query or len(query.strip()) < 2:
        return query

    # Try LLM first
    if OPENAI_API_KEY:
        try:
            client = _openai.OpenAI(api_key=OPENAI_API_KEY)
            prompt = f"""당신은 쇼핑 검색 시스템의 한국어 쿼리 정제기입니다.
사용자가 입력한 자연어 검색어에서 검색의 핵심이 되는 상품 키워드(단일 명사 또는 핵심 복합 명사)만 추출해 주세요.

규칙:
1. "추천", "해줘", "보여줘", "살래", "싶어", "있어" 등 대화체, 서술어, 조사, 수식어는 모두 제외하십시오.
2. 예시:
   - "휴대폰 추천해줘" -> "휴대폰"
   - "가성비 좋은 노트북 보여줄래?" -> "노트북"
   - "러닝화 원해요" -> "러닝화"
   - "이쁜 백팩" -> "백팩"
   - "스마트워치" -> "스마트워치"
3. 추출된 키워드 한 단어(혹은 띄어쓰기로 연결된 핵심 단어)만 직접 출력하십시오. 다른 설명이나 포맷팅은 절대 하지 마십시오.

사용자 검색어: "{query}"
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=20,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            result = resp.choices[0].message.content.strip()
            if result:
                return result
        except Exception:
            pass

    # Rule-based fallback if LLM fails or API key is missing
    normalized_query = query.strip().lower()
    raw_terms = [t for t in normalized_query.split() if t]
    
    stop_words = {
        "추천", "추천해줘", "추천해", "보여줘", "찾아줘", "알려줘", "해줘", "싶어", "원해", "구매", "살래", "검색", 
        "추천해드립니다", "추천해주세요", "있나요", "어떤게", "어떤", "원해요", "원합니다", "부탁해", "부탁해요", "부탁드립니다",
        "보여주세요", "찾아주세요", "알려주세요", "해줘요", "해주세요", "골라줘", "골라주세요", "골라",
        "이하", "이상", "미만", "초과", "under", "below", "over"
    }
    particles = ["은", "는", "이", "가", "을", "를", "의", "에", "과", "와", "로", "으로", "에서", "보다", "부터", "까지"]
    
    terms = []
    for t in raw_terms:
        if t in stop_words or is_price_constraint_term(t):
            continue
        for p in particles:
            if t.endswith(p) and len(t) > len(p):
                t = t[:-len(p)]
                break
        if t:
            terms.append(t)
            
    return " ".join(terms) if terms else query



BrainFryLevel = Literal["HIGH", "MID", "LOW"]
StyleType = Literal["utilitarian", "hedonic"]

DEFAULT_BUDGET_CEILING = 200_000
DEFAULT_STYLE: StyleType = "utilitarian"


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
        cleaned_query = clean_query_with_llm_and_fallback(intent.query)

        consumer_profile = self.tool_client.get_consumer_history(consumer_id)
        preference_vector = consumer_profile.get("preference_vector", {})
        price_distributions = self.tool_client.get_price_distributions()
        target_category = self.infer_target_category(
            query=cleaned_query,
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
            "query": cleaned_query,
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
        # ?쇰Ц Section IV.A: 5-signal BrainFry 怨듭떇
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
        ?쇰Ц Section IV.D 湲곕컲 洹쒖튃 遺꾨쪟湲?
        consumers.json??psychographic_type???덉쑝硫?洹멸쾬???곗꽑 ?ъ슜.
        ?좉퇋 ?ъ슜??援щℓ ?대젰 ?놁쓬)?먭쾶???몄뀡 ?됰룞 湲곕컲?쇰줈 異붾줎.
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
        ?쇰Ц Section IV.B: 移댄뀒怨좊━ ?곷????쇱꽱????덉궛 異붾줎.
        ?곗꽑?쒖쐞:
        1. ?ъ슜?먭? 吏곸젒 ?낅젰???덉궛
        2. 援щℓ ?대젰 湲곕컲 移댄뀒怨좊━ ?쇱꽱?????target_category???곸슜
        3. ?뚮옯??湲곕낯媛?200,000??        """
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
        CATEGORY_ENG_TO_KO = {
            "electronics": "전자기기",
            "fashion": "패션",
            "home_living": "홈/리빙",
            "beauty": "뷰티/퍼스널케어",
            "sports_outdoors": "스포츠/아웃도어",
            "food_grocery": "식품",
            "baby_kids": "유아/키즈",
            "books_media": "도서/미디어",
            "automotive": "자동차용품",
            "pet_supplies": "반려동물용품",
        }
        normalized_query = query.strip().lower()
        mapped_query = CATEGORY_ENG_TO_KO.get(normalized_query, normalized_query)

        # 1. Direct Category Match
        for category in price_distributions:
            if category.lower() == mapped_query:
                return category

        # 2. Subcategory or Keyword to Parent Category Mapping
        SUB_TO_CAT = {
            # 전자기기 (electronics)
            "smartphones": "전자기기", "laptops": "전자기기", "earphones": "전자기기", "tablets": "전자기기",
            "smartwatches": "전자기기", "cameras": "전자기기", "monitors": "전자기기", "keyboards": "전자기기",
            "mice": "전자기기", "chargers": "전자기기",
            "스마트폰": "전자기기", "노트북": "전자기기", "무선이어폰": "전자기기", "이어폰": "전자기기", "태블릿": "전자기기",
            "스마트워치": "전자기기", "카메라": "전자기기", "모니터": "전자기기", "키보드": "전자기기",
            "마우스": "전자기기", "충전기": "전자기기", "랩탑": "전자기기", "laptop": "전자기기",
            "핸드폰": "전자기기", "휴대폰": "전자기기", "폰": "전자기기", "아이폰": "전자기기", "갤럭시": "전자기기",
            "에어팟": "전자기기", "버즈": "전자기기", "헤드폰": "전자기기", "패드": "전자기기", "맥북": "전자기기", "그램": "전자기기",
            "smartphone": "전자기기", "earphone": "전자기기", "tablet": "전자기기", "smartwatch": "전자기기", "camera": "전자기기", "monitor": "전자기기",
            # 패션 (fashion)
            "mens_apparel": "패션", "womens_apparel": "패션", "footwear": "패션", "bags": "패션",
            "accessories": "패션", "watches": "패션", "hats": "패션", "scarves": "패션", "belts": "패션",
            "남성의류": "패션", "여성의류": "패션", "신발": "패션", "가방": "패션", "악세사리": "패션",
            "시계": "패션", "모자": "패션", "스카프": "패션", "벨트": "패션", "백팩": "패션", "운동화": "패션",
            "스니커즈": "패션", "구두": "패션", "런닝화": "패션", "의류": "패션", "옷": "패션", "재킷": "패션", "jacket": "패션",
            "sneakers": "패션", "running shoes": "패션", "shoes": "패션", "bag": "패션",
            # 홈/리빙 (home_living)
            "furniture": "홈/리빙", "lighting": "홈/리빙", "kitchenware": "홈/리빙", "bedding": "홈/리빙",
            "storage": "홈/리빙", "cleaning_supplies": "홈/리빙", "candles": "홈/리빙", "rugs": "홈/리빙",
            "가구": "홈/리빙", "조명": "홈/리빙", "주방용품": "홈/리빙", "침구류": "홈/리빙", "수납용품": "홈/리빙",
            "청소용품": "홈/리빙", "캔들/방향제": "홈/리빙", "책상": "홈/리빙", "의자": "홈/리빙", "침대": "홈/리빙", "소파": "홈/리빙",
            "coffee maker": "홈/리빙", "coffee": "홈/리빙",
            # 뷰티/퍼스널케어 (beauty)
            "skincare": "뷰티/퍼스널케어", "haircare": "뷰티/퍼스널케어", "fragrance": "뷰티/퍼스널케어",
            "mens_grooming": "뷰티/퍼스널케어", "body_care": "뷰티/퍼스널케어", "makeup": "뷰티/퍼스널케어", "nail_care": "뷰티/퍼스널케어",
            "스킨케어": "뷰티/퍼스널케어", "헤어케어": "뷰티/퍼스널케어", "향수": "뷰티/퍼스널케어", "남성그루밍": "뷰티/퍼스널케어",
            "바디케어": "뷰티/퍼스널케어", "메이크업": "뷰티/퍼스널케어", "네일케어": "뷰티/퍼스널케어", "화장품": "뷰티/퍼스널케어",
            # 스포츠/아웃도어 (sports_outdoors)
            "fitness_equipment": "스포츠/아웃도어", "outdoor_gear": "스포츠/아웃도어", "cycling": "스포츠/아웃도어",
            "swimming": "스포츠/아웃도어", "yoga_pilates": "스포츠/아웃도어", "hiking": "스포츠/아웃도어", "team_sports": "스포츠/아웃도어",
            "운동기구": "스포츠/아웃도어", "아웃도어장비": "스포츠/아웃도어", "자전거용품": "스포츠/아웃도어", "수영용품": "스포츠/아웃도어",
            "요가/필라테스": "스포츠/아웃도어", "등산용품": "스포츠/아웃도어", "구기스포츠": "스포츠/아웃도어", "요가": "스포츠/아웃도어",
            "필라테스": "스포츠/아웃도어", "덤벨": "스포츠/아웃도어", "자전거": "스포츠/아웃도어",
            "yoga mat": "스포츠/아웃도어", "dumbbells": "스포츠/아웃도어", "fitness equipment": "스포츠/아웃도어", "fitness": "스포츠/아웃도어",
            # 식품 (food_grocery)
            "health_foods": "식품", "beverages": "식품", "snacks": "식품", "fresh_produce": "식품",
            "condiments": "식품", "supplements": "식품",
            "건강식품": "식품", "음료/차": "식품", "간식/과자": "식품", "신선식품": "식품", "조미료/소스": "식품",
            "영양제": "식품", "과자": "식품", "음료": "식품", "소스": "식품", "유산균": "식품", "비타민": "식품",
            # 유아/키즈 (baby_kids)
            "infant_products": "유아/키즈", "toys": "유아/키즈", "childrens_apparel": "유아/키즈",
            "school_supplies": "유아/키즈", "baby_care": "유아/키즈",
            "영유아용품": "유아/키즈", "완구/장난감": "유아/키즈", "아동의류": "유아/키즈", "학용품": "유아/키즈",
            "베이비케어": "유아/키즈", "장난감": "유아/키즈", "유아": "유아/키즈", "키즈": "유아/키즈",
            # 도서/미디어 (books_media)
            "books": "도서/미디어", "music": "도서/미디어", "film": "도서/미디어", "games": "도서/미디어",
            "stationery": "도서/미디어",
            "도서": "도서/미디어", "음반/음악": "도서/미디어", "영화/블루레이": "도서/미디어", "게임/콘솔": "도서/미디어",
            "문구류": "도서/미디어", "책": "도서/미디어", "음악": "도서/미디어", "게임": "도서/미디어", "book": "도서/미디어",
            # 자동차용품 (automotive)
            "car_accessories": "자동차용품", "car_care": "자동차용품", "dash_cameras": "자동차용품",
            "car_electronics": "자동차용품",
            "차량용액세서리": "자동차용품", "차량관리용품": "자동차용품", "블랙박스": "자동차용품", "차량용전자기기": "자동차용품",
            "블박": "자동차용품",
            # 반려동물용품 (pet_supplies)
            "dog_supplies": "반려동물용품", "cat_supplies": "반려동물용품", "pet_food": "반려동물용품",
            "treats": "반려동물용품", "pet_accessories": "반려동물용품", "pet_grooming": "반려동물용품",
            "강아지용품": "반려동물용품", "고양이용품": "반려동물용품", "반려동물사료": "반려동물용품", "반려동물간식": "반려동물용품",
            "반려동물액세서리": "반려동물용품", "반려동물미용": "반려동물용품", "사료": "반려동물용품", "간식": "반려동물용품",
            "강아지": "반려동물용품", "고양이": "반려동물용품", "pet food": "반려동물용품",
        }

        for kw, cat in SUB_TO_CAT.items():
            if kw in normalized_query:
                for pc in price_distributions:
                    if pc.lower() == cat.lower():
                        return pc

        # 3. Fallback to consumer historical top category
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
        3. utilitarian default for overloaded consumers.
        """
        if explicit_style is not None:
            return explicit_style, "explicit_user_input"

        top_style = preference_vector.get("top_style")
        if top_style in ("utilitarian", "hedonic"):
            return top_style, "top_style"

        return DEFAULT_STYLE, "overload_utilitarian_default"


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

