---
name: evochia-ops
description: End-to-end catering operations pipeline for Evochia: intake and normalize supplier prices, map to canonical products, cost recipes, apply Phase-1 sourcing (LOCK then LOWEST), and generate proposal-ready outputs. Use for requests about costing, supplier selection, recipe-to-cost conversion, and proposal preparation from market data.
---

# Evochia Ops

## Scope (Phase 1)
Run deterministic pipeline steps:
1. Intake prices (TheMart/manual) into raw offers
2. Normalize and map aliases to canonical products (manual-first)
3. Cost recipes with packaging/labor
4. Optimize sourcing with active rules: `LOCK -> LOWEST`
5. Produce proposal input payloads for template generator

## Safety / Determinism Rules
- Never guess missing prices or mandatory mappings.
- If required fields are missing, stop and ask.
- Keep tier separation (`standard`, `premium`) unless explicitly overridden.
- Phase 1 sourcing executes only `LOCK -> LOWEST`.
- `BAN` and `PREFER` are hooks only (Phase 2+).

## Inputs / Outputs
- Raw input schema (pre-mapping): `schemas/raw_offer.json`
- Mapped price schema: `schemas/price_quote.json`
- Canonical product schema: `schemas/catalog_item.json`
- Recipe schema: `schemas/recipe.json`
- Cost output schema: `schemas/cost_breakdown.json`
- Sourcing decision schema: `schemas/sourcing_decision.json`
- Proposal input schema: `schemas/proposal_input.json`

## Config
- `config/defaults.json`: costing and VAT defaults
- `config/overrides.json`: sourcing overrides (Phase 1 uses LOCK only)

## Scripts
- `scripts/normalize_prices.py` - normalize raw supplier rows
- `scripts/map_offers.py` - manual-first alias -> product_id mapping and needs_review queue
- `scripts/cost_recipe.py` - compute recipe cost breakdown
- `scripts/optimize_sourcing.py` - Phase 1 sourcing (`LOCK -> LOWEST`) + validity policy
- `scripts/generate_proposal_payload.py` - create proposal-ready JSON payload with pre-flight validation
- `scripts/render_docx.py` - strict placeholder-based DOCX render (PASS-only)
- `scripts/convert_doc_to_docx.ps1` - convert legacy .doc reference files to .docx

## Command Contract (Current interface)
Use explicit runner commands:
> Note: Phase 2 rules are OFF by default unless explicitly enabled.
- `import` → imports-first ingress (CSV/OCR) to unified price quotes
- `prices` → price intake/export only (Phase-1 deterministic path)
- `cost` → recipe to cost only
- `offer` → cost + payload + render (A/B/C)

Examples:
- `python scripts/run_pipeline.py prices --raw data/prices/sample_offers.json`
- `python scripts/run_pipeline.py cost --recipe data/recipes/sample_recipe.json --offers data/prices/sample_offers_mapped.json --decisions data/prices/sample_decisions.json`
- `python scripts/run_pipeline.py offer --template-type B --raw data/prices/sample_offers.json --recipe data/recipes/sample_recipe.json --request data/sample_proposal_request.json`

Runner artifacts are written under `runs/<YYYYMMDD-HHMM>/<type>/` and include:
- final output (DOCX/HTML)
- proposal payload/validation/issues
- `run_summary.txt` with stale/anomaly/lock flags

## Regression
Run local golden regression checks:
- `python scripts/run_regression_tests.py`

## Current status
Phase 1 clean ship complete (hardening frozen).
