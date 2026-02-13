# README_PROPOSALS

Deterministic filing tree for proposal outputs.

## Path

`skills/evochia-ops/proposals/YYYY/MM/<client_slug>/<event_date>/`

## Filename rule

`<event_date>_<client_slug>_<service_tag>_<template_tag>_<run_id>.<docx|html>`

- `client_slug`: latin lowercase, accents removed, spaces->`-`
- `service_tag`: `DEL` (delivery), `PC` (private_chef), `CAT` (catering/default)
- `template_tag`: `A|B|C`
- `run_id`: run timestamp directory (e.g. `20260212-0805`)

If filename already exists, deterministic suffix is appended: `_v2`, `_v3`, ...

## Copied artifacts

- final output (`docx|html`)
- `proposal_payload.json`
- `proposal_validation.json`
- `proposal_issues.json`
- `render_validation.json`
- `render_issues.json`
- `run_summary.txt`
- `decisions.json` (when present)
- `template_selection.json`

## Safety

- Copy-only: no move/delete from `runs/`
- Filing blocked when render compliance status is not `PASS`

## Folder manifest

Each filing folder keeps `manifest.json` with append-only entries including:

- list of filed artifacts
- source run path
- compliance status
- `template_selection.rule_fired`
- filing version (`v1`, `v2`, `v3`, ...)

## Optional client override

`run_pipeline.py offer` supports `--client "..."` for filing, used when request has missing/unstable client name.
