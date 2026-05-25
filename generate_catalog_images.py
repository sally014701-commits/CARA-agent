"""
generate_catalog_images.py
Generates catalog-style PNG product images using OpenAI DALL-E 3.
- Pure white background
- No gradients, no decorative blobs, no atmospheric backgrounds
- Consistent scale and padding
- SKU variants: same base geometry, different colors/materials
- Saves to assets/products/{product_id}.png
"""
import json
import os
import time
import requests
from openai import OpenAI

client = OpenAI()

ASSETS_DIR = "assets/products"
os.makedirs(ASSETS_DIR, exist_ok=True)

# item_type -> (practical_prompt, design_prompt)
ITEM_PROMPTS = {
    "smartphones": (
        "A single modern smartphone, matte black finish, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium smartphone, glossy midnight blue finish, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "laptops": (
        "A single open laptop computer, silver aluminum body, 3/4 angle view on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium laptop, space gray finish, 3/4 angle view on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "earbuds": (
        "A pair of wireless earbuds with charging case, white color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A pair of premium wireless earbuds with charging case, matte black color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "tablets": (
        "A single tablet computer, silver finish, screen facing up on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium tablet, space gray finish, screen facing up on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "smartwatches": (
        "A single smartwatch, black band with silver case, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium smartwatch, midnight blue band with gold case, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "bags": (
        "A single tote bag, beige canvas material, standing upright on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single designer tote bag, structured black leather, standing upright on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "sneakers": (
        "A single pair of white sneakers, clean minimal design, side view on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single pair of designer sneakers, black with contrast sole, side view on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "jeans": (
        "A single pair of classic blue denim jeans, folded flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single pair of premium dark wash slim jeans, folded flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "dresses": (
        "A single simple cotton dress, light gray color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single elegant silk dress, deep navy color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "jackets": (
        "A single utility jacket, olive green color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium bomber jacket, black leather, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "moisturizers": (
        "A single white pump bottle of moisturizer, minimalist label, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium glass jar of moisturizer, gold lid, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "serums": (
        "A single dropper bottle of face serum, clear glass, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium amber glass dropper bottle of serum, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "sunscreens": (
        "A single white tube of sunscreen, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium sunscreen stick in sleek packaging, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "shampoos": (
        "A single white plastic shampoo bottle, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium matte black shampoo bottle, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "lip balms": (
        "A single small cylindrical lip balm tube, white packaging, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium lip balm in gold metal case, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "air purifiers": (
        "A single white cylindrical air purifier, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium air purifier, matte white with black accents, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "coffee makers": (
        "A single drip coffee maker, black and silver, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium pour-over coffee maker, matte black with glass carafe, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "desk lamps": (
        "A single adjustable desk lamp, white metal, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium architect desk lamp, matte black with brass accents, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "pillows": (
        "A single white bed pillow, square shape, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium linen pillow, natural beige color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "storage boxes": (
        "A single white cardboard storage box with lid, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium fabric storage box, charcoal gray with leather handles, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "dumbbells": (
        "A single pair of rubber-coated dumbbells, black color, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single pair of premium chrome dumbbells, polished silver, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "yoga mats": (
        "A single rolled yoga mat, purple color, standing upright on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium cork yoga mat, natural brown, rolled and standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "running shoes": (
        "A single pair of running shoes, white with gray accents, side view on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single pair of premium running shoes, all-black with reflective details, side view on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "resistance bands": (
        "A set of resistance bands, multiple colors, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A set of premium resistance bands, black with gold branding, flat lay on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
    "water bottles": (
        "A single stainless steel water bottle, white matte finish, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot",
        "A single premium insulated water bottle, matte black with copper accents, standing on pure white background, product photography, catalog style, no shadows, no gradients, centered, professional studio shot"
    ),
}

def generate_image(prompt, output_path):
    """Generate a single product image using DALL-E 3."""
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        img_data = requests.get(image_url, timeout=30).content
        with open(output_path, "wb") as f:
            f.write(img_data)
        print(f"  ✓ {output_path}")
        return True
    except Exception as e:
        print(f"  ✗ {output_path}: {e}")
        return False

def main():
    with open("products.json") as f:
        products = json.load(f)

    # Group products by item_type and style_type
    # We generate one representative image per (item_type, style_type) pair
    # Then copy/assign to all products with that combination
    
    # First, collect all unique (item_type, style_type) combos
    combos = {}
    for p in products:
        key = (p["item_type"], p["style_type"])
        if key not in combos:
            combos[key] = []
        combos[key].append(p["product_id"])

    print(f"Generating images for {len(combos)} unique (item_type, style_type) combinations...")
    print(f"Total products: {len(products)}")
    
    # Generate one image per combo, then copy to all products in that combo
    import shutil
    
    generated_templates = {}  # (item_type, style_type) -> template_path
    
    for (item_type, style_type), product_ids in sorted(combos.items()):
        prompts = ITEM_PROMPTS.get(item_type)
        if not prompts:
            print(f"  ! No prompt for {item_type}, skipping")
            continue
        
        prompt = prompts[0] if style_type == "practical" else prompts[1]
        
        # Use the first product_id as the template
        template_id = product_ids[0]
        template_path = os.path.join(ASSETS_DIR, f"{template_id}.png")
        
        # Check if already generated
        if os.path.exists(template_path) and os.path.getsize(template_path) > 10000:
            print(f"  ~ {item_type}/{style_type}: using existing {template_id}.png")
            generated_templates[(item_type, style_type)] = template_path
        else:
            print(f"  Generating {item_type}/{style_type} -> {template_id}.png")
            success = generate_image(prompt, template_path)
            if success:
                generated_templates[(item_type, style_type)] = template_path
                time.sleep(1)  # Rate limit
        
        # Copy template to all other products in this combo
        if (item_type, style_type) in generated_templates:
            src = generated_templates[(item_type, style_type)]
            for pid in product_ids[1:]:
                dst = os.path.join(ASSETS_DIR, f"{pid}.png")
                if not os.path.exists(dst) or os.path.getsize(dst) < 10000:
                    shutil.copy2(src, dst)
    
    print(f"\n✓ Done. Images in {ASSETS_DIR}/")
    
    # Verify all products have images
    missing = []
    for p in products:
        path = os.path.join(ASSETS_DIR, f"{p['product_id']}.png")
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            missing.append(p["product_id"])
    
    if missing:
        print(f"  ! Missing images for: {missing[:10]}...")
    else:
        print(f"  ✓ All {len(products)} product images present")

if __name__ == "__main__":
    main()
