"""
check_image_coverage.py
- 각 item_type별로 전용 tmpl 이미지가 존재하는지 확인
- 폴백을 사용 중인 item_type과 영향받는 제품 수 출력
- 이미지 파일 크기로 실제 생성 여부 판단 (< 50KB = 폴백 의심)
"""
import json, os
from PIL import Image
import hashlib

ASSETS = "assets/products"
MANIFEST = "product_manifest.json"

with open(MANIFEST) as f:
    manifest = json.load(f)

# 1. 각 item_type별 전용 tmpl 파일 존재 여부
all_item_types = sorted(set(e["item_type"] for e in manifest))
print("=" * 60)
print("TEMPLATE COVERAGE CHECK")
print("=" * 60)

missing_templates = []
for it in all_item_types:
    for style in ["practical", "design"]:
        slug = it.replace(" ", "_")
        tmpl = os.path.join(ASSETS, f"tmpl_{slug}_{style}.png")
        exists = os.path.exists(tmpl)
        size_kb = os.path.getsize(tmpl) / 1024 if exists else 0
        ok = exists and size_kb > 50
        if not ok:
            missing_templates.append((it, style, tmpl, size_kb))
            print(f"  ✗ MISSING  {it:25s} [{style:10s}]  {size_kb:.0f}KB  {tmpl}")

if not missing_templates:
    print("  All templates present (>50KB)")

print()

# 2. 폴백 해시 기반 중복 감지 — 같은 이미지가 여러 item_type에 쓰이는지
print("=" * 60)
print("FALLBACK DETECTION (hash-based)")
print("=" * 60)

def img_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None

# tmpl 파일들의 해시 수집
tmpl_hashes = {}
for f in os.listdir(ASSETS):
    if f.startswith("tmpl_") and f.endswith(".png"):
        h = img_hash(os.path.join(ASSETS, f))
        tmpl_hashes[f] = h

# 해시 → 파일명 역매핑
hash_to_tmpls = {}
for fname, h in tmpl_hashes.items():
    hash_to_tmpls.setdefault(h, []).append(fname)

# 중복 해시 (폴백으로 복사된 것들)
fallback_hashes = {h: fnames for h, fnames in hash_to_tmpls.items() if len(fnames) > 1}
if fallback_hashes:
    print(f"  Found {len(fallback_hashes)} hash groups with duplicates:")
    for h, fnames in sorted(fallback_hashes.items(), key=lambda x: -len(x[1])):
        print(f"  [{h[:8]}] {len(fnames)} files share same image:")
        for fn in sorted(fnames):
            print(f"    - {fn}")
else:
    print("  No duplicate templates detected")

print()

# 3. 제품별 이미지 매핑 현황
print("=" * 60)
print("PRODUCT IMAGE MAPPING (by item_type)")
print("=" * 60)

# 각 제품의 이미지 해시 수집
product_hashes = {}
for entry in manifest:
    pid = entry["product_id"]
    path = os.path.join(ASSETS, f"{pid}.png")
    product_hashes[pid] = img_hash(path)

# item_type별로 어떤 해시를 쓰는지
from collections import defaultdict
type_hash_map = defaultdict(lambda: defaultdict(list))
for entry in manifest:
    it = entry["item_type"]
    style = entry["style_type"]
    h = product_hashes[entry["product_id"]]
    type_hash_map[it][h].append(entry["product_id"])

# 해시 → tmpl 역매핑
hash_to_tmpl_name = {h: fnames[0] for h, fnames in hash_to_tmpls.items()}

needs_generation = []
for it in sorted(type_hash_map.keys()):
    hashes = type_hash_map[it]
    unique_hashes = list(hashes.keys())
    tmpl_names = [hash_to_tmpl_name.get(h, "UNKNOWN") for h in unique_hashes]
    
    # 자신의 tmpl을 사용하는지 확인
    slug = it.replace(" ", "_")
    own_tmpls = [t for t in tmpl_names if slug in t]
    foreign_tmpls = [t for t in tmpl_names if slug not in t and t != "UNKNOWN"]
    
    product_count = sum(len(v) for v in hashes.values())
    
    if foreign_tmpls or not own_tmpls:
        status = "✗ FALLBACK"
        needs_generation.append(it)
    else:
        status = "✓ OK"
    
    print(f"  {status:12s} {it:25s} ({product_count:3d} products)  using: {tmpl_names}")

print()
print("=" * 60)
print(f"SUMMARY: {len(needs_generation)} item_types need proper images:")
for it in needs_generation:
    slug = it.replace(" ", "_")
    count = sum(1 for e in manifest if e["item_type"] == it)
    print(f"  - {it:25s}  ({count} products)")
print("=" * 60)
