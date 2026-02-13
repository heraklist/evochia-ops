# README_PHASE2_PREP

## Scope
Phase 2 prep is **imports-first** (CSV/OCR) with optional BAN/PREFER activation, while keeping Phase 1 deterministic path intact.

## Exact Commands (copy/paste)

### 1) Import CSV only
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --csv-input skills/evochia-ops/data/imports/supplier_x_prices.csv \
  --csv-profile skills/evochia-ops/suppliers/supplier_x.json
```

### 2) Import OCR only (stub demo)
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --ocr-input skills/evochia-ops/data/imports/supplier_y_ocr_rows.json \
  --ocr-profile skills/evochia-ops/suppliers/supplier_y.json
```

### 3) Import batch (CSV + OCR)
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --csv-input skills/evochia-ops/data/imports/supplier_x_prices.csv \
  --csv-profile skills/evochia-ops/suppliers/supplier_x.json \
  --ocr-input skills/evochia-ops/data/imports/supplier_y_ocr_rows.json \
  --ocr-profile skills/evochia-ops/suppliers/supplier_y.json
```

### 4) Offer Phase 1 (default rules)
```bash
python skills/evochia-ops/scripts/run_pipeline.py offer \
  --template-type B \
  --raw skills/evochia-ops/data/prices/sample_offers.json \
  --recipe skills/evochia-ops/data/recipes/sample_recipe.json \
  --request skills/evochia-ops/data/sample_proposal_request.json
```

### 5) Offer Phase 2 (BAN/PREFER ON)
```bash
python skills/evochia-ops/scripts/run_pipeline.py offer \
  --template-type B \
  --raw skills/evochia-ops/runs/<TS>/prices/price_quotes.json \
  --recipe skills/evochia-ops/data/recipes/sample_recipe_phase2.json \
  --request skills/evochia-ops/data/sample_proposal_request.json \
  --overrides skills/evochia-ops/config/overrides_phase2_demo.json \
  --phase 2 --enable-phase2-rules
```

### 6) Regression run
```bash
python skills/evochia-ops/scripts/run_regression_tests.py
```

### 7) Review apply (with supplier_id required)
```bash
python skills/evochia-ops/scripts/run_pipeline.py review \
  --needs-review skills/evochia-ops/runs/<TS>/prices/needs_review_ocr.json \
  --raw skills/evochia-ops/runs/<TS>/prices/raw_merged.json \
  --price-quotes skills/evochia-ops/runs/<TS>/prices/price_quotes.json \
  --supplier-id 4fsa \
  --apply-csv skills/evochia-ops/data/imports/review_patch_filled_demo.csv
```

---

## Input Contracts

### CSV required columns (source file)
Minimum for `import_csv.py` (mapped via supplier profile):
- `sku`
- `name`
- `category`
- `pack_size`
- `pack_unit`
- `price`
- `currency` (optional if default exists)
- `vat_rate` (optional if default exists)
- `in_stock` (optional default true)

### Mapping via supplier profile
`suppliers/<supplier_id>.json` defines `column_map` so input column names can differ per supplier.

### RawOffer minimal fields (post import)
- `offer_id`
- `supplier`
- `supplier_sku`
- `product_name`
- `price`
- `currency`
- `captured_at`
- `valid_until`

### PriceQuote minimal fields (post normalize)
- `offer_id`
- `product_id` (nullable pre-mapping)
- `supplier`
- `price`
- `price_per_base_unit`
- `captured_at`
- `valid_until`
- `pack_unit` normalized to base (`kg|lt|pcs`)

### captured_at / valid_until in imports
- `captured_at`: import timestamp (or explicit `--captured-at` if set)
- `valid_until`: `captured_at + catalog_valid_days` from supplier profile

### Alios canonical active CSV
- Active production input: `skills/evochia-ops/data/prices/alios/alios_round1_real.csv`
- Legacy/demo Alios datasets must stay under `skills/evochia-ops/data/prices/alios/archive/`

---

## Supplier profile how-to

Template (`suppliers/<supplier_id>.json`):
```json
{
  "supplier_id": "supplier_x",
  "layout_version": "v1",
  "layout_rules": {
    "required_anchors": ["ΤΙΜΟΛΟΓΙΟ", "ΠΕΡΙΓΡΑΦΗ", "ΠΟΣΟΤ"],
    "required_table_pattern": "line_items_v1"
  },
  "supplier_name": "Supplier X",
  "supplier_code": "SUPX",
  "column_map": {
    "supplier_sku": "sku",
    "product_name": "name",
    "category": "category",
    "pack_size": "pack_size",
    "pack_unit": "pack_unit",
    "price": "price",
    "currency": "currency",
    "vat_rate": "vat_rate",
    "in_stock": "in_stock"
  },
  "defaults": {
    "currency": "EUR",
    "vat_rate": 0.13,
    "tier": "standard",
    "max_age_days": 14
  }
}
```

Layout guard rule:
- If anchors/table pattern do not match profile v1 expectations:
  - issue code `SUPPLIER-LAYOUT-UNKNOWN`
  - all rows go to `needs_review`
  - no partial parse

### Add new supplier (steps 1–5)
1. Create `suppliers/<new_supplier_id>.json`.
2. Set `column_map` to match supplier CSV/OCR fields.
3. Set defaults (`currency`, `vat_rate`, `max_age_days`, `tier`).
4. Run `import` with this profile and inspect `needs_review` + `import_issues`.
5. Fix mapping/unit issues, rerun, then proceed to `prices/offer`.

---

## Override examples
From `config/overrides_phase2_demo.json`:
- BAN example:
  - rule: `BAN`
  - scope: `category`
  - match: `Γαλακτοκομικά`
  - supplier: `Supplier X`
- PREFER example:
  - rule: `PREFER`
  - scope: `category`
  - supplier: `Supplier Y`
  - `max_premium_pct`: 5

### reason_codes in decisions
- `LOCK_ENFORCED`: LOCK rule selected supplier
- `BAN_FILTERED`: candidates removed via BAN
- `PREFER_APPLIED`: preferred supplier selected within premium threshold

---

## Safety hardening implemented

### A) Strict unit normalization guard
If imported `pack_unit` is unknown (e.g. `τεμ`, `κιβ`, `συσκ`):
- add issue code: `IMPORT-UNSUPPORTED-UNIT`
- push row to `needs_review`
- do **not** silently convert

### B) Deterministic batch_id
`import_batch.json` batch id includes:
- timestamp
- `supplier_id`
- hash of input file

Format example:
`BATCH-supplier_x-20260211-203812-a1b2c3d4e5`

This reduces duplicate ingestion risk and improves traceability.

## Persist storage (production paths)
- `mappings/supplier_sku_map/<supplier_id>.json`
- `mappings/unit_rules/<supplier_id>.json`
- `mappings/catalog_aliases.jsonl` (append-only)
- `audit/mapping_persist_log.jsonl` (append-only)

Safety:
- `review --apply-csv` without `--supplier-id` => BLOCK
- `set_product_id` missing => unresolved row (no crash)
- sku_map conflict => BLOCK + audit entry
