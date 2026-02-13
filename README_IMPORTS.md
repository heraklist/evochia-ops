# README_IMPORTS

Operator copy/paste guide for all ingress types using the shared **RawOffer** contract.

---

## 1) CSV import

### Required inputs
- CSV file (supplier price list)
- Supplier profile JSON

### Example command
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --csv-input skills/evochia-ops/data/imports/supplier_x_prices.csv \
  --csv-profile skills/evochia-ops/suppliers/supplier_x.json
```

### Expected outputs (`runs/<ts>/prices/`)
- `import_batch_csv.json`
- `raw_from_csv.json`
- `raw_merged.json`
- `price_quotes.json`
- `needs_review_import.json` (if any)
- `run_summary.txt`

---

## 2) XLSX import

### Required inputs
- XLSX file (supplier price list)
- Supplier profile JSON with `xlsx.*` config

### Example command
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --xlsx-input skills/evochia-ops/data/prices/alios/alios_dry_sushi_2025_REAL.xlsx \
  --xlsx-profile skills/evochia-ops/suppliers/alios.json
```

### Expected outputs (`runs/<ts>/prices/`)
- `import_batch_xlsx.json`
- `raw_from_xlsx.json`
- `raw_merged.json`
- `price_quotes.json`
- `needs_review_xlsx.json` (if any)
- `run_summary.txt`

---

## 3) OCR structured import

### Required inputs
- Structured OCR JSON input
- Supplier profile JSON

### Example command
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --ocr-input skills/evochia-ops/data/imports/ocr_fixtures/alios_v1_complete.json \
  --ocr-profile skills/evochia-ops/suppliers/alios.json
```

### Expected outputs (`runs/<ts>/prices/`)
- `import_batch_ocr.json`
- `raw_from_ocr.json`
- `raw_merged.json`
- `price_quotes.json`
- `needs_review_ocr.json` (if any)
- `run_summary.txt`

---

## 4) PDF-OCR structured import

### Required inputs
- Structured PDF-OCR JSON input
- Supplier profile JSON (with layout guards)

### Example command
```bash
python skills/evochia-ops/scripts/run_pipeline.py import \
  --pdf-ocr-input skills/evochia-ops/data/imports/pdf_fixtures/alios_pdf_price_list_fixture.json \
  --pdf-ocr-profile skills/evochia-ops/suppliers/alios.json
```

### Expected outputs (`runs/<ts>/prices/`)
- `import_batch_pdf_ocr.json`
- `raw_from_pdf_ocr.json`
- `raw_merged.json`
- `price_quotes.json`
- `needs_review_pdf_ocr.json` (if any)
- `run_summary.txt`

---

## Next steps (same flow for all ingress types)

1. **Normalize** (already included in `run_pipeline.py import` via `normalize_import_batch.py`)
2. **Review** (export skeleton CSV)
3. Fill CSV (`set_product_id`, unit fixes) → apply patch → persist `sku_map`
4. Rerun **offer** (`phase=3`, policies ON) with filing + Telegram reply

### Review / apply example
```bash
python skills/evochia-ops/scripts/run_pipeline.py review \
  --needs-review skills/evochia-ops/runs/<TS>/prices/needs_review_import.json \
  --raw skills/evochia-ops/runs/<TS>/prices/raw_merged.json \
  --price-quotes skills/evochia-ops/runs/<TS>/prices/price_quotes.json \
  --supplier-id alios \
  --export-csv-skeleton skills/evochia-ops/data/imports/review_patch_skeleton.csv
```

```bash
python skills/evochia-ops/scripts/run_pipeline.py review \
  --needs-review skills/evochia-ops/runs/<TS>/prices/needs_review_import.json \
  --raw skills/evochia-ops/runs/<TS>/prices/raw_merged.json \
  --price-quotes skills/evochia-ops/runs/<TS>/prices/price_quotes.json \
  --supplier-id alios \
  --apply-csv skills/evochia-ops/data/imports/review_patch_filled.csv
```

### Offer + file + reply example
```bash
python skills/evochia-ops/scripts/run_pipeline.py intake \
  --text "2026-03-20 | 40 guests | DEL finger | budget 25 per person | client: Demo" \
  --run-offer --file-proposal --reply
```

---

## Troubleshooting (short)

- `SUPPLIER-LAYOUT-UNKNOWN`
  - Bump `layout_version` and update `required_anchors` / `required_table_pattern` (new v2 profile).

- `IMPORT-UNSUPPORTED-UNIT`
  - Add/adjust `unit_map` or resolve via review patch.
  - **No silent conversions**.

- `IMPORT-MISSING-CRITICAL-FIELD`
  - Verify `column_map`, file headers, and `required_columns`.

---

## Daily Ops checklist

1. Import (CSV/XLSX/OCR/PDF-OCR)
2. Review (export → fill → apply → persist)
3. Offer (phase=3, balanced default)
4. File (manifest + versioning)
5. Archive/log (runs immutable, proposals filed)
