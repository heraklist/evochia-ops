# REAL_SUPPLIER_ONBOARDING_REPORT

## Scope
Phase 3.5 real supplier onboarding for **TheMart** using real CSV input.

## Input
- Requested input path: `/mnt/data/oporopoleio_unified.csv`
- Host-accessible file used in run: `C:\Users\herax\Desktop\oporopoleio_unified.csv`
- Rows: **208**
- Columns (source): `κωδικός προϊόντος | όνομα | τιμή | link | κατάσταση_diff | πηγές`

## Supplier profile changes
Updated: `skills/evochia-ops/suppliers/themart.json`

- Column map:
  - `supplier_sku = κωδικός προϊόντος`
  - `raw_desc = όνομα`
  - `net_price_raw = τιμή`
  - `url = link`
  - `diff_status = κατάσταση_diff`
  - `sources = πηγές`
- Price parse policy:
  - parses net textual price like `3,07€ χωρίς ΦΠΑ` -> `3.07 EUR`
- Pack/unit inference policy (explicit, deterministic):
  - `(###g|gr)` -> `pack_size=###`, `pack_unit=g`
  - `(###kg)` -> `pack_size=###`, `pack_unit=kg`
  - parentheses like `(bio)` / `(11cm)` ignored as non-pack
  - keyword `γλαστράκι` -> `pack_size=1`, `pack_unit=pcs`
  - fallback policy: `themart_assume_per_kg=true` -> `pack_size=1`, `pack_unit=kg`
- No silent conversions beyond above rules.

## Run plan executed
1. Import:
   - `run_pipeline.py import --csv-input C:/Users/herax/Desktop/oporopoleio_unified.csv --csv-profile skills/evochia-ops/suppliers/themart.json`
2. Baseline map/prices:
   - `run_pipeline.py prices ... --phase 3 --enable-phase2-rules --policies ...`
3. Review patch (sku_map only):
   - Applied CSV patch with `persist_mode=sku_map`
   - No alias / no unit_rule persistence
4. Rerun offer (Phase 3, policies ON) and filing:
   - `proposal_validation = PASS`
   - `filing_status = FILED`
   - Telegram reply generated

## Metrics (before/after)
- Baseline needs_review (map/prices): **188**
- After review+persist sku_map: **0**
- Target (`<=10`) achieved: **YES**

## Mapping persistence
- Updated: `skills/evochia-ops/mappings/supplier_sku_map/themart.json`
- Entries before: **20**
- Entries after: **208**
- Mappings added in this onboarding: **188**
- Append-only audit log updated:
  - `skills/evochia-ops/audit/mapping_persist_log.jsonl`

## Remaining issues
- None blocking for current onboarded dataset.

## Validation
- `REGRESSION_PASS`
