"""
redeploy_fixed.py
새로 생성된 7개 item_type 템플릿을 해당 제품 이미지에 배포한다.
"""
import json, os, shutil

ASSETS = "assets/products"
MANIFEST = "product_manifest.json"

FIXED_TYPES = {
    "dumbbells", "pillows", "resistance bands",
    "running shoes", "storage boxes", "water bottles", "yoga mats"
}

with open(MANIFEST) as f:
    manifest = json.load(f)

updated = 0
errors = []

for entry in manifest:
    it = entry["item_type"]
    if it not in FIXED_TYPES:
        continue

    style = entry["style_type"]
    slug = it.replace(" ", "_")
    tmpl = os.path.join(ASSETS, f"tmpl_{slug}_{style}.png")
    dest = os.path.join(ASSETS, f"{entry['product_id']}.png")

    if not os.path.exists(tmpl):
        errors.append(f"MISSING TEMPLATE: {tmpl}")
        continue

    tmpl_size = os.path.getsize(tmpl)
    if tmpl_size < 50_000:
        errors.append(f"TEMPLATE TOO SMALL ({tmpl_size}B): {tmpl}")
        continue

    shutil.copy2(tmpl, dest)
    updated += 1
    print(f"  ✓ {entry['product_id']} ← {os.path.basename(tmpl)}")

print()
print(f"Updated: {updated} products")
if errors:
    print(f"Errors ({len(errors)}):")
    for e in errors:
        print(f"  ✗ {e}")
else:
    print("No errors.")
