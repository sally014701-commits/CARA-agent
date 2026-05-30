import sqlite3
import json
import time
import os
import sys

# Load .env manually
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

import voyageai

VOYAGE_API_KEY = os.environ.get('VOYAGE_API_KEY')
if not VOYAGE_API_KEY:
    print("ERROR: VOYAGE_API_KEY not found")
    sys.exit(1)

client = voyageai.Client(api_key=VOYAGE_API_KEY)

DB_PATH = os.getenv("DB_PATH", "./cara.db")
BATCH_SIZE = 5
BATCH_DELAY = 21   # 3 RPM free tier: 1 req per 20s
RETRY_DELAY = 30
MODEL = 'voyage-3-lite'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT product_id, product_name, brand, keywords FROM products WHERE embedding IS NULL ORDER BY product_id")
rows = c.fetchall()

total = len(rows)
print(f"Target: {total} products to embed")

processed = 0
for i in range(0, total, BATCH_SIZE):
    batch = rows[i:i + BATCH_SIZE]
    texts = []
    ids = []
    for product_id, product_name, brand, keywords in batch:
        name = product_name or ''
        br = brand or ''
        kw = keywords or ''
        text = f"{name} {br} {kw}".strip()
        texts.append(text)
        ids.append(product_id)

    while True:
        try:
            result = client.embed(texts, model=MODEL)
            embeddings = result.embeddings
            break
        except Exception as e:
            err_str = str(e)
            if '429' in err_str or 'rate' in err_str.lower() or 'RateLimit' in err_str:
                print(f"  Rate limit hit -- waiting {RETRY_DELAY}s before retry...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  Error: {e}")
                raise

    for pid, emb in zip(ids, embeddings):
        c.execute("UPDATE products SET embedding = ? WHERE product_id = ?",
                  (json.dumps(emb), pid))
    conn.commit()

    processed += len(batch)
    batch_num = i // BATCH_SIZE + 1
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"  Batch {batch_num}/{total_batches}: {len(batch)} done ({processed}/{total})")

    if i + BATCH_SIZE < total:
        time.sleep(BATCH_DELAY)

c.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
count = c.fetchone()[0]
print(f"\nDone! embedding IS NOT NULL count: {count}")
conn.close()
