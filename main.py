"""
CARA Tool Use Module.

Run:
  python main.py

The server loads products.json and consumers.json into memory at startup and
exposes RESTful API tools for CARA agents.
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from critic_agent import CriticAgent
from executor_agent import ExecutorAgent, ProductToolClient
from planner_agent import PlannerAgent, SessionInput, ToolUseClient, UserIntent


BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_PATH = BASE_DIR / "products.json"
CONSUMERS_PATH = BASE_DIR / "consumers.json"

StyleType = Literal["practical", "design"]
BudgetLevel = Literal["low", "mid", "high"]


class Product(BaseModel):
    """Product catalog record loaded from products.json."""

    product_id: str
    category: str
    item_type: str
    name: str
    price: int
    style_type: StyleType
    rating: float
    review_count: int
    description: str | None = None


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


class SessionDataRequest(BaseModel):
    """Current passive tracking metrics sent by the storefront."""

    n: int = Field(default=0, ge=0)
    dwell_variance: float = Field(default=0.0, ge=0)
    ctr: float = Field(default=0.0, ge=0.0, le=1.0)


class PlanRequest(BaseModel):
    """Request body for Planner orchestration."""

    consumer_id: str = "user123"
    query: str = ""
    session_data: SessionDataRequest


class PlanResponse(BaseModel):
    """Planner response used by the two-turn confirmation dialog."""

    consumer_id: str
    query: str
    budget_ceiling: int
    preferred_style: StyleType
    brainfry_level: str
    brainfry_score: float
    top_category: str | None = None
    avg_spend: float | None = None


class RecommendRequest(BaseModel):
    """Request body for end-to-end recommendation orchestration."""

    consumer_id: str = "user123"
    query: str = ""
    budget_ceiling: int
    preferred_style: StyleType


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


products: list[Product] = []
consumers: dict[str, ConsumerProfile] = {}


def load_json(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array from disk and return raw dictionaries."""
    if not path.exists():
        raise FileNotFoundError(f"Required data file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array.")

    return data


def load_database() -> None:
    """Load products and consumers into process memory for fast tool access."""
    global products, consumers

    products = [Product.model_validate(item) for item in load_json(PRODUCTS_PATH)]
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
    if consumer_id in {"user123", "guest", "USR-001"}:
        return "C0001"
    return consumer_id


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize the in-memory JSON database when the FastAPI server starts."""
    load_database()
    yield


app = FastAPI(
    title="CARA Tool Use Module",
    description=(
        "RESTful API tools for CARA(Context-Aware Recommendation Agent), "
        "backed by products.json and consumers.json."
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


@app.get("/", response_model=dict[str, str])
def health_check() -> dict[str, str]:
    """Return a lightweight health check for server and agent connectivity."""
    return {"status": "ok", "service": "CARA Tool Use Module"}


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
    style_type: StyleType | None = Query(
        default=None,
        description="Optional style filter: practical or design.",
    ),
    category: str | None = Query(
        default=None,
        description="Optional product category filter.",
    ),
) -> ProductSearchResponse:
    """
    Search the product catalog with keyword and optional structured filters.

    CARA agents call this tool to collect candidate products. The endpoint uses
    simple case-insensitive string matching against product name and optional
    description, then applies max_price, style_type, and category filters.
    """
    normalized_query = query.strip().lower()
    normalized_category = category.strip().lower() if category is not None else None

    filtered_products: list[Product] = []

    for product in products:
        searchable_text = f"{product.name} {product.description or ''}".lower()

        if normalized_query and normalized_query not in searchable_text:
            continue

        if max_price is not None and product.price > max_price:
            continue

        if style_type is not None and product.style_type != style_type:
            continue

        if (
            normalized_category is not None
            and product.category.lower() != normalized_category
        ):
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


@app.post("/api/plan", response_model=PlanResponse)
def create_recommendation_plan(request: PlanRequest) -> PlanResponse:
    """
    Orchestrate the Planner Agent for the storefront confirmation dialog.

    The frontend sends passive tracking metrics, and this endpoint returns the
    inferred budget, preferred style, and BrainFry state needed for Turn 1.
    """
    consumer_id = normalize_consumer_id(request.consumer_id)
    planner = PlannerAgent(ToolUseClient("http://127.0.0.1:8000"))
    plan = planner.create_plan(
        consumer_id=consumer_id,
        session_input=SessionInput(
            page_visits=request.session_data.n,
            dwell_time_variance=request.session_data.dwell_variance,
            ctr=request.session_data.ctr,
        ),
        user_intent=UserIntent(query=request.query),
    )

    return PlanResponse(
        consumer_id=consumer_id,
        query=plan["query"],
        budget_ceiling=int(plan["budget_ceiling"]),
        preferred_style=plan["preferred_style"],
        brainfry_level=plan["brainfry_level"],
        brainfry_score=float(plan["brainfry_score"]),
        top_category=plan.get("top_category"),
        avg_spend=plan.get("avg_spend"),
    )


@app.post("/api/recommend", response_model=list[FinalRecommendation])
def create_final_recommendations(
    request: RecommendRequest,
) -> list[FinalRecommendation]:
    """
    Run Planner context completion, Executor search/rerank, and Critic checks.

    The frontend calls this endpoint after the user confirms or edits the
    two-turn dialog. The response is the final 3-5 item visual grid payload.
    """
    consumer_id = normalize_consumer_id(request.consumer_id)
    planner = PlannerAgent(ToolUseClient("http://127.0.0.1:8000"))
    plan = planner.create_plan(
        consumer_id=consumer_id,
        session_input=SessionInput(page_visits=0, dwell_time_variance=0.0, ctr=1.0),
        user_intent=UserIntent(
            query=request.query,
            explicit_budget=request.budget_ceiling,
            explicit_style=request.preferred_style,
        ),
    )
    plan["budget_ceiling"] = request.budget_ceiling
    plan["preferred_style"] = request.preferred_style

    executor = ExecutorAgent(ProductToolClient("http://127.0.0.1:8000"))
    critic = CriticAgent()
    executor_result = executor.execute_plan(plan)
    final_result = critic.critique(plan=plan, executor_result=executor_result)

    return [
        FinalRecommendation(
            id=str(product.get("product_id")),
            product_id=str(product.get("product_id")),
            name=str(product.get("name")),
            price=int(product.get("price", 0)),
            style=str(product.get("style_type")),
            style_type=str(product.get("style_type")),
            rating=float(product.get("rating", 0.0)),
            RAG_score=float(product.get("RAG_score", 0.0)),
        )
        for product in final_result["final_recommendations"][:5]
    ]


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
