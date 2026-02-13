# REAL_SUPPLIER_ONBOARDING_REPORT_ALIOS

## Scope
Phase 3.5 real supplier onboarding for **Alios** (REAL XLSX round merge).

## Inputs
Used real XLSX files from repo:
- `skills/evochia-ops/data/prices/alios/alios_dry_sushi_2025_REAL.xlsx`
- `skills/evochia-ops/data/prices/alios/alios_frozen_sushi_2025_REAL.xlsx`

Requested `*_FILLED_DEMO.xlsx` names were not present; REAL equivalents were used.

## Merged Round1 artifact
- `skills/evochia-ops/data/prices/alios/alios_round1.csv`
- Rows merged: **59**
- Category tags applied: `dry` / `frozen`

## Supplier profile changes
Updated `skills/evochia-ops/suppliers/alios.json` (v1 strict XLSX profile remains active):
- `xlsx.*` block in use (`sheet/header_row/column_map/required_columns/stop_rules`)
- `unit_map` extended for operational real XLSX units:
  - includes `G -> g` and `ML -> ml` (plus existing KG/LT/PCS)
- Guard behavior unchanged:
  - missing critical -> `IMPORT-MISSING-CRITICAL-FIELD`
  - unsupported unit -> `IMPORT-UNSUPPORTED-UNIT`
  - no silent conversions

## Run plan + metrics
1) Baseline map/prices run (`phase=3`, policies ON) on merged raw basket
- baseline `needs_review`: **40**

2) Review patch apply (`persist_mode=sku_map` only, `--supplier-id alios`)
- helper patch CSVs:
  - `skills/evochia-ops/data/imports/alios_review_filled_real.csv`
  - `skills/evochia-ops/data/imports/alios_review_filled_real_round2.csv`
- no alias / no unit_rule persistence

3) Rerun same basket
- final `needs_review`: **0** (target `<=10` achieved)

4) Offer + filing + Telegram reply
- intake chain executed with `--run-offer --file-proposal --reply`
- result: **PASS + FILED**

## Mapping persistence
- Updated: `skills/evochia-ops/mappings/supplier_sku_map/alios.json`
- Count before onboarding: **30**
- Count after onboarding: **90**
- Added in this onboarding wave: **60**
- Audit append-only updated:
  - `skills/evochia-ops/audit/mapping_persist_log.jsonl`

## Remaining issues
- None blocking for this round basket.

## Validation
- `REGRESSION_PASS`
