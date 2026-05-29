from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
CARA_DB_PATH = BASE_DIR / "cara.db"
VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-large-2"
EMBEDDING_DIMENSIONS = 1536


load_dotenv(BASE_DIR / ".env", override=True)


def ensure_embedding_column(db_path: Path = CARA_DB_PATH) -> None:
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(products)").fetchall()
        }
        if "embedding" not in columns:
            connection.execute("ALTER TABLE products ADD COLUMN embedding TEXT")
        connection.commit()


def product_embedding_text(row: sqlite3.Row) -> str:
    return f"{row['product_name']} {row['brand']} {row['keywords'] or ''}".strip()


def embed_texts(
    texts: list[str],
    input_type: str,
    api_key: str | None = None,
    max_retries: int = 6,
) -> list[list[float]]:
    key = api_key or os.getenv("VOYAGE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "VOYAGE_API_KEY is required to create Voyage AI embeddings."
        )

    payload = {
        "input": texts,
        "model": VOYAGE_MODEL,
        "input_type": input_type,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120) as client:
        for attempt in range(max_retries):
            try:
                response = client.post(
                    VOYAGE_EMBEDDINGS_URL,
                    headers=headers,
                    json=payload,
                )
                if response.status_code != 429:
                    response.raise_for_status()
                    data = response.json()["data"]
                    break
                retry_after = response.headers.get("Retry-After")
                wait_seconds = (
                    float(retry_after) if retry_after else min(2 ** attempt * 5, 60)
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == max_retries - 1:
                    raise
                wait_seconds = min(2 ** attempt * 5, 60)
            time.sleep(wait_seconds)
        else:
            response.raise_for_status()

    embeddings = [item["embedding"] for item in data]
    for embedding in embeddings:
        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Expected {EMBEDDING_DIMENSIONS} dimensions, got {len(embedding)}"
            )
    return embeddings


def embed_missing_products(
    db_path: Path = CARA_DB_PATH,
    batch_size: int = 20,
    sleep_seconds: float = 0.5,
    max_batches: int | None = None,
) -> int:
    ensure_embedding_column(db_path)
    total_updated = 0

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT product_id, product_name, brand, keywords
            FROM products
            WHERE embedding IS NULL
            ORDER BY product_id
            """
        ).fetchall()

    batches_processed = 0
    for start in range(0, len(rows), batch_size):
        if max_batches is not None and batches_processed >= max_batches:
            break
        batch = rows[start : start + batch_size]
        texts = [product_embedding_text(row) for row in batch]
        embeddings = embed_texts(texts, input_type="document")

        with sqlite3.connect(db_path) as connection:
            connection.executemany(
                "UPDATE products SET embedding = ? WHERE product_id = ?",
                [
                    (json.dumps(embedding, separators=(",", ":")), row["product_id"])
                    for row, embedding in zip(batch, embeddings)
                ],
            )
            connection.commit()

        total_updated += len(batch)
        batches_processed += 1
        if start + batch_size < len(rows) and (
            max_batches is None or batches_processed < max_batches
        ):
            time.sleep(sleep_seconds)

    return total_updated


def embedding_count(db_path: Path = CARA_DB_PATH) -> int:
    ensure_embedding_column(db_path)
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL"
            ).fetchone()[0]
        )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def lexical_similarity(query_text: str, row: sqlite3.Row | dict[str, Any]) -> float:
    haystack = " ".join(
        str(row.get(key, "") if isinstance(row, dict) else row[key] or "")
        for key in ("product_name", "brand", "subcategory", "keywords", "skin_type")
    ).lower()
    query = (query_text or "").lower()
    tokens = [
        token
        for token in query.replace(",", " ").split()
        if token and not any(char.isdigit() for char in token)
    ]
    if not tokens:
        return 1.0
    matched = sum(1 for token in tokens if token in haystack)
    return matched / len(tokens)


def compute_rag_score(
    similarity: float,
    row: sqlite3.Row | dict[str, Any],
    user_budget: float | None,
    preferred_style: str | None,
    avg_price: float,
) -> float:
    style_value = row.get("preference_style") if isinstance(row, dict) else row["preference_style"]
    price_value = float(row.get("price", 0) if isinstance(row, dict) else row["price"] or 0)
    rating_value = float(row.get("star_rating", 0) if isinstance(row, dict) else row["star_rating"] or 0)
    style_match = 1 if preferred_style and style_value == preferred_style else 0
    budget = float(user_budget or avg_price or 1.0)
    price_score = math.exp(-abs(price_value - budget) / max(avg_price, 1.0))
    return (
        10 * similarity
        + 15 * style_match
        + 10 * price_score
        + 3 * rating_value
    )


def lexical_rag_rerank_rows(
    query_text: str,
    rows: list[sqlite3.Row],
    user_budget: float | None,
    preferred_style: str | None,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    candidate_prices = [float(row["price"] or 0) for row in rows]
    avg_price = sum(candidate_prices) / max(len(candidate_prices), 1)
    reranked: list[dict[str, Any]] = []
    for row in rows:
        similarity = lexical_similarity(query_text, row)
        item = dict(row)
        item["S"] = round(similarity, 6)
        item["RAG_score"] = round(
            compute_rag_score(
                similarity=similarity,
                row=row,
                user_budget=user_budget,
                preferred_style=preferred_style,
                avg_price=avg_price,
            ),
            4,
        )
        reranked.append(item)
    reranked.sort(key=lambda item: item["RAG_score"], reverse=True)
    return reranked


def rag_rerank_rows(
    query_text: str,
    rows: list[sqlite3.Row],
    user_budget: float | None,
    preferred_style: str | None,
) -> list[dict[str, Any]]:
    rows_with_embeddings = [row for row in rows if row["embedding"]]
    if not rows_with_embeddings:
        return []

    query_vector = embed_texts([query_text], input_type="query")[0]
    candidate_prices = [float(row["price"] or 0) for row in rows_with_embeddings]
    avg_price = sum(candidate_prices) / max(len(candidate_prices), 1)
    budget = float(user_budget or avg_price or 1.0)

    reranked: list[dict[str, Any]] = []
    for row in rows_with_embeddings:
        embedding = json.loads(row["embedding"])
        similarity = cosine_similarity(query_vector, embedding)
        rag_score = compute_rag_score(
            similarity=similarity,
            row=row,
            user_budget=budget,
            preferred_style=preferred_style,
            avg_price=avg_price,
        )
        item = dict(row)
        item["S"] = round(similarity, 6)
        item["RAG_score"] = round(rag_score, 4)
        reranked.append(item)

    reranked.sort(key=lambda item: item["RAG_score"], reverse=True)
    return reranked


def similar_products_for_product(
    product_name: str,
    subcategory: str,
    db_path: Path = CARA_DB_PATH,
    limit: int = 5,
) -> list[dict[str, Any]]:
    ensure_embedding_column(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        source = connection.execute(
            "SELECT embedding FROM products WHERE product_name = ?",
            (product_name,),
        ).fetchone()
        if not source or not source["embedding"]:
            return []
        source_embedding = json.loads(source["embedding"])
        rows = connection.execute(
            """
            SELECT product_name, embedding
            FROM products
            WHERE subcategory = ?
              AND embedding IS NOT NULL
            """,
            (subcategory,),
        ).fetchall()

    scored = [
        {
            "product_name": row["product_name"],
            "similarity": round(
                cosine_similarity(source_embedding, json.loads(row["embedding"])),
                6,
            ),
        }
        for row in rows
    ]
    scored.sort(key=lambda item: item["similarity"], reverse=True)
    return scored[:limit]
