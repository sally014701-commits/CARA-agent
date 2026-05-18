"""
distribute_images.py
- Fills any missing tmpl_* images by copying from closest available template
- Then distributes all templates to the 200 product PNG files
"""
import json, os, shutil

ASSETS = "assets/products"
MANIFEST = "product_manifest.json"

# Map item_type -> (practical_tmpl, design_tmpl)
TEMPLATES = {
    "smartphones":      ("tmpl_smartphones_practical.png",      "tmpl_smartphones_design.png"),
    "laptops":          ("tmpl_laptops_practical.png",           "tmpl_laptops_design.png"),
    "earbuds":          ("tmpl_earbuds_practical.png",           "tmpl_earbuds_design.png"),
    "tablets":          ("tmpl_tablets_practical.png",           "tmpl_tablets_design.png"),
    "smartwatches":     ("tmpl_smartwatches_practical.png",      "tmpl_smartwatches_design.png"),
    "bags":             ("tmpl_bags_practical.png",              "tmpl_bags_design.png"),
    "sneakers":         ("tmpl_sneakers_practical.png",          "tmpl_sneakers_design.png"),
    "jeans":            ("tmpl_jeans_practical.png",             "tmpl_jeans_design.png"),
    "dresses":          ("tmpl_dresses_practical.png",           "tmpl_dresses_design.png"),
    "jackets":          ("tmpl_jackets_practical.png",           "tmpl_jackets_design.png"),
    "moisturizers":     ("tmpl_moisturizers_practical.png",      "tmpl_moisturizers_design.png"),
    "serums":           ("tmpl_serums_practical.png",            "tmpl_serums_design.png"),
    "sunscreens":       ("tmpl_sunscreens_practical.png",        "tmpl_sunscreens_design.png"),
    "shampoos":         ("tmpl_shampoos_practical.png",          "tmpl_shampoos_design.png"),
    "lip balms":        ("tmpl_lip_balms_practical.png",         "tmpl_lip_balms_design.png"),
    # home living — use closest available if not generated yet
    "air purifiers":    ("tmpl_air_purifiers_practical.png",     "tmpl_air_purifiers_design.png"),
    "coffee makers":    ("tmpl_coffee_makers_practical.png",     "tmpl_coffee_makers_design.png"),
    "desk lamps":       ("tmpl_desk_lamps_practical.png",        "tmpl_desk_lamps_design.png"),
    "pillows":          ("tmpl_pillows_practical.png",           "tmpl_pillows_design.png"),
    "storage boxes":    ("tmpl_storage_boxes_practical.png",     "tmpl_storage_boxes_design.png"),
    # sports
    "dumbbells":        ("tmpl_dumbbells_practical.png",         "tmpl_dumbbells_design.png"),
    "yoga mats":        ("tmpl_yoga_mats_practical.png",         "tmpl_yoga_mats_design.png"),
    "running shoes":    ("tmpl_running_shoes_practical.png",     "tmpl_running_shoes_design.png"),
    "resistance bands": ("tmpl_resistance_bands_practical.png",  "tmpl_resistance_bands_design.png"),
    "water bottles":    ("tmpl_water_bottles_practical.png",     "tmpl_water_bottles_design.png"),
}

# Fallback chain: if a template is missing, use the other variant or a category peer
CATEGORY_FALLBACKS = {
    "home living": "tmpl_moisturizers_practical.png",   # clean white bottle works
    "sports equipment": "tmpl_dumbbells_practical.png",
    "electronics": "tmpl_smartphones_practical.png",
    "fashion": "tmpl_bags_practical.png",
    "beauty": "tmpl_moisturizers_practical.png",
}

def resolve_template(item_type, style_type, category):
    idx = 0 if style_type == "practical" else 1
    pair = TEMPLATES.get(item_type)
    if pair:
        tmpl = os.path.join(ASSETS, pair[idx])
        if os.path.exists(tmpl) and os.path.getsize(tmpl) > 50000:
            return tmpl
        # try other variant
        other = os.path.join(ASSETS, pair[1 - idx])
        if os.path.exists(other) and os.path.getsize(other) > 50000:
            return other
    # category fallback
    fb = CATEGORY_FALLBACKS.get(category)
    if fb:
        p = os.path.join(ASSETS, fb)
        if os.path.exists(p):
            return p
    # last resort: first available tmpl
    for f in sorted(os.listdir(ASSETS)):
        if f.startswith("tmpl_") and f.endswith(".png"):
            p = os.path.join(ASSETS, f)
            if os.path.getsize(p) > 50000:
                return p
    return None

with open(MANIFEST) as f:
    manifest = json.load(f)

copied = 0
missing_tmpl = []

for entry in manifest:
    pid = entry["product_id"]
    item_type = entry["item_type"]
    style_type = entry["style_type"]
    category = entry["category"]
    dst = os.path.join(ASSETS, f"{pid}.png")

    tmpl = resolve_template(item_type, style_type, category)
    if tmpl:
        shutil.copy2(tmpl, dst)
        copied += 1
    else:
        missing_tmpl.append(pid)

print(f"✓ Distributed {copied} product images")
if missing_tmpl:
    print(f"  ! Could not resolve template for: {missing_tmpl}")

# Verify
ok = sum(1 for e in manifest if os.path.exists(os.path.join(ASSETS, f"{e['product_id']}.png")) and os.path.getsize(os.path.join(ASSETS, f"{e['product_id']}.png")) > 50000)
print(f"  ✓ {ok}/{len(manifest)} products have valid images (>50KB)")
