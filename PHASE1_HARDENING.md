# PHASE1_HARDENING (MUST-only)

Date: 2026-02-13
Scope: Strict Phase 1 hardening only (no refactor, no new features, no new subcommands).

## Applied commits

1. `1c820a2` — Validity exactness
   - `config/defaults.json`: `phase1_price_validity.max_age_days` changed **15 -> 14**
   - `block_after_days` remains **28**

2. `6f1f8e8` — Runs packaging hygiene
   - Removed tracked `runs/` artifacts from repo
   - Added deterministic cleaner: `scripts/clean_runs.py`
   - Added samples path: `data/samples/phase30/`
   - Added ignore rule: `runs/`

3. `7ae8e0d` — Templates de-dup
   - Kept canonical reference files under `templates/reference/`
   - Removed duplicate `ref_*` files from `templates/` root

4. `4f8d211` — Pycache cleanup
   - Removed Python cache artifacts
   - Added ignore rules: `__pycache__/`, `**/__pycache__/`, `*.pyc`

## Packaging state (now)

- `skills/evochia-ops/runs/` is ignored for packaging/repo hygiene
- Golden sample artifacts live at:
  - `skills/evochia-ops/data/samples/phase30/diff_report.json`
  - `skills/evochia-ops/data/samples/phase30/run_summary.txt`

## Phase 1 non-negotiables (active)

- Price validity: **14 days warning horizon**, **28 days block horizon**
- Proposal rendering: **PASS-only render**
- Policy: **No guessing** (missing criticals => block and ask)

## How to verify

Run exactly:

```bash
python scripts/run_regression_tests.py
```

Expected result: `REGRESSION_PASS`
