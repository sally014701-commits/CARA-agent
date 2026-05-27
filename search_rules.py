from __future__ import annotations

import re
from dataclasses import dataclass


SUBCATEGORY_MAP = {
    "스킨": "스킨", "토너": "스킨", "토닉": "스킨", "스킨케어": "스킨",
    "에센스": "스킨", "세럼": "스킨", "앰플": "스킨",
    "로션": "로션", "크림": "로션", "에멀전": "로션", "수분크림": "로션",
    "모이스처": "로션", "보습": "로션",
    "마스크팩": "마스크팩", "마스크": "마스크팩", "팩": "마스크팩",
    "시트마스크": "마스크팩", "수면팩": "마스크팩", "패치": "마스크팩",
    "립틴트": "립틴트", "틴트": "립틴트", "립": "립틴트",
    "립스틱": "립틴트", "립밤": "립틴트", "립글로스": "립틴트",
    "하이라이터": "하이라이터", "하이라이트": "하이라이터",
    "하이라이팅": "하이라이터", "글로우": "하이라이터", "광채": "하이라이터",
    "쿠션": "쿠션", "쿠션팩트": "쿠션", "팩트": "쿠션",
    "파운데이션": "파운데이션", "파운": "파운데이션",
    "베이스": "파운데이션", "비비": "파운데이션",
    "블러셔": "블러셔", "블러쉬": "블러셔", "볼터치": "블러셔",
    "치크": "블러셔", "홍조": "블러셔",
    "샴푸": "샴푸", "두피": "샴푸", "헤어": "샴푸",
    "탈모": "샴푸", "린스": "샴푸",
    "바디워시": "바디워시", "바디": "바디워시", "샤워젤": "바디워시",
    "바디클렌저": "바디워시", "바디로션": "바디워시",
}

SKIN_TYPE_MAP = {
    "건성": "dry", "건조": "dry", "dry": "dry",
    "지성": "oily", "유분": "oily", "oily": "oily",
    "복합성": "combo", "복합": "combo", "combo": "combo",
    "모든피부": "all", "모든 피부": "all", "전체피부": "all", "all": "all",
}

CLARIFICATION_PROMPT = "어떤 종류의 화장품을 찾으시나요?"


@dataclass(frozen=True)
class ParsedSearch:
    subcategory: str | None
    budget: int | None
    skin_type: str | None
    clarification_needed: bool


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def infer_subcategory(text: str) -> str | None:
    normalized = normalize_text(text)
    matches = [
        (keyword, subcategory)
        for keyword, subcategory in SUBCATEGORY_MAP.items()
        if normalize_text(keyword) in normalized
    ]
    if not matches:
        return None

    matches.sort(key=lambda item: len(normalize_text(item[0])), reverse=True)
    return matches[0][1]


def infer_skin_type(text: str) -> str | None:
    normalized = normalize_text(text)
    for keyword, skin_type in SKIN_TYPE_MAP.items():
        if normalize_text(keyword) in normalized:
            return skin_type
    return None


def parse_budget(text: str) -> int | None:
    normalized = (text or "").replace(",", "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(만원|만|원)?", normalized)
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2) or ""
    if unit in {"만원", "만"}:
        amount *= 10000

    return int(amount)


def has_upper_budget_marker(text: str) -> bool:
    normalized = normalize_text(text)
    return any(marker in normalized for marker in ("~이하", "이하", "미만"))


def parse_search(text: str) -> ParsedSearch:
    subcategory = infer_subcategory(text)
    return ParsedSearch(
        subcategory=subcategory,
        budget=parse_budget(text),
        skin_type=infer_skin_type(text),
        clarification_needed=bool((text or "").strip()) and subcategory is None,
    )


def clean_query_rule_based(query: str) -> str:
    return infer_subcategory(query) or ""
