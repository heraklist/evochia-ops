# ONBOARDING_SUPPLIER (v1 playbook)

## Goal
Add a new supplier safely with deterministic behavior.

## Steps
1. **Add profile v1**
   - Create `suppliers/<supplier_id>.json`
   - Required: `supplier_id`, `layout_version: v1`, `layout_rules`, `column_map`, `unit_map`, `defaults`

2. **Add fixtures (2 files)**
   - one **complete** fixture (expected parse OK)
   - one **broken** fixture (expected BLOCK/needs_review)
   - put under `data/imports/ocr_fixtures/`

3. **Run fixture tests**
   ```bash
   python skills/evochia-ops/scripts/run_supplier_fixture_tests.py
   ```

4. **If `SUPPLIER-LAYOUT-UNKNOWN` appears**
   - Do not patch parser in place.
   - Create/extend profile to `layout_version: v2` with updated anchors/table pattern.
   - Add/adjust fixtures for v2.
   - Re-run fixture tests.

5. **Operational run**
   - run `import`
   - inspect `run_summary.txt`
   - if needed run `review` with patch and re-run
   - always pass `--supplier-id <supplier_id>` on `review --apply-csv`

## Persist paths (production)
- SKU mappings: `skills/evochia-ops/mappings/supplier_sku_map/<supplier_id>.json`
- Unit rules: `skills/evochia-ops/mappings/unit_rules/<supplier_id>.json`
- Catalog aliases (append-only): `skills/evochia-ops/mappings/catalog_aliases.jsonl`
- Persist audit log (append-only): `skills/evochia-ops/audit/mapping_persist_log.jsonl`

## Constraints (always)
- No fuzzy matching
- No silent conversions
- Unsupported/unknown units => `needs_review`
- Phase 1 regression must remain PASS
