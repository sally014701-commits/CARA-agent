# Product Card UI Specification

## Image Area Rules (enforced in CARA.html)

```html
<div class="product-img-wrap">
  <img class="product-img"
       src="assets/products/{product_id}.png"
       alt="{product_name}"
       loading="lazy"
       decoding="async" />
</div>
```

### CSS Rules
```css
.product-img-wrap {
  width: 100%;
  aspect-ratio: 1;
  background: #ffffff;        /* clean white — no fake backgrounds */
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;              /* consistent padding on all sides */
  overflow: hidden;
}
.product-img {
  width: 100%;
  height: 100%;
  object-fit: contain;        /* never crop, never stretch */
  object-position: center;
  display: block;
}
```

### Rules
- Image area background is always `#ffffff` — never a gradient, never a blob
- `object-fit: contain` — product always fully visible, never cropped
- Consistent 12px padding on all sides for breathing room
- Same rules apply to the drawer detail view (`.drawer-img-wrap` / `.drawer-img`)

## Card Structure

```
.product-card
  └── .product-img-wrap
        └── <img class="product-img">   ← real PNG from assets/products/
  └── .product-body
        ├── .product-kicker             ← item_type (uppercase, muted)
        ├── .product-name               ← product name
        ├── .product-price              ← ₩ formatted, tnum
        └── .product-meta
              ├── .rating               ← ★ N.N · RAG N.NN
              └── .style-tag            ← practical | design
```

## Image Source
All product images are sourced from `assets/products/{product_id}.png`.
Templates are in `assets/products/tmpl_{item_type}_{style}.png`.
Mapping is defined in `product_manifest.json`.
