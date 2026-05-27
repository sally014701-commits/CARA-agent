from __future__ import annotations

import argparse

from vector_search import (
    embed_missing_products,
    embedding_count,
    ensure_embedding_column,
    similar_products_for_product,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage CARA product embeddings.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ensure-schema")
    subparsers.add_parser("count")

    embed_parser = subparsers.add_parser("embed-products")
    embed_parser.add_argument("--batch-size", type=int, default=20)
    embed_parser.add_argument("--sleep", type=float, default=0.5)
    embed_parser.add_argument("--max-batches", type=int)

    similar_parser = subparsers.add_parser("similar")
    similar_parser.add_argument("--product-name", default="그린티 씨드 세럼")
    similar_parser.add_argument("--subcategory", default="스킨")
    similar_parser.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()

    if args.command == "ensure-schema":
        ensure_embedding_column()
        print("embedding column ready")
    elif args.command == "count":
        print(embedding_count())
    elif args.command == "embed-products":
        updated = embed_missing_products(
            batch_size=args.batch_size,
            sleep_seconds=args.sleep,
            max_batches=args.max_batches,
        )
        print(f"updated={updated}")
        print(f"embedding_count={embedding_count()}")
    elif args.command == "similar":
        rows = similar_products_for_product(
            product_name=args.product_name,
            subcategory=args.subcategory,
            limit=args.limit,
        )
        for row in rows:
            print(f"{row['product_name']}\t{row['similarity']}")


if __name__ == "__main__":
    main()
