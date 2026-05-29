from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Literal


PreferenceStyle = Literal["utilitarian", "hedonic"]

PREFERENCE_STYLE_MODEL = os.getenv(
    "PREFERENCE_STYLE_MODEL",
    "joeddav/xlm-roberta-large-xnli",
)
PREFERENCE_LABELS = ["기능성 실용적 제품", "감성적 디자인 제품"]
PREFERENCE_HYPOTHESIS_TEMPLATE = "이 사람은 {} 을 원한다."
PREFERENCE_CONFIDENCE_THRESHOLD = 0.6

UTILITARIAN_STYLE_TERMS = {
    "성분",
    "기능",
    "기능성",
    "효과",
    "효능",
    "보습",
    "보습력",
    "수분",
    "진정",
    "장벽",
    "저자극",
    "민감성",
    "건성",
    "지성",
    "복합성",
    "여드름",
    "트러블",
    "히알루론산",
    "세라마이드",
    "나이아신아마이드",
    "레티놀",
    "spf",
    "유분",
    "흡수",
    "지속력",
    "가성비",
    "저렴",
    "만원",
    "이하",
    "미만",
}

HEDONIC_STYLE_TERMS = {
    "예쁜",
    "예쁘",
    "감성",
    "디자인",
    "향",
    "향기",
    "향기로운",
    "무드",
    "고급스러운",
    "고급",
    "패키지",
    "패키징",
    "선물",
    "기분",
    "산뜻한 느낌",
    "촉감",
}

STRONG_HEDONIC_TERMS = {
    "예쁜",
    "예쁘",
    "감성",
    "디자인",
    "향기",
    "향기로운",
    "무드",
    "고급스러운",
    "패키지",
    "패키징",
    "선물",
}


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _matched_terms(text: str, terms: set[str]) -> list[str]:
    normalized = _normalized_text(text)
    return [term for term in terms if _normalized_text(term) in normalized]


def _rule_based_preference_style(user_message: str) -> dict[str, Any] | None:
    utilitarian_terms = _matched_terms(user_message, UTILITARIAN_STYLE_TERMS)
    hedonic_terms = _matched_terms(user_message, HEDONIC_STYLE_TERMS)
    strong_hedonic_terms = _matched_terms(user_message, STRONG_HEDONIC_TERMS)

    has_price_constraint = bool(
        re.search(r"\d+\s*(원|만원|천원|만|k|krw)?\s*(이하|미만|under|below)", user_message.lower())
    )
    has_skin_or_ingredient_need = any(
        term in utilitarian_terms
        for term in {
            "성분",
            "기능",
            "기능성",
            "효과",
            "효능",
            "보습",
            "보습력",
            "건성",
            "지성",
            "복합성",
            "민감성",
            "히알루론산",
            "세라마이드",
            "나이아신아마이드",
            "레티놀",
        }
    )

    if has_price_constraint or has_skin_or_ingredient_need:
        return {
            "style": "utilitarian",
            "source": "rule",
            "top_label": "기능성 실용적 제품",
            "top_score": 1.0,
            "matched_terms": {
                "utilitarian": utilitarian_terms,
                "hedonic": hedonic_terms,
            },
        }

    if strong_hedonic_terms and len(hedonic_terms) >= len(utilitarian_terms):
        return {
            "style": "hedonic",
            "source": "rule",
            "top_label": "감성적 디자인 제품",
            "top_score": 1.0,
            "matched_terms": {
                "utilitarian": utilitarian_terms,
                "hedonic": hedonic_terms,
            },
        }

    if len(utilitarian_terms) > len(hedonic_terms):
        return {
            "style": "utilitarian",
            "source": "rule",
            "top_label": "기능성 실용적 제품",
            "top_score": 1.0,
            "matched_terms": {
                "utilitarian": utilitarian_terms,
                "hedonic": hedonic_terms,
            },
        }

    if len(hedonic_terms) > len(utilitarian_terms):
        return {
            "style": "hedonic",
            "source": "rule",
            "top_label": "감성적 디자인 제품",
            "top_score": 1.0,
            "matched_terms": {
                "utilitarian": utilitarian_terms,
                "hedonic": hedonic_terms,
            },
        }

    return None


@lru_cache(maxsize=1)
def _preference_classifier() -> Any:
    from transformers import pipeline

    return pipeline(
        "zero-shot-classification",
        model=PREFERENCE_STYLE_MODEL,
    )


def classify_preference_style(user_message: str) -> dict[str, Any]:
    rule_result = _rule_based_preference_style(user_message)
    if rule_result is not None:
        return {
            **rule_result,
            "model": PREFERENCE_STYLE_MODEL,
            "raw": None,
        }

    result = _preference_classifier()(
        user_message,
        candidate_labels=PREFERENCE_LABELS,
        hypothesis_template=PREFERENCE_HYPOTHESIS_TEMPLATE,
    )
    top_label = result["labels"][0]
    top_score = float(result["scores"][0])
    style: PreferenceStyle

    if top_score < PREFERENCE_CONFIDENCE_THRESHOLD:
        style = "utilitarian"
    elif "감성" in top_label:
        style = "hedonic"
    else:
        style = "utilitarian"

    return {
        "style": style,
        "top_label": top_label,
        "top_score": top_score,
        "source": "zero_shot",
        "matched_terms": {
            "utilitarian": [],
            "hedonic": [],
        },
        "model": PREFERENCE_STYLE_MODEL,
        "raw": result,
    }


def detect_preference_style(user_message: str) -> PreferenceStyle:
    return classify_preference_style(user_message)["style"]


def main() -> None:
    cases = [
        ("예쁘고 감성적인 스킨케어 원해요", "hedonic"),
        ("성분 좋고 지성 피부에 효과적인 거", "utilitarian"),
        ("촉촉하고 향기로운 로션", "hedonic"),
        ("히알루론산 들어간 기능성 크림", "utilitarian"),
        ("스킨케어 추천해줘", "utilitarian"),
        ("촉촉한 건성을 위한 5만원 이하 스킨 찾아줘", "utilitarian"),
        ("선호 특성: 보습력 강한 제품", "utilitarian"),
    ]
    for message, expected in cases:
        detected = detect_preference_style(message)
        print(f"{message} -> {detected} (expected: {expected})")


if __name__ == "__main__":
    main()
