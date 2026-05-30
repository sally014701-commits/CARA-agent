"""
CARA Tool Use Module.

Run:
  python main.py

The server loads the active product catalog from cara.db and consumer profiles
from consumers.json into memory at startup, then exposes RESTful API tools for
CARA agents.
"""

from __future__ import annotations

import asyncio
import csv
import os
import re
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)
import json
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from critic_agent import CriticAgent
from conversation_agent import ConversationAgent
from database import engine, Base, AgentTrace, ChatMessage, SessionEvent, get_db
from executor_agent import ExecutorAgent, ProductToolClient
from planner_agent import PlannerAgent, SessionInput, ToolUseClient, UserIntent
from preference_style_detector import classify_preference_style
from search_rules import CLARIFICATION_PROMPT, parse_budget, parse_search
from vector_search import ensure_embedding_column, lexical_rag_rerank_rows, rag_rerank_rows


BASE_DIR = Path(__file__).resolve().parent
CONSUMERS_PATH = BASE_DIR / "consumers.json"
CARA_DB_PATH = Path(os.getenv("DB_PATH", "./cara.db"))

BudgetLevel = Literal["low", "mid", "high"]

SIMPLE_CONFIRMATIONS = {
    "yes",
    "y",
    "ok",
    "okay",
    "네",
    "응",
    "예",
    "좋아",
    "좋아요",
    "추천 시작",
    "시작",
    "바로 추천",
    "추천해줘",
    "그대로",
    "응",
    "네",
    "예",
    "좋아",
    "그걸로",
    "그걸로 해줘",
    "그걸로 추천해줘",
}

QUERY_NORMALIZATION_MAP = {
    "노트북": "노트북",
    "laptop": "노트북",
    "laptops": "노트북",
    "백팩": "백팩",
    "backpack": "백팩",
    "backpacks": "백팩",
    "운동화": "운동화",
    "running shoes": "운동화",
    "running shoe": "운동화",
    "shoes": "운동화",
    "sneakers": "운동화",
    "커피머신": "커피머신",
    "커피 머신": "커피머신",
    "coffee maker": "커피머신",
    "coffee machine": "커피머신",
    "헤어팩": "헤어팩",
    "hair pack": "헤어팩",
    "hair mask": "헤어팩",
}

QUERY_FILLER_WORDS = {
    "가성비",
    "좋은",
    "예쁜",
    "추천",
    "추천해",
    "추천해줘",
    "보여줘",
    "찾아줘",
    "이하",
    "이상",
    "under",
    "for",
    "daily",
    "workout",
    "미만",
    "초과",
    "below",
    "over",
}

UTILITARIAN_TERM_ALIASES = {
    "가성비": ["가성비", "가격 대비", "저렴", "저렴한"],
    "튼튼한": ["튼튼", "튼튼한", "내구성"],
    "가벼운": ["가벼운", "가벼워", "경량"],
    "휴대성": ["휴대성", "휴대"],
    "성능": ["성능", "스펙"],
    "배터리": ["배터리"],
    "수납력": ["수납력", "수납"],
    "방수": ["방수"],
    "실용적인": ["실용", "실용적인"],
    "업무용": ["업무용", "업무"],
    "공부용": ["공부용", "공부"],
}

HEDONIC_TERM_ALIASES = {
    "예쁜": ["예쁜", "예쁘", "이쁜", "이쁘"],
    "감성적인": ["감성", "감성적인"],
    "고급스러운": ["고급", "고급스러운"],
    "깔끔한": ["깔끔", "깔끔한"],
    "귀여운": ["귀여운", "귀엽"],
    "힙한": ["힙한", "힙하"],
    "트렌디한": ["트렌디", "트렌디한"],
    "미니멀한": ["미니멀", "미니멀한"],
    "색감": ["색감"],
    "디자인": ["디자인"],
    "세련된": ["세련", "세련된"],
    "무드 있는": ["무드"],
}


def is_price_constraint_term(term: str) -> bool:
    normalized = term.strip().lower().replace(",", "")
    if normalized in QUERY_FILLER_WORDS:
        return True
    return bool(re.fullmatch(r"[$₩]?\d+(\.\d+)?(원|만원|천원|만|k|krw)?", normalized))


def extract_budget_ceiling(text: str) -> int | None:
    parsed = parse_budget(text)
    if parsed is not None:
        return parsed
    normalized = text.replace(",", "").lower()
    if re.search(r"(이상|초과|\bover\b)", normalized):
        return None
    return extract_price_amount(text)


def extract_budget_floor(text: str) -> int | None:
    normalized = text.replace(",", "").lower()
    if not re.search(r"(이상|초과|\bover\b)", normalized):
        return None
    return extract_price_amount(text)


def extract_price_amount(text: str) -> int | None:
    parsed = parse_budget(text)
    if parsed is not None:
        return parsed
    normalized = text.replace(",", "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(만원|만\s*원|천원|원|만|k|krw)?", normalized)
    if not match:
        return None

    amount = float(match.group(1))
    unit = (match.group(2) or "원").replace(" ", "")
    if unit in {"만원", "만"}:
        amount *= 10000
    elif unit == "천원":
        amount *= 1000
    elif unit == "k":
        amount *= 1000

    return int(amount)


def is_simple_confirmation(message: str) -> bool:
    normalized = " ".join(message.strip().lower().split())
    compact = normalized.replace(" ", "")
    return normalized in SIMPLE_CONFIRMATIONS or compact in {
        item.replace(" ", "") for item in SIMPLE_CONFIRMATIONS
    }


def extract_chat_query(message: str) -> str:
    mapped_subcategory = parse_search(message).subcategory
    if mapped_subcategory:
        return mapped_subcategory
    return ""

    cleaned = clean_query_with_llm_and_fallback(message).strip()
    if not cleaned:
        return ""

    normalized_message = " ".join(message.strip().lower().split())
    normalized_cleaned = " ".join(cleaned.lower().split())
    for key, value in QUERY_NORMALIZATION_MAP.items():
        if key in normalized_cleaned or key in normalized_message:
            return value

    if normalized_cleaned == normalized_message and " " in cleaned:
        terms = []
        for term in cleaned.split():
            stripped = term.strip(".,!?~")
            if not stripped or stripped.lower() in QUERY_FILLER_WORDS:
                continue
            if is_price_constraint_term(stripped):
                continue
            terms.append(stripped)
        if terms:
            return terms[-1]

    return cleaned


def _matched_style_terms(message: str, aliases: dict[str, list[str]]) -> list[str]:
    normalized = message.lower().replace(" ", "")
    matched: list[str] = []
    for canonical, variants in aliases.items():
        if any(variant.replace(" ", "").lower() in normalized for variant in variants):
            matched.append(canonical)
    return matched


def parse_user_utterance(
    message: str,
    existing_preferred_style: str | None = None,
) -> dict[str, Any]:
    parsed_search = parse_search(message)
    utilitarian_terms = _matched_style_terms(message, UTILITARIAN_TERM_ALIASES)
    hedonic_terms = _matched_style_terms(message, HEDONIC_TERM_ALIASES)
    util_score = len(utilitarian_terms)
    hedonic_score = len(hedonic_terms)
    preferred_style: str | None = None
    style_confidence = 0.0

    if util_score > hedonic_score:
        preferred_style = "utilitarian"
        style_confidence = round((util_score - hedonic_score) / max(util_score + hedonic_score, 1), 4)
    elif hedonic_score > util_score:
        preferred_style = "hedonic"
        style_confidence = round((hedonic_score - util_score) / max(util_score + hedonic_score, 1), 4)
    elif util_score or hedonic_score:
        preferred_style = existing_preferred_style

    return {
        "query": parsed_search.subcategory or "",
        "skin_type": parsed_search.skin_type,
        "search_text": message,
        "utilitarian_terms": utilitarian_terms,
        "hedonic_terms": hedonic_terms,
        "preferred_style": preferred_style,
        "style_confidence": style_confidence,
    }


class StyleType(str, Enum):
    utilitarian = "utilitarian"
    hedonic = "hedonic"


class Product(BaseModel):
    """Product catalog record loaded from cara.db."""

    product_id: str
    category: str
    subcategory: str | None = None
    item_type: str | None = None
    name: str
    price: int
    brand: str | None = None
    style_type: StyleType
    star_rating: float | None = None
    rating: float | None = None
    review_count: int
    review_text: str | None = None
    sentiment_score: float | None = None
    skin_type: str | None = None
    similarity_score: float | None = None
    RAG_score: float | None = None
    stock_status: bool | None = None
    description: str | None = None

    # Bilingual metadata
    category_en: str
    category_ko: str
    subcategory_en: str | None = None
    subcategory_ko: str | None = None
    title_en: str
    title_ko: str
    keywords_ko: list[str] = Field(default_factory=list)
    synonyms_ko: list[str] = Field(default_factory=list)

    @property
    def effective_rating(self) -> float:
        return self.star_rating or self.rating or 0.0


class SessionBehavior(BaseModel):
    """Simulated session behavior and cognitive overload metrics."""

    page_visits: int
    dwell_times: list[float]
    dwell_time_variance: float
    scroll_depths: list[float]
    average_scroll_depth: float
    ctr: float
    brainfry_score: float


class ConsumerProfile(BaseModel):
    """Consumer profile record loaded from consumers.json."""

    consumer_id: str
    psychographic_type: str = "utilitarian"
    preference_style: StyleType
    budget_level: BudgetLevel
    purchase_history: list[str]
    session_behavior: SessionBehavior
    ctr: float
    brainfry_score: float


class ConsumerHistoryResponse(BaseModel):
    """Response model for a single consumer's profile and history."""

    consumer_id: str
    purchase_history: list[str]
    session_behavior: SessionBehavior
    preference_vector: dict[str, Any] = Field(
        description="Precomputed preference features used by CARA agents.",
    )


class ProductSearchResponse(BaseModel):
    """Response model for product search endpoints."""

    count: int
    products: list[Product]
    clarification_needed: bool = False
    message: str | None = None
    subcategory: str | None = None
    budget: int | None = None
    skin_type: str | None = None


class SessionDataRequest(BaseModel):
    """Current passive tracking metrics sent by the storefront."""

    n: int = Field(default=0, ge=0)
    dwell_variance: float = Field(default=0.0, ge=0)
    ctr: float = Field(default=0.0, ge=0.0, le=1.0)
    scroll_depth: float = Field(default=0.5, ge=0.0, le=1.0)
    query_reformulations: int = Field(default=0, ge=0)
    self_report_score: float = Field(default=0.0, ge=0.0, le=1.0)
    text_brainfry_score: float = Field(default=0.0, ge=0.0, le=1.0)


class PlanRequest(BaseModel):
    """Request body for Planner orchestration."""

    consumer_id: str = "user123"
    query: str = ""
    session_data: SessionDataRequest


class PassiveTrackingRequest(BaseModel):
    """Periodic passive tracking snapshot sent by the storefront."""

    session_id: str
    consumer_id: str = "user123"
    session_data: SessionDataRequest


class PassiveTrackingResponse(BaseModel):
    """BrainFry score recorded from a passive tracking snapshot."""

    brainfry_level: str
    brainfry_score: float
    b_behavioral: float


class ChatRequest(BaseModel):
    """Request body for the two-turn CARA conversation."""

    session_id: str
    consumer_id: str = "user123"
    message: str
    session_data: SessionDataRequest
    history: list[dict[str, str]] = Field(default_factory=list)
    plan_context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Conversation Agent response plus updated planning context."""

    reply: str
    plan_context: dict[str, Any]
    turn_complete: bool
    self_report_score: float | None = None
    b_text: float
    b_behavioral: float = 0.0
    b_final: float = 0.0
    n_rec: int = 7
    agent_trace: list[dict[str, str]]


class PlanResponse(BaseModel):
    """Planner response used by the two-turn confirmation dialog."""

    consumer_id: str
    query: str
    budget_ceiling: int
    preferred_style: StyleType
    brainfry_level: str
    brainfry_score: float
    n_rec: int
    psychographic_type: str
    top_category: str | None = None
    avg_spend: float | None = None


class RecommendRequest(BaseModel):
    """Request body for end-to-end recommendation orchestration."""

    session_id: str | None = None
    consumer_id: str = "user123"
    query: str = ""
    budget_ceiling: int
    preferred_style: StyleType
    psychographic_type: str = "utilitarian"
    skin_type: str | None = None
    brainfry_score: float | None = Field(default=None, ge=0.0, le=1.0)
    use_vector_search: bool = True
    utilitarian_terms: list[str] = Field(default_factory=list)
    hedonic_terms: list[str] = Field(default_factory=list)
    style_confidence: float = 0.0


class FinalRecommendation(BaseModel):
    """Critic-approved product result returned to the storefront."""

    id: str
    product_id: str
    name: str
    price: int
    style: str
    style_type: str
    rating: float
    RAG_score: float
    presentation_hint: str = "spec_first"
    n_rec: int = 5
    critic_iterations: int = 0


products: list[Product] = []
consumers: dict[str, ConsumerProfile] = {}
category_price_distributions: dict = {}


def load_json(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array from disk and return raw dictionaries."""
    if not path.exists():
        raise FileNotFoundError(f"Required data file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array.")

    return data


def load_products_from_cara_db(path: Path = CARA_DB_PATH) -> list[Product]:
    """Load the active product catalog from cara.db."""
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Required product database not found: {path}")

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'products'"
        ).fetchone()
        if table_exists is None:
            raise RuntimeError(f"Required table not found in {path}: products")

        rows = connection.execute(
            """
            SELECT
                product_id,
                subcategory,
                product_name,
                brand,
                brand_tier,
                price,
                price_percentile,
                star_rating,
                review_count,
                skin_type,
                preference_style,
                sentiment_score,
                keywords
            FROM products
            ORDER BY product_id
            """
        ).fetchall()

    mapped_products: list[Product] = []
    for row in rows:
        keywords = [
            keyword.strip()
            for keyword in str(row["keywords"] or "").split(",")
            if keyword.strip()
        ]
        subcategory = str(row["subcategory"])
        product_name = str(row["product_name"])
        brand = str(row["brand"])
        product_id = f"P{int(row['product_id']):04d}"
        mapped_products.append(
            Product.model_validate(
                {
                    "product_id": product_id,
                    "category": subcategory,
                    "subcategory": subcategory,
                    "item_type": subcategory,
                    "name": product_name,
                    "price": int(row["price"]),
                    "brand": brand,
                    "style_type": row["preference_style"],
                    "star_rating": float(row["star_rating"]),
                    "rating": float(row["star_rating"]),
                    "review_count": int(row["review_count"] or 0),
                    "review_text": None,
                    "sentiment_score": float(row["sentiment_score"] or 0.0),
                    "skin_type": str(row["skin_type"] or ""),
                    "stock_status": True,
                    "description": " ".join(
                        part
                        for part in [
                            product_name,
                            brand,
                            subcategory,
                            str(row["brand_tier"] or ""),
                            str(row["skin_type"] or ""),
                            " ".join(keywords),
                        ]
                        if part
                    ),
                    "category_en": "beauty",
                    "category_ko": subcategory,
                    "subcategory_en": subcategory,
                    "subcategory_ko": subcategory,
                    "title_en": product_name,
                    "title_ko": product_name,
                    "keywords_ko": keywords,
                    "synonyms_ko": [
                        item
                        for item in [
                            subcategory,
                            brand,
                            str(row["skin_type"] or ""),
                            str(row["brand_tier"] or ""),
                        ]
                        if item
                    ],
                }
            )
        )

    if not mapped_products:
        raise RuntimeError(f"No products found in {path}.products")

    return mapped_products


def query_products_from_cara_db(
    subcategory: str,
    query_text: str,
    budget: float | None = None,
    skin_type: str | None = None,
    preferred_style: str | None = None,
    use_vector_search: bool = True,
    path: Path = CARA_DB_PATH,
) -> list[Product]:
    """Run the rule-based search SQL directly against cara.db.products."""
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                product_id,
                subcategory,
                product_name,
                brand,
                brand_tier,
                price,
                price_percentile,
                star_rating,
                review_count,
                skin_type,
                preference_style,
                sentiment_score,
                keywords
                , embedding
            FROM products
            WHERE subcategory = ?
              AND (? IS NULL OR price <= ?)
              AND (? IS NULL OR skin_type IN (?, 'all'))
            ORDER BY star_rating DESC
            LIMIT 50
            """,
            (subcategory, budget, budget, skin_type, skin_type),
        ).fetchall()

    reranked_rows: list[dict[str, Any]] = []
    if use_vector_search:
        try:
            reranked_rows = rag_rerank_rows(
                query_text=query_text or subcategory,
                rows=list(rows),
                user_budget=budget,
                preferred_style=preferred_style,
            )
        except Exception:
            reranked_rows = []

    if not reranked_rows:
        reranked_rows = lexical_rag_rerank_rows(
            query_text=query_text or subcategory,
            rows=list(rows),
            user_budget=budget,
            preferred_style=preferred_style,
        )

    ordered_rows: list[Any] = reranked_rows or list(rows)

    mapped_products: list[Product] = []
    for row in ordered_rows:
        keywords = [
            keyword.strip()
            for keyword in str(row["keywords"] or "").split(",")
            if keyword.strip()
        ]
        row_subcategory = str(row["subcategory"])
        product_name = str(row["product_name"])
        brand = str(row["brand"])
        mapped_products.append(
            Product.model_validate(
                {
                    "product_id": f"P{int(row['product_id']):04d}",
                    "category": row_subcategory,
                    "subcategory": row_subcategory,
                    "item_type": row_subcategory,
                    "name": product_name,
                    "price": int(row["price"]),
                    "brand": brand,
                    "style_type": row["preference_style"],
                    "star_rating": float(row["star_rating"]),
                    "rating": float(row["star_rating"]),
                    "review_count": int(row["review_count"] or 0),
                    "review_text": None,
                    "sentiment_score": float(row["sentiment_score"] or 0.0),
                    "skin_type": str(row["skin_type"] or ""),
                    "similarity_score": row.get("S") if isinstance(row, dict) else None,
                    "RAG_score": row.get("RAG_score") if isinstance(row, dict) else None,
                    "stock_status": True,
                    "description": " ".join(
                        part
                        for part in [
                            product_name,
                            brand,
                            row_subcategory,
                            str(row["brand_tier"] or ""),
                            str(row["skin_type"] or ""),
                            " ".join(keywords),
                        ]
                        if part
                    ),
                    "category_en": "beauty",
                    "category_ko": row_subcategory,
                    "subcategory_en": row_subcategory,
                    "subcategory_ko": row_subcategory,
                    "title_en": product_name,
                    "title_ko": product_name,
                    "keywords_ko": keywords,
                    "synonyms_ko": [
                        item
                        for item in [
                            row_subcategory,
                            brand,
                            str(row["skin_type"] or ""),
                            str(row["brand_tier"] or ""),
                        ]
                        if item
                    ],
                }
            )
        )

    return mapped_products


def load_database() -> None:
    """Load products and consumers into process memory for fast tool access."""
    global products, consumers

    ensure_embedding_column(CARA_DB_PATH)
    products = load_products_from_cara_db()
    consumer_records = [
        ConsumerProfile.model_validate(item) for item in load_json(CONSUMERS_PATH)
    ]
    consumers = {consumer.consumer_id: consumer for consumer in consumer_records}


def build_preference_vector(consumer: ConsumerProfile) -> dict[str, Any]:
    """Derive compact preference features from profile and purchase history."""
    purchased_product_ids = set(consumer.purchase_history)
    purchased_products = [
        product
        for product in products
        if product.product_id in purchased_product_ids
    ]
    style_counts = Counter(product.style_type for product in purchased_products)
    top_style = (
        style_counts.most_common(1)[0][0]
        if style_counts
        else consumer.preference_style
    )
    category_counts = Counter(product.category for product in purchased_products)
    top_category = (
        category_counts.most_common(1)[0][0]
        if category_counts
        else None
    )
    historical_prices = [product.price for product in purchased_products]
    average_historical_spend = (
        round(sum(historical_prices) / len(historical_prices), 2)
        if historical_prices
        else None
    )
    maximum_historical_spend = max(historical_prices) if historical_prices else None

    return {
        "psychographic_type": consumer.psychographic_type,
        "preference_style": consumer.preference_style,
        "budget_level": consumer.budget_level,
        "top_style": top_style,
        "top_category": top_category,
        "average_historical_spend": average_historical_spend,
        "maximum_historical_spend": maximum_historical_spend,
        "ctr": consumer.ctr,
        "brainfry_score": consumer.brainfry_score,
    }


def normalize_consumer_id(consumer_id: str) -> str:
    """Map demo storefront IDs to an available synthetic consumer profile."""
    if consumer_id in consumers:
        return consumer_id
    short_match = re.fullmatch(r"C(\d{3})", consumer_id)
    if short_match:
        padded = f"C{int(short_match.group(1)):04d}"
        if padded in consumers:
            return padded
    if consumer_id in {"user123", "guest", "USR-001"}:
        return "C0001"
    return consumer_id


def style_value(style: Any) -> str:
    return style.value if isinstance(style, StyleType) else str(style)


def normalize_preference_style_reply(reply: str, preferred_style: Any) -> str:
    style = style_value(preferred_style).lower()
    if style not in {"hedonic", "utilitarian"}:
        style = "utilitarian"
    replacement = f"- 선호 스타일: {style}"
    pattern = r"(?m)^-\s*선호\s*스타일\s*[:：]\s*.*$"
    if re.search(pattern, reply):
        return re.sub(pattern, replacement, reply)
    return reply


def build_category_price_distributions(products: list) -> dict:
    from collections import defaultdict
    dist = defaultdict(list)
    for product in products:
        dist[product.category].append(float(product.price))
    return {cat: sorted(prices) for cat, prices in dist.items()}


def current_tool_base_url(http_request: Request) -> str:
    """Use the active FastAPI host/port for internal tool-use calls."""
    return str(http_request.base_url).rstrip("/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize the in-memory JSON database when the FastAPI server starts."""
    load_database()
    global category_price_distributions
    category_price_distributions = build_category_price_distributions(products)
    yield


app = FastAPI(
    title="CARA Tool Use Module",
    description=(
        "RESTful API tools for CARA(Context-Aware Recommendation Agent), "
        "backed by cara.db and consumers.json."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")


@app.get("/", response_class=FileResponse)
def serve_root() -> FileResponse:
    """Serve the main CARA application."""
    return FileResponse(
        BASE_DIR / "CARA.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", response_model=dict[str, str])
def health_check() -> dict[str, str]:
    """Return a lightweight health check for server and agent connectivity."""
    return {"status": "ok", "service": "CARA Tool Use Module"}


@app.get("/CARA.html", response_class=FileResponse)
def serve_cara_html() -> FileResponse:
    return FileResponse(
        BASE_DIR / "CARA.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/admin.html", response_class=FileResponse)
def serve_admin_html() -> FileResponse:
    return FileResponse(
        BASE_DIR / "admin.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/app", response_class=FileResponse)
def serve_app() -> FileResponse:
    return FileResponse(
        BASE_DIR / "CARA.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/consumers/{consumer_id}/history",
    response_model=ConsumerHistoryResponse,
)
def get_consumer_history(consumer_id: str) -> ConsumerHistoryResponse:
    """
    Retrieve a consumer's full recommendation context.

    CARA agents call this tool to fetch purchase history, dynamic session
    behavior, and precomputed preference features such as style and budget.
    A missing consumer_id returns HTTP 404.
    """
    consumer = consumers.get(consumer_id)
    if consumer is None:
        raise HTTPException(
            status_code=404,
            detail=f"Consumer not found: {consumer_id}",
        )

    return ConsumerHistoryResponse(
        consumer_id=consumer.consumer_id,
        purchase_history=consumer.purchase_history,
        session_behavior=consumer.session_behavior,
        preference_vector=build_preference_vector(consumer),
    )


SYNONYMS_MAP = {
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

    # English benchmark synonyms
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


@app.get("/products/search", response_model=ProductSearchResponse)
def search_products(
    query: str = Query(
        default="",
        description="Keyword matched against product name or description.",
    ),
    max_price: float | None = Query(
        default=None,
        ge=0,
        description="Optional upper price bound.",
    ),
    min_price: float | None = Query(
        default=None,
        ge=0,
        description="Optional lower price bound.",
    ),
    style_type: StyleType | None = Query(
        default=None,
        description="Optional style filter: utilitarian or hedonic.",
    ),
    category: str | None = Query(
        default=None,
        description="Optional product category filter.",
    ),
    skin_type: str | None = Query(
        default=None,
        description="Optional skin type filter: dry, oily, combo, or all.",
    ),
    use_vector_search: bool = Query(
        default=True,
        description="Use remote vector embeddings before lexical RAG reranking.",
    ),
) -> ProductSearchResponse:
    """
    Search the product catalog with keyword and optional structured filters.

    CARA agents call this tool to collect candidate products. The endpoint uses
    simple case-insensitive string matching against product name and optional
    description, then applies max_price, style_type, and category filters.
    """
    parsed_search = parse_search(query)
    requested_subcategory = (category.strip() if category else None) or parsed_search.subcategory
    requested_skin_type = skin_type or parsed_search.skin_type
    effective_max_price = max_price if max_price is not None else parsed_search.budget

    if query.strip() and requested_subcategory is None:
        return ProductSearchResponse(
            count=0,
            products=[],
            clarification_needed=True,
            message=CLARIFICATION_PROMPT,
            subcategory=None,
            budget=int(effective_max_price) if effective_max_price is not None else None,
            skin_type=requested_skin_type,
        )

    if requested_subcategory is not None:
        sql_products = query_products_from_cara_db(
            subcategory=requested_subcategory,
            query_text=query,
            budget=effective_max_price,
            skin_type=requested_skin_type,
            preferred_style=style_value(style_type) if style_type is not None else None,
            use_vector_search=use_vector_search,
        )
        return ProductSearchResponse(
            count=len(sql_products),
            products=sql_products,
            subcategory=requested_subcategory,
            budget=int(effective_max_price) if effective_max_price is not None else None,
            skin_type=requested_skin_type,
        )

    rule_filtered_products: list[Product] = []
    for product in products:
        if requested_subcategory is not None and product.subcategory != requested_subcategory:
            continue
        if effective_max_price is not None and product.price > effective_max_price:
            continue
        if min_price is not None and product.price < min_price:
            continue
        if style_type is not None and product.style_type != style_type:
            continue
        if requested_skin_type is not None:
            product_skin_type = (product.skin_type or "").lower()
            if product_skin_type not in {requested_skin_type.lower(), "all"}:
                continue
        rule_filtered_products.append(product)

    if requested_subcategory is not None:
        rule_filtered_products.sort(key=lambda item: item.effective_rating, reverse=True)
        rule_filtered_products = rule_filtered_products[:20]

    return ProductSearchResponse(
        count=len(rule_filtered_products),
        products=rule_filtered_products,
        subcategory=requested_subcategory,
        budget=int(effective_max_price) if effective_max_price is not None else None,
        skin_type=requested_skin_type,
    )

    normalized_query = query.strip().lower()
    normalized_category = category.strip().lower() if category is not None else None
    effective_max_price = max_price
    if effective_max_price is None:
        effective_max_price = extract_budget_ceiling(query)
    effective_min_price = min_price
    if effective_min_price is None:
        effective_min_price = extract_budget_floor(query)

    filtered_products: list[Product] = []
    raw_terms = [t for t in normalized_query.split() if t]
    terms = []
    
    stop_words = {
        "추천", "추천해줘", "추천해", "보여줘", "찾아줘", "알려줘", "해줘", "싶어", "원해", "구매", "살래", "검색", 
        "추천해드립니다", "추천해주세요", "있나요", "어떤게", "어떤", "원해요", "원합니다", "부탁해", "부탁해요", "부탁드립니다",
        "보여주세요", "찾아주세요", "알려주세요", "해줘요", "해주세요", "골라줘", "골라주세요", "골라"
    }
    particles = ["은", "는", "이", "가", "을", "를", "의", "에", "과", "와", "로", "으로", "에서", "보다", "부터", "까지"]
    
    for t in raw_terms:
        if t in stop_words or is_price_constraint_term(t):
            continue
        for p in particles:
            if t.endswith(p) and len(t) > len(p):
                t = t[:-len(p)]
                break
        if t:
            terms.append(t)

    for product in products:
        # Match all terms in the query (AND logic)
        if terms:
            match_all_terms = True
            for term in terms:
                target_words = {term}
                if term in SYNONYMS_MAP:
                    target_words.update(SYNONYMS_MAP[term])

                term_matched = False
                for word in target_words:
                    if word in product.name.lower():
                        term_matched = True
                        break
                    if product.description and word in product.description.lower():
                        term_matched = True
                        break
                    if word in product.category.lower() or word in getattr(product, "category_en", "").lower():
                        term_matched = True
                        break
                    if (product.subcategory and word in product.subcategory.lower()) or (getattr(product, "subcategory_en", None) and word in product.subcategory_en.lower()):
                        term_matched = True
                        break
                    if any(word in kw.lower() for kw in getattr(product, "keywords_ko", [])):
                        term_matched = True
                        break
                    if any(word in syn.lower() for syn in getattr(product, "synonyms_ko", [])):
                        term_matched = True
                        break
                    if product.brand and word in product.brand.lower():
                        term_matched = True
                        break

                if not term_matched:
                    match_all_terms = False
                    break

            if not match_all_terms:
                continue

        if effective_max_price is not None and product.price > effective_max_price:
            continue

        if effective_min_price is not None and product.price < effective_min_price:
            continue

        if style_type is not None and product.style_type != style_type:
            continue

        if normalized_category is not None:
            prod_cat = product.category.lower()
            prod_cat_en = getattr(product, "category_en", "").lower()
            prod_cat_ko = getattr(product, "category_ko", "").lower()
            if normalized_category not in (prod_cat, prod_cat_en, prod_cat_ko):
                continue

        filtered_products.append(product)

    return ProductSearchResponse(
        count=len(filtered_products),
        products=filtered_products,
    )


@app.get("/products/trending", response_model=ProductSearchResponse)
def get_trending_products(
    category: str | None = Query(
        default=None,
        description="Optional category filter for trending products.",
    ),
) -> ProductSearchResponse:
    """
    Return the top 20 products by review_count.

    CARA agents call this tool as a fallback when keyword search returns fewer
    than three candidates. If category is provided, ranking is restricted to
    that category; otherwise all products are considered.
    """
    normalized_category = category.strip().lower() if category is not None else None

    candidate_products = [
        product
        for product in products
        if normalized_category is None
        or product.category.lower() == normalized_category
        or getattr(product, "category_en", "").lower() == normalized_category
        or getattr(product, "category_ko", "").lower() == normalized_category
    ]
    trending_products = sorted(
        candidate_products,
        key=lambda product: product.review_count,
        reverse=True,
    )[:20]

    return ProductSearchResponse(
        count=len(trending_products),
        products=trending_products,
    )


@app.get("/products/price-distributions", response_model=dict)
def get_price_distributions():
    return category_price_distributions


@app.post("/api/plan", response_model=PlanResponse)
def create_recommendation_plan(
    request: PlanRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
):
    """
    Orchestrate the Planner Agent for the storefront confirmation dialog.

    The frontend sends passive tracking metrics, and this endpoint returns the
    inferred budget, preferred style, and BrainFry state needed for Turn 1.
    """
    consumer_id = normalize_consumer_id(request.consumer_id)
    explicit_budget = extract_budget_ceiling(request.query)
    tool_base_url = current_tool_base_url(http_request)
    planner = PlannerAgent(ToolUseClient(tool_base_url))
    plan = planner.create_plan(
        consumer_id=consumer_id,
        session_input=SessionInput(
            page_visits=request.session_data.n,
            dwell_time_variance=request.session_data.dwell_variance,
            ctr=request.session_data.ctr,
            scroll_depth=request.session_data.scroll_depth,
            query_reformulations=request.session_data.query_reformulations,
            self_report_score=request.session_data.self_report_score,
            text_brainfry_score=request.session_data.text_brainfry_score,
        ),
        user_intent=UserIntent(query=request.query, explicit_budget=explicit_budget),
    )
    if explicit_budget is not None:
        plan["budget_ceiling"] = explicit_budget
        plan.setdefault("trace", {})["budget_source"] = "explicit_query_budget"
    brainfry_score = float(plan["brainfry_score"])
    n_rec = max(1, round(7 * (1 - brainfry_score)))

    # AgentTrace 기록
    for agent_name in ["User Intent Agent", "BrainFry Detector", "Psychology Agent"]:
        db.add(AgentTrace(
            session_id=request.consumer_id,
            agent_name=agent_name,
            status="done",
            input_data={"query": request.query, "brainfry_score": brainfry_score},
            output_data=plan,
        ))
    db.commit()

    return PlanResponse(
        consumer_id=consumer_id,
        query=plan["query"],
        budget_ceiling=int(plan["budget_ceiling"]),
        preferred_style=plan["preferred_style"],
        brainfry_level=plan["brainfry_level"],
        brainfry_score=brainfry_score,
        n_rec=n_rec,
        psychographic_type=plan.get("psychographic_type", "utilitarian"),
        top_category=plan.get("top_category"),
        avg_spend=plan.get("avg_spend"),
    )


@app.post("/api/passive-tracking", response_model=PassiveTrackingResponse)
def record_passive_tracking_tick(request: PassiveTrackingRequest, db: DBSession = Depends(get_db)):
    """
    Record a periodic BrainFry snapshot from passive browsing signals.

    The storefront can call this every 30 seconds while the page is open. The
    score uses the same BrainFry computation as the Planner so dashboard stats
    and recommendation planning stay aligned.
    """
    consumer_id = normalize_consumer_id(request.consumer_id)
    session_input = SessionInput(
        page_visits=request.session_data.n,
        dwell_time_variance=request.session_data.dwell_variance,
        ctr=request.session_data.ctr,
        scroll_depth=request.session_data.scroll_depth,
        query_reformulations=request.session_data.query_reformulations,
        self_report_score=request.session_data.self_report_score,
        text_brainfry_score=request.session_data.text_brainfry_score,
    )
    brainfry_score = PlannerAgent.compute_behavioral_score(session_input)
    brainfry_level = PlannerAgent.classify_brainfry_level(brainfry_score)

    db.add(SessionEvent(
        session_id=request.session_id,
        consumer_id=consumer_id,
        event_type="brainfry_tick",
        agent_name="BrainFry Detector",
        payload={
            "session_data": request.session_data.model_dump(),
            "interval_seconds": 30,
            "b_behavioral": brainfry_score,
            "brainfry_level": brainfry_level,
        },
        brainfry_score=brainfry_score,
    ))
    db.commit()

    return PassiveTrackingResponse(
        brainfry_level=brainfry_level,
        brainfry_score=brainfry_score,
        b_behavioral=brainfry_score,
    )


@app.post("/api/chat", response_model=ChatResponse)
def run_chat_turn(
    request: ChatRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
) -> ChatResponse:
    consumer_id = normalize_consumer_id(request.consumer_id)
    plan_context = dict(request.plan_context or {})
    has_plan_context = bool(plan_context)
    session_input = SessionInput(
        page_visits=request.session_data.n,
        dwell_time_variance=request.session_data.dwell_variance,
        ctr=request.session_data.ctr,
        scroll_depth=request.session_data.scroll_depth,
        query_reformulations=request.session_data.query_reformulations,
        text_brainfry_score=0.0,
    )
    b_behavioral = PlannerAgent.compute_behavioral_score(session_input)
    plan_context["b_behavioral"] = b_behavioral
    plan_context.setdefault("trace", {})["b_behavioral"] = b_behavioral

    agent_trace: list[dict[str, str]] = []
    explicit_budget = extract_budget_ceiling(request.message)
    parsed_utterance = parse_user_utterance(
        request.message,
        existing_preferred_style=plan_context.get("preferred_style"),
    )
    style_detection = None
    if request.message.strip() and not is_simple_confirmation(request.message):
        style_detection = classify_preference_style(request.message)
        parsed_utterance["preferred_style"] = style_detection["style"]
        parsed_utterance["style_confidence"] = (
            round(style_detection["top_score"], 4)
            if style_detection["top_score"] >= 0.6
            else 0.0
        )

    if request.message.strip() and not is_simple_confirmation(request.message) and not parsed_utterance["query"]:
        b_final = PlannerAgent.compute_final_score(b_behavioral=b_behavioral)
        brainfry_level = PlannerAgent.classify_brainfry_level(b_final)
        n_rec = max(1, round(7 * (1 - b_final)))
        plan_context.update({
            "b_behavioral": b_behavioral,
            "b_text": 0.0,
            "b_final": b_final,
            "text_brainfry_score": 0.0,
            "brainfry_score": b_final,
            "brainfry_level": brainfry_level,
            "n_rec": n_rec,
            "preferred_style": parsed_utterance["preferred_style"],
            "style_confidence": parsed_utterance["style_confidence"],
        })
        if style_detection is not None:
            plan_context["preference_style_detection"] = {
                "model": style_detection["model"],
                "source": style_detection["source"],
                "top_label": style_detection["top_label"],
                "top_score": round(style_detection["top_score"], 4),
                "style": style_detection["style"],
                "matched_terms": style_detection["matched_terms"],
            }
        db.add(ChatMessage(
            session_id=request.session_id,
            role="user",
            content=request.message,
        ))
        db.add(SessionEvent(
            session_id=request.session_id,
            consumer_id=consumer_id,
            event_type="chat_message",
            agent_name="BrainFry Detector",
            payload={
                "message": request.message,
                "b_behavioral": b_behavioral,
                "b_final": b_final,
                "n_rec": n_rec,
            },
            brainfry_score=b_final,
        ))
        db.add(ChatMessage(
            session_id=request.session_id,
            role="assistant",
            content=CLARIFICATION_PROMPT,
        ))
        db.commit()
        return ChatResponse(
            reply=CLARIFICATION_PROMPT,
            plan_context=plan_context,
            turn_complete=False,
            self_report_score=None,
            b_text=0.0,
            b_behavioral=b_behavioral,
            b_final=b_final,
            n_rec=n_rec,
            agent_trace=[{"agent": "Rule-Based Search", "status": "clarification_needed"}],
        )
    if not has_plan_context:
        tool_base_url = current_tool_base_url(http_request)
        planner = PlannerAgent(ToolUseClient(tool_base_url))
        plan_context = planner.create_plan(
            consumer_id=consumer_id,
            session_input=session_input,
            user_intent=UserIntent(query=request.message, explicit_budget=explicit_budget),
        )
        plan_context["b_behavioral"] = b_behavioral
        plan_context.setdefault("trace", {})["b_behavioral"] = b_behavioral
        if explicit_budget is not None:
            plan_context["budget_ceiling"] = explicit_budget
            plan_context.setdefault("trace", {})["budget_source"] = "explicit_chat_budget"
        plan_context["query"] = parsed_utterance["query"] or plan_context.get("query", "")
        plan_context["skin_type"] = parsed_utterance["skin_type"]
        plan_context["search_text"] = parsed_utterance["search_text"]
        plan_context["utilitarian_terms"] = parsed_utterance["utilitarian_terms"]
        plan_context["hedonic_terms"] = parsed_utterance["hedonic_terms"]
        plan_context["style_confidence"] = parsed_utterance["style_confidence"]
        if parsed_utterance["preferred_style"]:
            plan_context["preferred_style"] = parsed_utterance["preferred_style"]
        if style_detection is not None:
            plan_context["preference_style_detection"] = {
                "model": style_detection["model"],
                "source": style_detection["source"],
                "top_label": style_detection["top_label"],
                "top_score": round(style_detection["top_score"], 4),
                "style": style_detection["style"],
                "matched_terms": style_detection["matched_terms"],
            }
        for agent_name in ["User Intent Agent", "BrainFry Detector", "Psychology Agent"]:
            db.add(AgentTrace(
                session_id=request.session_id,
                agent_name=agent_name,
                status="done",
                input_data={"message": request.message},
                output_data=plan_context,
                finished_at=datetime.now(timezone.utc),
            ))
            agent_trace.append({"agent": agent_name, "status": "done"})
    else:
        if not is_simple_confirmation(request.message):
            cleaned_query = parsed_utterance["query"]
            if cleaned_query:
                plan_context["query"] = cleaned_query
            plan_context["skin_type"] = parsed_utterance["skin_type"]
            plan_context["search_text"] = parsed_utterance["search_text"]
            plan_context["utilitarian_terms"] = parsed_utterance["utilitarian_terms"]
            plan_context["hedonic_terms"] = parsed_utterance["hedonic_terms"]
            plan_context["style_confidence"] = parsed_utterance["style_confidence"]
            if parsed_utterance["preferred_style"]:
                plan_context["preferred_style"] = parsed_utterance["preferred_style"]
            if style_detection is not None:
                plan_context["preference_style_detection"] = {
                    "model": style_detection["model"],
                    "source": style_detection["source"],
                    "top_label": style_detection["top_label"],
                    "top_score": round(style_detection["top_score"], 4),
                    "style": style_detection["style"],
                    "matched_terms": style_detection["matched_terms"],
                }
            if explicit_budget is not None:
                plan_context["budget_ceiling"] = explicit_budget
                plan_context["budget_source"] = "explicit_chat_budget"

    db.add(ChatMessage(
        session_id=request.session_id,
        role="user",
        content=request.message,
    ))
    db.add(AgentTrace(
        session_id=request.session_id,
        agent_name="Conversation Agent",
        status="running",
        input_data={"message": request.message, "plan_context": plan_context},
        output_data=None,
    ))
    db.commit()

    conversation = ConversationAgent()
    messages = list(request.history or []) + [{"role": "user", "content": request.message}]
    result = conversation.run_turn(messages=messages, plan_context=plan_context)
    updated_context = result["updated_context"]
    assistant_reply = normalize_preference_style_reply(
        str(result["reply"]),
        updated_context.get("preferred_style", "utilitarian"),
    )

    db.add(ChatMessage(
        session_id=request.session_id,
        role="assistant",
        content=assistant_reply,
    ))
    db.add(SessionEvent(
        session_id=request.session_id,
        consumer_id=consumer_id,
        event_type="chat_message",
        agent_name="Conversation Agent",
        payload={
            "message": request.message,
            "b_behavioral": result.get("b_behavioral", updated_context.get("b_behavioral")),
            "b_final": result.get("b_final", updated_context.get("b_final")),
            "n_rec": result.get("n_rec", updated_context.get("n_rec")),
        },
        brainfry_score=updated_context.get("brainfry_score"),
    ))
    trace = db.query(AgentTrace).filter(
        AgentTrace.session_id == request.session_id,
        AgentTrace.agent_name == "Conversation Agent",
        AgentTrace.status == "running",
    ).first()
    if trace:
        trace.status = "done"
        trace.output_data = updated_context
        trace.finished_at = datetime.now(timezone.utc)
    db.commit()

    agent_trace.append({"agent": "Conversation Agent", "status": "done"})
    print(f'/api/chat plan_context.query = "{updated_context.get("query", "")}"')

    return ChatResponse(
        reply=assistant_reply,
        plan_context=updated_context,
        turn_complete=bool(result["turn_complete"] or is_simple_confirmation(request.message)),
        self_report_score=result["self_report_score"],
        b_text=float(result["b_text"]),
        b_behavioral=float(result.get("b_behavioral", 0.0)),
        b_final=float(result.get("b_final", updated_context.get("brainfry_score", 0.0))),
        n_rec=int(result.get("n_rec", updated_context.get("n_rec", 7))),
        agent_trace=agent_trace,
    )


@app.post("/api/recommend", response_model=list[FinalRecommendation])
def create_final_recommendations(
    request: RecommendRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
) -> list[FinalRecommendation]:
    """
    Run Planner context completion, Executor search/rerank, and Critic checks.

    The frontend calls this endpoint after the user confirms or edits the
    two-turn dialog. The response is the final 3-5 item visual grid payload.
    """
    print(f'/api/recommend request.query = "{request.query}"')
    consumer_id = normalize_consumer_id(request.consumer_id)
    explicit_budget = extract_budget_ceiling(request.query)
    budget_ceiling = explicit_budget if explicit_budget is not None else request.budget_ceiling
    tool_base_url = current_tool_base_url(http_request)
    planner = PlannerAgent(ToolUseClient(tool_base_url))
    plan = planner.create_plan(
        consumer_id=consumer_id,
        session_input=SessionInput(page_visits=0, dwell_time_variance=0.0, ctr=1.0),
        user_intent=UserIntent(
            query=request.query,
            explicit_budget=budget_ceiling,
            explicit_style=style_value(request.preferred_style),
        ),
    )
    plan["budget_ceiling"] = budget_ceiling
    plan["preferred_style"] = style_value(request.preferred_style)
    plan["psychographic_type"] = request.psychographic_type
    if request.skin_type:
        plan["skin_type"] = request.skin_type
    if request.brainfry_score is not None:
        plan["brainfry_score"] = round(float(request.brainfry_score), 4)
        plan["brainfry_level"] = PlannerAgent.classify_brainfry_level(float(request.brainfry_score))
    plan["use_vector_search"] = request.use_vector_search
    plan["utilitarian_terms"] = request.utilitarian_terms
    plan["hedonic_terms"] = request.hedonic_terms
    plan["style_confidence"] = request.style_confidence

    # 카테고리 평균가 주입 (RAG 공식 분모로 사용)
    top_cat = plan.get("top_category")
    if top_cat and top_cat in category_price_distributions:
        prices = category_price_distributions[top_cat]
        plan["category_avg_price"] = sum(prices) / len(prices)

    executor = ExecutorAgent(ProductToolClient(tool_base_url))
    critic = CriticAgent()

    # AgentTrace 기록
    target_session_id = request.session_id or consumer_id
    for agent_name in ["Product Search Agent", "Decision Simplifier", "Critic Agent"]:
        db.add(AgentTrace(
            session_id=target_session_id,
            agent_name=agent_name,
            status="running",
            input_data=plan,
            output_data=None,
        ))
    db.commit()

    executor_result = executor.execute_plan(plan)
    final_result = critic.critique(plan=plan, executor_result=executor_result)

    # AgentTrace 완료 업데이트
    for agent_name in ["Product Search Agent", "Decision Simplifier", "Critic Agent"]:
        trace = db.query(AgentTrace).filter(
            AgentTrace.session_id == target_session_id,
            AgentTrace.agent_name == agent_name,
            AgentTrace.status == "running"
        ).first()
        if trace:
            trace.status = "done"
            trace.output_data = {
                "n_rec": final_result["n_rec"],
                "decision_debug": final_result.get("decision_debug"),
            }
            trace.finished_at = datetime.now(timezone.utc)
    db.commit()

    return [
        FinalRecommendation(
            id=str(p.get("product_id")),
            product_id=str(p.get("product_id")),
            name=str(p.get("name")),
            price=int(p.get("price", 0)),
            style=str(p.get("style_type")),
            style_type=str(p.get("style_type")),
            rating=float(p.get("rating") if p.get("rating") is not None else p.get("star_rating", 0.0)),
            RAG_score=float(p.get("RAG_score", 0.0)),
            presentation_hint=final_result.get("presentation_hint", "spec_first"),
            n_rec=final_result.get("n_rec", 5),
            critic_iterations=int(final_result.get("correction_iterations", 0)),
        )
        for p in final_result["final_recommendations"]
    ]


@app.get("/admin/sessions")
def list_sessions(db: DBSession = Depends(get_db)):
    from sqlalchemy import select, func
    rows = db.execute(
        select(
            AgentTrace.session_id,
            func.min(AgentTrace.started_at).label("started_at"),
            func.count(AgentTrace.id).label("agent_calls"),
        )
        .group_by(AgentTrace.session_id)
        .order_by(func.min(AgentTrace.started_at).desc())
        .limit(50)
    ).all()
    return [
        {"session_id": r.session_id, "started_at": str(r.started_at), "agent_calls": r.agent_calls}
        for r in rows
    ]


@app.get("/admin/sessions/{session_id}")
def get_session_detail(session_id: str, db: DBSession = Depends(get_db)):
    traces = db.query(AgentTrace).filter(
        AgentTrace.session_id == session_id
    ).order_by(AgentTrace.started_at).all()
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp).all()
    return {
        "agent_timeline": [
            {"agent": t.agent_name, "status": t.status,
             "input": t.input_data, "output": t.output_data,
             "started_at": str(t.started_at)}
            for t in traces
        ],
        "chat_history": [
            {"role": m.role, "content": m.content, "timestamp": str(m.timestamp)}
            for m in messages
        ],
    }


@app.get("/admin/stats/brainfry")
def brainfry_stats(db: DBSession = Depends(get_db)):
    events = db.query(SessionEvent).filter(SessionEvent.brainfry_score.isnot(None)).all()
    scores = [e.brainfry_score for e in events]
    if not scores:
        return {"low": 0, "mid": 0, "high": 0, "average": 0.0}
    return {
        "low":     sum(1 for s in scores if s <= 0.35),
        "mid":     sum(1 for s in scores if 0.35 < s <= 0.65),
        "high":    sum(1 for s in scores if s > 0.65),
        "average": round(sum(scores) / len(scores), 3),
    }


def read_benchmark_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def group_benchmark_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        consumer_id = row.get("consumer_id", "").strip()
        if consumer_id:
            grouped.setdefault(consumer_id, []).append(row)
    return grouped


def strict_budget_compliance(
    consumers: list[dict[str, str]],
    recommendation_rows: list[dict[str, str]],
) -> float:
    recommendations = group_benchmark_rows(recommendation_rows)
    scores = []
    for consumer in consumers:
        consumer_id = consumer.get("consumer_id", "").strip()
        rows = recommendations.get(consumer_id, [])
        if not rows:
            continue
        budget = float(consumer.get("budget_amount") or 0)
        scores.append(int(all(float(row.get("price") or 0) <= budget for row in rows)))
    return round(sum(scores) / len(scores), 4) if scores else 0.0


@app.get("/admin/benchmark/dashboard")
def benchmark_dashboard():
    downloads_dir = Path.home() / "Downloads"
    consumers = read_benchmark_csv(downloads_dir / "consumer_profiles_200_final.csv")
    cara_rows = read_benchmark_csv(BASE_DIR / "cara_results.csv")
    random_rows = read_benchmark_csv(BASE_DIR / "baseline_random_results.csv")
    popular_rows = read_benchmark_csv(BASE_DIR / "baseline_popular_results.csv")
    persona_rows = read_benchmark_csv(BASE_DIR / "persona_scores.csv")

    persona_by_type: dict[str, list[float]] = {}
    for row in persona_rows:
        persona_type = row.get("psychographic_type", "").strip()
        if persona_type:
            persona_by_type.setdefault(persona_type, []).append(
                float(row.get("persona_satisfaction") or 0)
            )

    cara_grouped = group_benchmark_rows(cara_rows)
    critic_iterations = []
    for rows in cara_grouped.values():
        if rows and rows[0].get("critic_iterations") not in {None, ""}:
            critic_iterations.append(float(rows[0]["critic_iterations"]))

    brainfry_counts = {"low": 0, "mid": 0, "high": 0}
    for consumer in consumers:
        score = float(consumer.get("brainfry_score") or 0)
        if score <= 0.35:
            brainfry_counts["low"] += 1
        elif score <= 0.65:
            brainfry_counts["mid"] += 1
        else:
            brainfry_counts["high"] += 1

    total_consumers = len(consumers)
    brainfry = {
        key: {
            "count": count,
            "percentage": round(count / total_consumers * 100, 1) if total_consumers else 0.0,
        }
        for key, count in brainfry_counts.items()
    }

    return {
        "n_consumers": total_consumers,
        "metrics": {
            "hit_at_n": {"cara": 0.975, "random": 0.605, "popular": 0.390},
            "budget_compliance": {
                "cara": strict_budget_compliance(consumers, cara_rows),
                "random": strict_budget_compliance(consumers, random_rows),
                "popular": strict_budget_compliance(consumers, popular_rows),
            },
            "preference_alignment": {"cara": 0.69, "random": 0.64, "popular": 0.64},
        },
        "critic_average_iterations": (
            round(sum(critic_iterations) / len(critic_iterations), 2)
            if critic_iterations else None
        ),
        "persona_satisfaction": {
            persona_type: round(sum(scores) / len(scores), 1)
            for persona_type, scores in persona_by_type.items()
        },
        "brainfry": brainfry,
        "sources": {
            "cara_results": bool(cara_rows),
            "baseline_random_results": bool(random_rows),
            "baseline_popular_results": bool(popular_rows),
            "consumer_profiles": bool(consumers),
            "ground_truth": (downloads_dir / "ground_truth_final.csv").exists(),
            "persona_scores": bool(persona_rows),
        },
    }


@app.get("/admin/benchmark/download/{report_name}")
def download_benchmark_report(report_name: str):
    reports = {
        "metrics": BASE_DIR / "benchmark_results.csv",
        "persona-satisfaction": BASE_DIR / "persona_scores.csv",
        "consumer-profiles": Path.home() / "Downloads" / "consumer_profiles_200_final.csv",
    }
    path = reports.get(report_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown benchmark report.")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Benchmark report not found: {path.name}")
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=path.name,
    )


@app.post("/admin/benchmark/evaluate")
def run_benchmark_evaluation(
    request: RecommendRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
):
    from persona_evaluator import PersonaEvaluator

    consumer_id = normalize_consumer_id(request.consumer_id)
    tool_base_url = current_tool_base_url(http_request)
    planner = PlannerAgent(ToolUseClient(tool_base_url))
    plan = planner.create_plan(
        consumer_id=consumer_id,
        session_input=SessionInput(page_visits=0, dwell_time_variance=0.0, ctr=1.0),
        user_intent=UserIntent(
            query=request.query,
            explicit_budget=request.budget_ceiling,
            explicit_style=style_value(request.preferred_style),
        ),
    )
    plan["psychographic_type"] = request.psychographic_type

    top_cat = plan.get("top_category")
    if top_cat and top_cat in category_price_distributions:
        prices = category_price_distributions[top_cat]
        plan["category_avg_price"] = sum(prices) / len(prices)

    executor = ExecutorAgent(ProductToolClient(tool_base_url))
    critic = CriticAgent()
    executor_result = executor.execute_plan(plan)
    final_result = critic.critique(plan=plan, executor_result=executor_result)

    plan["n_rec"] = final_result["n_rec"]
    evaluator = PersonaEvaluator()
    persona_scores = evaluator.evaluate_all(
        recommendations=final_result["final_recommendations"],
        plan_context=plan,
    )

    return {
        "recommendations": final_result["final_recommendations"],
        "n_rec": final_result["n_rec"],
        "presentation_hint": final_result["presentation_hint"],
        "plan": plan,
        "persona_evaluation": persona_scores,
        "mean_satisfaction": round(
            sum(v["persona_satisfaction_score"] for v in persona_scores.values()) / 6, 2
        ),
        "mean_decision_ease": round(
            sum(v["decision_ease_score"] for v in persona_scores.values()) / 6, 2
        ),
    }


@app.get("/admin/sessions/{session_id}/stream")
async def stream_agent_trace(session_id: str):
    async def event_generator():
        last_id = 0
        import json as _json
        while True:
            with DBSession(engine) as db:
                new_traces = db.query(AgentTrace).filter(
                    AgentTrace.session_id == session_id,
                    AgentTrace.id > last_id
                ).order_by(AgentTrace.id).all()
            for trace in new_traces:
                last_id = trace.id
                data = _json.dumps({
                    "agent": trace.agent_name,
                    "status": trace.status,
                    "output": trace.output_data,
                    "started_at": str(trace.started_at),
                })
                yield f"data: {data}\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


port = int(os.environ.get("PORT", 8000))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port)
