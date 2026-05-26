"""
CARA Tool Use Module.

Run:
  python main.py

The server loads products.json and consumers.json into memory at startup and
exposes RESTful API tools for CARA agents.
"""

from __future__ import annotations

import asyncio
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
from fastapi import Depends, FastAPI, HTTPException, Query
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


BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_PATH = BASE_DIR / "products.json"
CONSUMERS_PATH = BASE_DIR / "consumers.json"

BudgetLevel = Literal["low", "mid", "high"]


class StyleType(str, Enum):
    utilitarian = "utilitarian"
    hedonic = "hedonic"


class Product(BaseModel):
    """Product catalog record loaded from products.json."""

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
    stock_status: bool | None = None
    description: str | None = None

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

    consumer_id: str = "user123"
    query: str = ""
    budget_ceiling: int
    preferred_style: StyleType
    psychographic_type: str = "utilitarian"


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
    if consumer_id in {"user123", "guest", "USR-001"}:
        return "C0001"
    return consumer_id


def style_value(style: Any) -> str:
    return style.value if isinstance(style, StyleType) else str(style)


def build_category_price_distributions(products: list) -> dict:
    from collections import defaultdict
    dist = defaultdict(list)
    for product in products:
        dist[product.category].append(float(product.price))
    return {cat: sorted(prices) for cat, prices in dist.items()}


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

app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")


@app.get("/", response_model=dict[str, str])
def health_check() -> dict[str, str]:
    """Return a lightweight health check for server and agent connectivity."""
    return {"status": "ok", "service": "CARA Tool Use Module"}


@app.get("/CARA.html", response_class=FileResponse)
def serve_cara_html() -> FileResponse:
    return FileResponse(BASE_DIR / "CARA.html")


@app.get("/admin.html", response_class=FileResponse)
def serve_admin_html() -> FileResponse:
    return FileResponse(BASE_DIR / "admin.html")


@app.get("/app", response_class=FileResponse)
def serve_app() -> FileResponse:
    return FileResponse(BASE_DIR / "CARA.html")


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
        description="Optional style filter: utilitarian or hedonic.",
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


@app.get("/products/price-distributions", response_model=dict)
def get_price_distributions():
    return category_price_distributions


@app.post("/api/plan", response_model=PlanResponse)
def create_recommendation_plan(request: PlanRequest, db: DBSession = Depends(get_db)):
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
            scroll_depth=request.session_data.scroll_depth,
            query_reformulations=request.session_data.query_reformulations,
            self_report_score=request.session_data.self_report_score,
            text_brainfry_score=request.session_data.text_brainfry_score,
        ),
        user_intent=UserIntent(query=request.query),
    )
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


@app.post("/api/chat", response_model=ChatResponse)
def run_chat_turn(request: ChatRequest, db: DBSession = Depends(get_db)) -> ChatResponse:
    consumer_id = normalize_consumer_id(request.consumer_id)
    plan_context = dict(request.plan_context or {})

    agent_trace: list[dict[str, str]] = []
    if not plan_context:
        planner = PlannerAgent(ToolUseClient("http://127.0.0.1:8000"))
        plan_context = planner.create_plan(
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
            user_intent=UserIntent(query=request.message),
        )
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
        plan_context.setdefault("query", request.message)

    db.add(ChatMessage(
        session_id=request.session_id,
        role="user",
        content=request.message,
    ))
    db.add(SessionEvent(
        session_id=request.session_id,
        consumer_id=consumer_id,
        event_type="chat_message",
        agent_name="Conversation Agent",
        payload={"message": request.message},
        brainfry_score=plan_context.get("brainfry_score"),
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

    db.add(ChatMessage(
        session_id=request.session_id,
        role="assistant",
        content=result["reply"],
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

    return ChatResponse(
        reply=result["reply"],
        plan_context=updated_context,
        turn_complete=bool(result["turn_complete"]),
        self_report_score=result["self_report_score"],
        b_text=float(result["b_text"]),
        agent_trace=agent_trace,
    )


@app.post("/api/recommend", response_model=list[FinalRecommendation])
def create_final_recommendations(
    request: RecommendRequest,
    db: DBSession = Depends(get_db),
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
            explicit_style=style_value(request.preferred_style),
        ),
    )
    plan["budget_ceiling"] = request.budget_ceiling
    plan["preferred_style"] = style_value(request.preferred_style)
    plan["psychographic_type"] = request.psychographic_type

    # 카테고리 평균가 주입 (RAG 공식 분모로 사용)
    top_cat = plan.get("top_category")
    if top_cat and top_cat in category_price_distributions:
        prices = category_price_distributions[top_cat]
        plan["category_avg_price"] = sum(prices) / len(prices)

    executor = ExecutorAgent(ProductToolClient("http://127.0.0.1:8000"))
    critic = CriticAgent()

    # AgentTrace 기록
    for agent_name in ["Product Search Agent", "Decision Simplifier", "Critic Agent"]:
        db.add(AgentTrace(
            session_id=consumer_id,
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
            AgentTrace.session_id == consumer_id,
            AgentTrace.agent_name == agent_name,
            AgentTrace.status == "running"
        ).first()
        if trace:
            trace.status = "done"
            trace.output_data = {"n_rec": final_result["n_rec"]}
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


@app.post("/admin/benchmark/evaluate")
def run_benchmark_evaluation(request: RecommendRequest, db: DBSession = Depends(get_db)):
    from persona_evaluator import PersonaEvaluator

    consumer_id = normalize_consumer_id(request.consumer_id)
    planner = PlannerAgent(ToolUseClient("http://127.0.0.1:8000"))
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

    executor = ExecutorAgent(ProductToolClient("http://127.0.0.1:8000"))
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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
