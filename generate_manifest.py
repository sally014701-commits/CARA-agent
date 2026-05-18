"""
generate_manifest.py
Builds product_manifest.json from products.json.
Each entry maps: product_id, sku_id, image_file, variant_group, category.
SKU variant_group = item_type (same base geometry, only color/material changes).
"""
import json
import os

PRODUCTS_FILE = "products.json"
MANIFEST_FILE = "product_manifest.json"
ASSETS_DIR = "assets/products"

with open(PRODUCTS_FILE) as f:
    products = json.load(f)

manifest = []
for p in products:
    product_id = p["product_id"]
    category = p["category"]
    item_type = p["item_type"]
    style_type = p.get("style_type", "practical")

    # variant_group: same item_type = same base geometry, different color/material per style
    variant_group = f"{item_type.replace(' ', '_')}"

    # sku_id encodes product_id + style variant
    sku_id = f"{product_id}-{style_type[:1].upper()}"

    image_file = f"assets/products/{product_id}.png"

    manifest.append({
        "product_id": product_id,
        "sku_id": sku_id,
        "image_file": image_file,
        "variant_group": variant_group,
        "category": category,
        "item_type": item_type,
        "style_type": style_type,
        "name": p["name"],
        "price": p["price"],
        "rating": p["rating"]
    })

# Sort by product_id for deterministic output
manifest.sort(key=lambda x: x["product_id"])

with open(MANIFEST_FILE, "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"✓ product_manifest.json written — {len(manifest)} entries")

# Summary by category
from collections import Counter
cats = Counter(m["category"] for m in manifest)
for cat, count in sorted(cats.items()):
    print(f"  {cat}: {count} products")
