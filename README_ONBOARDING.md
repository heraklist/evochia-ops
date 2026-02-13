# README_ONBOARDING

Phase 3.3 Supplier Onboarding Kit (Telegram-first ops)

## Command (copy/paste)

```bash
python skills/evochia-ops/scripts/run_pipeline.py onboard-supplier \
  --supplier-id demo_supplier_kappa \
  --display-name "Demo Supplier Kappa" \
  --mode both \
  --run-tests
```

## Generated outputs

- Supplier profile skeleton:
  - `skills/evochia-ops/suppliers/<supplier-id>.json`
- Fixture folder:
  - `skills/evochia-ops/data/imports/fixtures/<supplier-id>/`
  - `xlsx_v1_complete.json`
  - `xlsx_v1_broken_missing_price.json`
  - `pdfocr_v1_complete.json`
  - `pdfocr_v1_layout_unknown.json`
  - `ONBOARDING_REPORT.md`
- Run summary:
  - `skills/evochia-ops/runs/<ts>/onboarding/run_summary.txt`
  - `skills/evochia-ops/runs/<ts>/onboarding/onboarding_summary.json`

## Determinism / safety

- No overwrite by default: existing files get `_v2`, `_v3`, ...
- Unsupported units remain `needs_review` (`IMPORT-UNSUPPORTED-UNIT`)
- Missing critical fields remain `needs_review` (`IMPORT-MISSING-CRITICAL-FIELD`)
- Layout mismatch is blocked (`SUPPLIER-LAYOUT-UNKNOWN`)

## Next actions after skeleton

1. Put real headers in `column_map`
2. Tune `required_anchors` + `required_table_pattern`
3. Extend `unit_map` for supplier-specific units
4. Re-run `onboard-supplier --run-tests`
5. Start imports through `run_pipeline.py import`
