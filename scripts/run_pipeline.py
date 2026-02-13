import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TEMPLATES = ROOT / "templates"
RUNS = ROOT / "runs"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    return r.stdout.strip()


def now_run_dir(kind: str):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS / ts / kind
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_json(path):
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def write_summary(path: Path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _vat_summary(rows):
    c13 = sum(1 for r in rows if float(r.get("vat_rate", 0) or 0) == 0.13)
    c24 = sum(1 for r in rows if float(r.get("vat_rate", 0) or 0) == 0.24)
    return f"13:{c13},24:{c24}"


def _parse_iso(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _guard_active_dataset_name(path_str: str):
    p = Path(path_str)
    name = p.name.lower()
    if "alios" in [x.lower() for x in p.parts] and "data" in [x.lower() for x in p.parts] and "prices" in [x.lower() for x in p.parts]:
        bad = ("demo" in name) or ("legacy" in name) or (name == "alios_round1.csv")
        if bad:
            raise RuntimeError(f"DATASET-NAME-NOT-ALLOWED: {path_str}")


def cmd_import(args):
    out = now_run_dir("prices")
    raw_csv_json = out / "raw_from_csv.json"
    raw_ocr_json = out / "raw_from_ocr.json"
    batch_csv = out / "import_batch_csv.json"
    batch_ocr = out / "import_batch_ocr.json"
    raw_merged = out / "raw_merged.json"
    price_quotes = out / "price_quotes.json"
    needs_review = out / "needs_review_import.json"
    import_issues = out / "import_issues.json"
    ocr_needs = out / "needs_review_ocr.json"
    ocr_issues = out / "issues_ocr.json"
    xlsx_needs = out / "needs_review_xlsx.json"
    xlsx_issues = out / "issues_xlsx.json"
    pdf_needs = out / "needs_review_pdf_ocr.json"
    pdf_issues = out / "issues_pdf_ocr.json"

    merged = []
    files = []

    csv_pairs = []
    if args.csv_input:
        csv_pairs.append((args.csv_input, args.csv_profile, raw_csv_json, batch_csv))
    if args.csv_input_2:
        csv_pairs.append((args.csv_input_2, args.csv_profile_2, out / "raw_from_csv_2.json", out / "import_batch_csv_2.json"))

    for cinput, cprofile, raw_out, batch_out in csv_pairs:
        _guard_active_dataset_name(cinput)
        run([
            sys.executable,
            str(SCRIPTS / "import_csv.py"),
            "--input",
            cinput,
            "--supplier-profile",
            cprofile,
            "--out",
            str(raw_out),
            "--batch-out",
            str(batch_out),
        ])
        merged.extend(load_json(raw_out))
        files.append(str(raw_out))

    if getattr(args, "xlsx_input", None):
        raw_xlsx_json = out / "raw_from_xlsx.json"
        batch_xlsx = out / "import_batch_xlsx.json"
        needs_xlsx = out / "needs_review_xlsx.json"
        issues_xlsx = out / "issues_xlsx.json"
        run([
            sys.executable,
            str(SCRIPTS / "import_xlsx.py"),
            "--input",
            args.xlsx_input,
            "--supplier-profile",
            args.xlsx_profile,
            "--out",
            str(raw_xlsx_json),
            "--batch-out",
            str(batch_xlsx),
            "--needs-review",
            str(needs_xlsx),
            "--issues-out",
            str(issues_xlsx),
        ])
        merged.extend(load_json(raw_xlsx_json))
        files.append(str(raw_xlsx_json))

    if args.ocr_input:
        run([
            sys.executable,
            str(SCRIPTS / "import_ocr.py"),
            "--input",
            args.ocr_input,
            "--supplier-profile",
            args.ocr_profile,
            "--out",
            str(raw_ocr_json),
            "--batch-out",
            str(batch_ocr),
            "--needs-review",
            str(ocr_needs),
            "--issues-out",
            str(ocr_issues),
        ])
        merged.extend(load_json(raw_ocr_json))
        files.append(str(raw_ocr_json))

    if getattr(args, "pdf_ocr_input", None):
        raw_pdf_json = out / "raw_from_pdf_ocr.json"
        batch_pdf = out / "import_batch_pdf_ocr.json"
        run([
            sys.executable,
            str(SCRIPTS / "import_pdf_ocr.py"),
            "--input",
            args.pdf_ocr_input,
            "--supplier-profile",
            args.pdf_ocr_profile,
            "--out",
            str(raw_pdf_json),
            "--batch-out",
            str(batch_pdf),
            "--needs-review",
            str(pdf_needs),
            "--issues-out",
            str(pdf_issues),
        ])
        merged.extend(load_json(raw_pdf_json))
        files.append(str(raw_pdf_json))

    raw_merged.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    run([
        sys.executable,
        str(SCRIPTS / "normalize_import_batch.py"),
        "--input",
        str(raw_merged),
        "--out",
        str(price_quotes),
        "--needs-review",
        str(needs_review),
        "--issues-out",
        str(import_issues),
    ])

    needs = load_json(needs_review)
    imp_issues = load_json(import_issues)
    o_needs = load_json(ocr_needs)
    o_issues = load_json(ocr_issues)
    x_needs = load_json(xlsx_needs)
    x_issues = load_json(xlsx_issues)
    p_needs = load_json(pdf_needs)
    p_issues = load_json(pdf_issues)
    batches = []
    for b in [batch_csv, out / "import_batch_csv_2.json", out / "import_batch_xlsx.json", batch_ocr, out / "import_batch_pdf_ocr.json"]:
        if b.exists():
            batches.append(load_json(b))
    quotes = load_json(price_quotes)
    suppliers = sorted({b.get("supplier_id", "unknown") for b in batches})
    layouts = sorted({b.get("layout_version", "n/a") for b in batches})
    batch_ids = [b.get("batch_id", "") for b in batches]
    lines_needs = len(needs) + len(o_needs) + len(x_needs) + len(p_needs)
    rows_with_sku = sum(1 for r in merged if str(r.get("supplier_sku", "")).strip())
    rows_without_sku = len(merged) - rows_with_sku
    summary = [
        "run_type=import",
        f"raw_rows={len(merged)}",
        f"rows_with_sku={rows_with_sku}",
        f"rows_without_sku={rows_without_sku}",
        f"sources={','.join(files)}",
        f"supplier_id={','.join(suppliers)}",
        f"layout_version={','.join(layouts)}",
        f"batch_id={','.join(batch_ids)}",
        f"price_quotes={price_quotes}",
        f"lines_ok={len(quotes)}",
        f"lines_needs_review={lines_needs}",
        f"vat_summary={_vat_summary(quotes)}",
        f"needs_review={lines_needs}",
        f"issues={len(imp_issues) + len(o_issues) + len(x_issues) + len(p_issues)}",
        (f"next_action=run review to resolve {lines_needs} lines" if lines_needs > 0 else "next_action=proceed to prices/offer"),
    ]
    write_summary(out / "run_summary.txt", summary)
    print(str(out))


def cmd_review(args):
    out = now_run_dir("review")
    review_summary = out / "review_summary.json"
    patch_template = out / "mapping_patch.template.json"
    out_quotes = out / "price_quotes.json"
    out_needs = out / "needs_review.json"
    out_issues = out / "review_issues.json"
    audit = out / "review_audit.json"

    export_csv = args.export_csv_skeleton if args.export_csv_skeleton else str(out / "review_patch_skeleton.csv")

    cmd = [
        sys.executable,
        str(SCRIPTS / "review_needs.py"),
        "--needs-review",
        args.needs_review,
        "--raw",
        args.raw,
        "--price-quotes",
        args.price_quotes,
        "--out-price-quotes",
        str(out_quotes),
        "--out-needs-review",
        str(out_needs),
        "--out-issues",
        str(out_issues),
        "--mapping-patch-out",
        str(patch_template),
        "--summary-out",
        str(review_summary),
        "--audit-out",
        str(audit),
        "--export-csv-skeleton",
        str(export_csv),
    ]

    if args.supplier_id:
        cmd.extend(["--supplier-id", args.supplier_id])

    if args.apply_csv:
        cmd.extend(["--apply-csv", args.apply_csv])
    elif args.patch:
        cmd.extend(["--patch", args.patch])

    run(cmd)

    s = load_json(review_summary)
    summary = [
        "run_type=review",
        f"input_needs_review={args.needs_review}",
        f"csv_skeleton={export_csv}",
        f"mapping_patch_template={patch_template}",
        f"resolved={s.get('resolved_via_patch', 0)}",
        f"remaining_needs_review={s.get('remaining_needs_review', 0)}",
        f"next_action={s.get('next_action', '')}",
        f"price_quotes={out_quotes}",
        f"audit={audit}",
    ]
    write_summary(out / "run_summary.txt", summary)
    print(str(out))


def cmd_prices(args):
    if getattr(args, "refresh_needed", False):
        out = now_run_dir("prices_refresh")
        defaults = load_json(args.defaults)
        max_age = int(defaults.get("phase1_price_validity", {}).get("max_age_days", 15))
        block_after = int(defaults.get("phase1_price_validity", {}).get("block_after_days", 28))

        rows = []
        if args.raw:
            rows = load_json(args.raw)
        else:
            candidates = list((ROOT / "runs").glob("*/prices/price_quotes.json"))
            if candidates:
                latest = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
                rows = load_json(latest)

        now = datetime.now(timezone.utc)
        by_supplier = {}
        for r in rows:
            sid = (r.get("supplier") or r.get("supplier_id") or "unknown").lower()
            by_supplier.setdefault(sid, []).append(r)

        report = []
        for sid, arr in by_supplier.items():
            captured = max((_parse_iso(x.get("captured_at")) for x in arr), default=None)
            valid_until = max((_parse_iso(x.get("valid_until")) for x in arr), default=None)
            if not captured:
                continue
            age_days = max(0.0, (now - captured).total_seconds() / 86400.0)
            status = "OK"
            next_action = "none"
            if valid_until and now > valid_until or age_days > block_after:
                status = "EXPIRED"
                next_action = "re-import latest price list"
            elif age_days >= max_age:
                status = "STALE"
                next_action = "run with --confirm-stale or re-import latest price list"
            report.append({
                "supplier_id": sid,
                "captured_at": captured.isoformat(),
                "valid_until": valid_until.isoformat() if valid_until else None,
                "age_days": round(age_days, 2),
                "status": status,
                "next_action": next_action,
            })

        refresh_json = out / "refresh_needed.json"
        refresh_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = [
            "run_type=prices_refresh",
            f"suppliers={len(report)}",
            f"stale={sum(1 for x in report if x.get('status') == 'STALE')}",
            f"expired={sum(1 for x in report if x.get('status') == 'EXPIRED')}",
            f"report={refresh_json}",
        ]
        write_summary(out / "run_summary.txt", summary)
        print(str(out))
        return

    if not args.raw:
        raise RuntimeError("prices requires --raw unless --refresh-needed is used")

    out = now_run_dir("prices")
    normalized_csv = out / "offers_normalized.csv"
    mapped_json = out / "offers_mapped.json"
    needs_review = out / "needs_review.json"
    decisions = out / "decisions.json"
    issues = out / "issues.json"

    run([sys.executable, str(SCRIPTS / "normalize_prices.py"), "--input", args.raw, "--out", str(normalized_csv)])
    run([
        sys.executable,
        str(SCRIPTS / "map_offers.py"),
        "--raw",
        args.raw,
        "--catalog",
        args.catalog,
        "--out",
        str(mapped_json),
        "--needs-review",
        str(needs_review),
    ])
    run([
        sys.executable,
        str(SCRIPTS / "optimize_sourcing.py"),
        "--offers",
        str(mapped_json),
        "--overrides",
        args.overrides,
        "--defaults",
        args.defaults,
        "--out",
        str(decisions),
        "--issues-out",
        str(issues),
        "--phase",
        str(args.phase),
        "--service-tag",
        str(getattr(args, "service_tag", "CAT")),
    ] + (["--policies", args.policies] if getattr(args, "policies", None) else [])
      + (["--enable-phase2-rules"] if args.enable_phase2_rules else [])
      + (["--enable-production-overrides"] if getattr(args, "enable_production_overrides", False) else [])
      + (["--rollout-categories", args.rollout_categories] if getattr(args, "rollout_categories", None) else []))

    i = load_json(issues)
    d = load_json(decisions)
    needs = load_json(needs_review)
    locks_used = sum(1 for x in d if x.get("rule_applied") == "LOCK")
    themart_n = sum(1 for x in d if str(x.get("selected_supplier", "")).lower() == "themart")
    alios_n = sum(1 for x in d if str(x.get("selected_supplier", "")).lower() == "alios")
    overlap_items_count = sum(1 for x in d if len(x.get("candidates", [])) >= 2)
    savings_total = sum(float(x.get("savings_vs_lowest_global_per_base_unit", 0) or 0) for x in d)

    summary = [
        f"run_type=prices",
        f"normalized_csv={normalized_csv}",
        f"mapped_json={mapped_json}",
        f"needs_review={len(needs)}",
        f"decisions={len(d)}",
        f"issues={len(i)}",
        f"flags_stale={sum(1 for x in i if 'STALE' in x.get('code',''))}",
        f"flags_anomaly={sum(1 for x in i if 'ANOMALY' in x.get('code',''))}",
        f"locks_used={locks_used}",
        f"supplier_split: themart={themart_n}, alios={alios_n}",
        f"overlap_items_count={overlap_items_count}",
        f"savings_vs_lowest_global={round(savings_total, 6)}",
    ]
    write_summary(out / "run_summary.txt", summary)
    print(str(out))


def cmd_cost(args):
    out = now_run_dir("cost")
    cost_json = out / "cost_breakdown.json"
    issues = out / "issues.json"

    run([
        sys.executable,
        str(SCRIPTS / "cost_recipe.py"),
        "--recipe",
        args.recipe,
        "--offers",
        args.offers,
        "--decisions",
        args.decisions,
        "--defaults",
        args.defaults,
        "--out",
        str(cost_json),
        "--issues-out",
        str(issues),
    ] + (["--confirm-stale"] if args.confirm_stale else []))

    i = load_json(issues)
    summary = [
        "run_type=cost",
        f"cost_breakdown={cost_json}",
        f"issues={len(i)}",
        f"flags_stale={sum(1 for x in i if 'STALE' in x.get('code',''))}",
        f"flags_anomaly={sum(1 for x in i if 'ANOMALY' in x.get('code',''))}",
    ]
    write_summary(out / "run_summary.txt", summary)
    print(str(out))


def build_typec_payload(request_path, cost_path, out_payload):
    req = load_json(request_path)
    cost = load_json(cost_path)
    payload = {
        "proposal_id": req.get("proposal_id", "PROP-TYPEC"),
        "compliance_status": "PASS",
        "placeholder_values": {
            "COURSE_COUNT": req.get("course_count", 0),
            "PRICE_PER_PERSON": req.get("price_per_person", ""),
            "MENU_BLOCKS": req.get("menu_blocks", ""),
        },
        "source_cost_total": cost.get("total_cost", 0),
    }
    Path(out_payload).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_onboard_supplier(args):
    out = now_run_dir("onboarding")
    summary_json = out / "onboarding_summary.json"

    run([
        sys.executable,
        str(SCRIPTS / "onboard_supplier.py"),
        "--supplier-id", args.supplier_id,
        "--display-name", args.display_name or args.supplier_id,
        "--mode", args.mode,
        "--templates-root", args.templates_root,
        "--out-dir", args.out_dir,
        "--fixtures-dir", args.fixtures_dir,
        "--summary-out", str(summary_json),
    ])

    s = load_json(summary_json)
    test_status = "SKIPPED"
    test_note = "not_requested"
    if args.run_tests:
        profile_path = s.get("profile")
        fixtures_root = s.get("fixtures_root")
        try:
            run([
                sys.executable,
                str(SCRIPTS / "run_onboarding_fixture_tests.py"),
                "--supplier-id", args.supplier_id,
                "--profile", str(profile_path),
                "--fixtures-root", str(fixtures_root),
            ])
            test_status = "PASS"
            test_note = "ONBOARDING_FIXTURE_TESTS_PASS"
            s["status"] = "READY"
        except Exception as e:
            test_status = "FAIL"
            test_note = str(e)
            s["status"] = "NEEDS_REVIEW"
        summary_json.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "run_type=onboard_supplier",
        f"supplier_id={args.supplier_id}",
        f"status={s.get('status')}",
        f"profile={s.get('profile')}",
        f"fixtures_root={s.get('fixtures_root')}",
        f"tests={test_status}",
        f"test_note={test_note}",
        f"summary_json={summary_json}",
    ]
    write_summary(out / "run_summary.txt", lines)
    print(str(out))


def cmd_search_proposals(args):
    out = now_run_dir("search")
    index_json = ROOT / "proposals" / "index" / "proposals_index.json"

    if args.reindex or not index_json.exists():
        run([
            sys.executable,
            str(SCRIPTS / "index_proposals.py"),
            "--proposals-root",
            str(ROOT / "proposals"),
            "--index-dir",
            str(ROOT / "proposals" / "index"),
        ])

    idx = load_json(index_json)
    rows = idx.get("rows", []) if isinstance(idx, dict) else []

    def ok(r):
        if args.client:
            q = args.client.lower()
            if q not in str(r.get("client_slug", "")).lower() and q not in str(r.get("client_display", "")).lower():
                return False
        if args.date_from and str(r.get("event_date", "")) < args.date_from:
            return False
        if args.date_to and str(r.get("event_date", "")) > args.date_to:
            return False
        if args.service and str(r.get("service_tag") or "").upper() != str(args.service).upper():
            return False
        if args.template and str(r.get("template_tag") or "").upper() != str(args.template).upper():
            return False
        if args.contains:
            q = args.contains.lower()
            hay = " ".join([
                str(r.get("key_notes", "")),
                str(r.get("client_slug", "")),
                str(r.get("client_display", "")),
            ]).lower()
            if q not in hay:
                return False
        return True

    filtered = [r for r in rows if ok(r)]
    filtered = filtered[: int(args.limit or 20)]

    out_json = out / "search_results.json"
    out_csv = out / "search_results.csv"
    out_txt = out / "search_reply.txt"

    out_json.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")

    import csv
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "event_date", "client_slug", "client_display", "service_tag", "template_tag", "price_per_person_gross", "filed_path_rel", "filed_path_abs"
        ])
        w.writeheader()
        for r in filtered:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    lines = []
    if filtered:
        h = filtered[0]
        client = h.get("client_display") or h.get("client_slug")
        price = h.get("price_per_person_gross")
        lines.append(f"Top hit: {h.get('event_date')} | {client} | {h.get('service_tag')} | {h.get('template_tag')} | €/{price if price is not None else '?'} | {h.get('filed_path_rel') or h.get('filed_path_abs')}")
        for r in filtered[1:9]:
            client = r.get("client_display") or r.get("client_slug")
            price = r.get("price_per_person_gross")
            lines.append(f"{r.get('event_date')} | {client} | {r.get('service_tag')} | {r.get('template_tag')} | €/{price if price is not None else '?'} | {r.get('filed_path_rel') or r.get('filed_path_abs')}")
        lines.append("Tip: γράψε 'open <n>' για να σου δώσω το full path του result n")
    else:
        lines.append("No results.")
    lines = lines[:10]
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_summary(out / "run_summary.txt", [
        "run_type=search_proposals",
        f"results={len(filtered)}",
        f"search_results_json={out_json}",
        f"search_results_csv={out_csv}",
        f"search_reply_txt={out_txt}",
    ])
    print(str(out))


def cmd_open_result(args):
    out = now_run_dir("open")
    search_dir = Path(args.search_run)
    results_path = search_dir / "search_results.json"
    rows = load_json(results_path)

    reply_lines = []
    out_obj = {}

    n = int(args.n)
    if n < 1 or n > len(rows):
        out_obj = {
            "status": "BLOCKED",
            "code": "OPEN-N-OUT-OF-RANGE",
            "requested_n": n,
            "valid_range": f"1..{len(rows)}",
            "search_run": str(search_dir),
        }
        reply_lines = [
            "OPEN-N-OUT-OF-RANGE",
            f"valid range: 1..{len(rows)}",
            f"search_run: {search_dir}",
        ]
    else:
        row = rows[n - 1]
        client = row.get("client_display") or row.get("client_slug")
        summary = f"{row.get('event_date')}|{client}|{row.get('service_tag')}|{row.get('template_tag')}|{row.get('gross_total')}"
        out_obj = {
            "status": "PASS",
            "n": n,
            "absolute_path": row.get("filed_path_abs"),
            "relative_path": row.get("filed_path_rel"),
            "manifest_path": row.get("manifest_path"),
            "summary": summary,
            "search_run": str(search_dir),
        }
        reply_lines = [
            f"abs: {row.get('filed_path_abs')}",
            f"rel: {row.get('filed_path_rel')}",
            f"{summary}",
        ]

        if args.copy_to_clipboard and row.get("filed_path_abs"):
            try:
                import subprocess
                subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value \"{row.get('filed_path_abs')}\""])
                out_obj["clipboard"] = "copied"
            except Exception:
                out_obj["clipboard"] = "failed"

    out_json = out / "open_result.json"
    out_txt = out / "open_reply.txt"
    out_json.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    out_txt.write_text("\n".join(reply_lines[:3]) + "\n", encoding="utf-8")

    write_summary(out / "run_summary.txt", [
        "run_type=open_result",
        f"status={out_obj.get('status')}",
        f"open_result_json={out_json}",
        f"open_reply_txt={out_txt}",
    ])
    print(str(out))


def cmd_recipe_skeleton(args):
    out = now_run_dir("recipe")
    out_recipes = out / "recipes_skeleton.json"
    out_summary = out / "recipe_summary.json"
    out_reply = out / "recipe_reply.txt"

    cmd = [
        sys.executable,
        str(SCRIPTS / "build_recipe_skeleton.py"),
        "--out-recipes",
        str(out_recipes),
        "--out-summary",
        str(out_summary),
        "--out-reply",
        str(out_reply),
    ]
    if args.text:
        cmd.extend(["--text", args.text])
    if args.items_json:
        cmd.extend(["--items-json", args.items_json])
    if args.autofill_portions is not None:
        cmd.extend(["--autofill-portions", str(args.autofill_portions)])

    run(cmd)
    s = load_json(out_summary)
    write_summary(out / "run_summary.txt", [
        "run_type=recipe_skeleton",
        f"status={s.get('status')}",
        f"code={s.get('code')}",
        f"recipe_count={s.get('recipe_count', 0)}",
        f"recipes_skeleton={out_recipes}",
        f"recipe_summary={out_summary}",
        f"recipe_reply={out_reply}",
    ])
    print(str(out))


def cmd_recipe_review(args):
    out = now_run_dir("recipe_review")
    mapped = out / "recipes_mapped.json"
    needs = out / "needs_review_ingredients.json"
    issues = out / "issues.json"
    summary_json = out / "recipe_review_summary.json"

    export_csv = args.export_csv_skeleton if args.export_csv_skeleton else str(out / "recipe_review_skeleton.csv")

    cmd = [
        sys.executable,
        str(SCRIPTS / "review_recipe_ingredients.py"),
        "--recipes", args.recipes,
        "--out-mapped", str(mapped),
        "--out-needs", str(needs),
        "--out-issues", str(issues),
        "--out-summary", str(summary_json),
        "--persist-mode", str(args.persist_mode),
        "--export-csv-skeleton", str(export_csv),
    ]
    if args.apply_csv:
        cmd.extend(["--apply-csv", args.apply_csv])

    run(cmd)
    s = load_json(summary_json)
    write_summary(out / "run_summary.txt", [
        "run_type=recipe_review",
        f"status={s.get('status')}",
        f"recipes={s.get('recipes', 0)}",
        f"needs_review_ingredients={s.get('needs_review_ingredients', 0)}",
        f"issues={s.get('issues', 0)}",
        f"recipes_mapped={mapped}",
        f"needs_review={needs}",
        f"issues_json={issues}",
        f"csv_skeleton={export_csv}",
    ])
    print(str(out))


def cmd_recipe_cost(args):
    out = now_run_dir("recipe_cost")
    costs = out / "recipes_cost_breakdown.json"
    issues = out / "issues.json"
    summary_json = out / "recipe_cost_summary.json"

    cmd = [
        sys.executable,
        str(SCRIPTS / "run_recipe_cost.py"),
        "--recipes-mapped", args.recipes_mapped,
        "--out-costs", str(costs),
        "--out-issues", str(issues),
        "--out-summary", str(summary_json),
        "--defaults", str(args.defaults),
    ]
    if args.offers:
        cmd.extend(["--offers", args.offers])
    if args.decisions:
        cmd.extend(["--decisions", args.decisions])
    if args.confirm_stale:
        cmd.append("--confirm-stale")

    run(cmd)
    s = load_json(summary_json)
    write_summary(out / "run_summary.txt", [
        "run_type=recipe_cost",
        f"status={s.get('status')}",
        f"recipes={s.get('recipes', 0)}",
        f"costed={s.get('costed', 0)}",
        f"issues={s.get('issues', 0)}",
        f"costs={costs}",
        f"issues_json={issues}",
    ])
    print(str(out))


def _latest_run_file(glob_pat: str):
    c = list((ROOT / "runs").glob(glob_pat))
    if not c:
        return None
    return str(sorted(c, key=lambda p: p.stat().st_mtime, reverse=True)[0])


def cmd_menu_offer(args):
    out = now_run_dir("menu_offer")
    pointers = {}

    intake_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "intake",
        "--text",
        args.text,
        "--channel",
        "telegram",
    ])
    pointers["intake"] = intake_dir
    intake_summary = load_json(Path(intake_dir) / "intake_summary.json")

    telegram_reply_txt = out / "telegram_reply.txt"
    telegram_reply_json = out / "telegram_reply.json"

    if intake_summary.get("status") != "PASS":
        msg = f"BLOCKED: {intake_summary.get('next_question') or 'λείπουν required πεδία intake'}"
        missing = intake_summary.get("missing_required", []) or []
        mf = missing[0] if missing else "date"
        hint = "Date: YYYY-MM-DD" if str(mf).lower() in {"date", "event_date"} else f"{mf}: <value>"
        next_action = f"Next action: Reply with {hint}."
        telegram_reply_txt.write_text(msg + "\n" + next_action + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "intake", "message": msg, "next_action": next_action}, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_open_shortcut(telegram_reply_txt, telegram_reply_json, f"open-path --run {out} --target run_summary")
        write_summary(out / "run_summary.txt", [
            "run_type=menu_offer",
            "status=BLOCKED",
            "stage=intake",
            f"intake={intake_dir}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    menu_lines = []
    for ln in str(args.text).splitlines():
        s = ln.strip()
        if not s:
            continue
        if "portion" in s.lower():
            menu_lines.append(s)
    recipe_text = "\n".join(menu_lines) if menu_lines else str(args.text)

    recipe_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "recipe-skeleton",
        "--text",
        recipe_text,
    ])
    pointers["recipe"] = recipe_dir
    recipe_summary = load_json(Path(recipe_dir) / "recipe_summary.json")
    if recipe_summary.get("status") != "PASS":
        msg = f"BLOCKED: {recipe_summary.get('next_question') or 'recipe skeleton invalid'}"
        telegram_reply_txt.write_text(msg + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "recipe-skeleton", "message": msg}, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_open_shortcut(telegram_reply_txt, telegram_reply_json, f"open-path --run {out} --target run_summary")
        write_summary(out / "run_summary.txt", [
            "run_type=menu_offer",
            "status=BLOCKED",
            "stage=recipe-skeleton",
            f"recipe={recipe_dir}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    skeleton_csv = out / "recipe_review_patch_skeleton.csv"
    recipe_review_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "recipe-review",
        "--recipes",
        str(Path(recipe_dir) / "recipes_skeleton.json"),
        "--export-csv-skeleton",
        str(skeleton_csv),
    ])
    pointers["recipe_review"] = recipe_review_dir
    rr_summary = load_json(Path(recipe_review_dir) / "recipe_review_summary.json")
    if rr_summary.get("status") != "PASS":
        msg = f"BLOCKED: λείπουν mappings ingredients. Συμπλήρωσε: {skeleton_csv}"
        rel_csv = skeleton_csv.relative_to(ROOT).as_posix() if str(skeleton_csv).startswith(str(ROOT)) else str(skeleton_csv)
        next_action = f"Next action: Fill CSV {skeleton_csv} ({rel_csv}) then run resume with --menu-offer-run {out} --apply-recipe-review-csv {skeleton_csv}."
        telegram_reply_txt.write_text((msg + "\n" + next_action + "\n")[0:2000], encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "recipe-review", "message": msg, "skeleton_csv": str(skeleton_csv), "next_action": next_action}, ensure_ascii=False, indent=2), encoding="utf-8")
        pointers["raw"] = str(args.raw or "")
        pointers["policies"] = str(args.policies)
        (out / "pointers.json").write_text(json.dumps(pointers, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_open_shortcut(telegram_reply_txt, telegram_reply_json, f"open-path --run {out} --target patch_csv")
        write_summary(out / "run_summary.txt", [
            "run_type=menu_offer",
            "status=BLOCKED",
            "stage=recipe-review",
            f"intake={intake_dir}",
            f"recipe={recipe_dir}",
            f"recipe_review={recipe_review_dir}",
            f"recipe_review_patch_skeleton={skeleton_csv}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    raw = args.raw or _latest_run_file("*/prices/raw_merged.json")
    if not raw:
        raise RuntimeError("menu-offer requires --raw or existing runs/*/prices/raw_merged.json")

    prices_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "prices",
        "--raw",
        str(raw),
        "--phase",
        "3",
        "--enable-phase2-rules",
        "--policies",
        str(args.policies),
    ])
    pointers["prices"] = prices_dir

    recipe_cost_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "recipe-cost",
        "--recipes-mapped",
        str(Path(recipe_review_dir) / "recipes_mapped.json"),
        "--offers",
        str(Path(prices_dir) / "offers_mapped.json"),
        "--decisions",
        str(Path(prices_dir) / "decisions.json"),
    ])
    pointers["recipe_cost"] = recipe_cost_dir
    rc_summary = load_json(Path(recipe_cost_dir) / "recipe_cost_summary.json")
    if rc_summary.get("status") != "PASS":
        msg = "BLOCKED: recipe-cost απέτυχε (λείπουν τιμές/decisions)."
        next_action = "Next action: Run prices import/offer decisions for the supplier round, then rerun menu-offer (or resume if supported)."
        telegram_reply_txt.write_text(msg + "\n" + next_action + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "recipe-cost", "message": msg, "next_action": next_action}, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_open_shortcut(telegram_reply_txt, telegram_reply_json, f"open-path --run {out} --target run_summary")
        write_summary(out / "run_summary.txt", [
            "run_type=menu_offer",
            "status=BLOCKED",
            "stage=recipe-cost",
            f"recipe_cost={recipe_cost_dir}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    recipes_mapped = load_json(Path(recipe_review_dir) / "recipes_mapped.json")
    one_recipe = out / "menu_recipe_selected.json"
    one_recipe.write_text(json.dumps((recipes_mapped or [{}])[0], ensure_ascii=False, indent=2), encoding="utf-8")

    offer_cmd = [
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "offer",
        "--raw",
        str(raw),
        "--recipe",
        str(one_recipe),
        "--proposal-request",
        str(Path(intake_dir) / "proposal_request.json"),
        "--phase",
        "3",
        "--enable-phase2-rules",
        "--policies",
        str(args.policies),
    ]
    if args.template_hint:
        offer_cmd.extend(["--template-type", str(args.template_hint)])
    if args.file_proposal:
        offer_cmd.append("--file-proposal")
    if args.client:
        offer_cmd.extend(["--client", args.client])

    offer_dir = run(offer_cmd)
    pointers["offer"] = offer_dir

    run([
        sys.executable,
        str(SCRIPTS / "format_telegram_reply.py"),
        "--intake-summary",
        str(Path(intake_dir) / "intake_summary.json"),
        "--template-selection",
        str(Path(intake_dir) / "template_selection.json"),
        "--proposal-request",
        str(Path(intake_dir) / "proposal_request.json"),
        "--proposal-payload",
        str(Path(offer_dir) / "proposal_payload.json"),
        "--offer-run-summary",
        str(Path(offer_dir) / "run_summary.txt"),
        "--out-txt",
        str(telegram_reply_txt),
        "--out-json",
        str(telegram_reply_json),
    ])

    pointers["raw"] = str(raw)
    pointers["policies"] = str(args.policies)
    (out / "pointers.json").write_text(json.dumps(pointers, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_open_shortcut(telegram_reply_txt, telegram_reply_json, f"open-path --run {out} --target filed")
    write_summary(out / "run_summary.txt", [
        "run_type=menu_offer",
        "status=PASS",
        f"intake={intake_dir}",
        f"recipe={recipe_dir}",
        f"recipe_review={recipe_review_dir}",
        f"recipe_cost={recipe_cost_dir}",
        f"offer={offer_dir}",
        f"telegram_reply_txt={telegram_reply_txt}",
        f"telegram_reply_json={telegram_reply_json}",
    ])
    if args.reply and telegram_reply_txt.exists():
        print(telegram_reply_txt.read_text(encoding="utf-8").rstrip())
    else:
        print(str(out))


def _read_run_summary_map(path: Path):
    m = {}
    if not path.exists():
        return m
    for ln in path.read_text(encoding="utf-8").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            m[k.strip()] = v.strip()
    return m


def _resolve_repo_relative(p: Path):
    try:
        return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return None


def _menu_offer_summary_line(run_dir: Path):
    pointers = load_json(run_dir / "pointers.json") if (run_dir / "pointers.json").exists() else {}
    offer_dir = Path(pointers.get("offer", "")) if isinstance(pointers, dict) and pointers.get("offer") else None
    if offer_dir and offer_dir.exists():
        payload = load_json(offer_dir / "proposal_payload.json")
        req = load_json(offer_dir / "selected_proposal_request.json")
        event = req.get("event", {}) if isinstance(req, dict) else {}
        date = event.get("date") or event.get("event_date")
        client = ((payload.get("client") or {}).get("name") if isinstance(payload, dict) else None) or (event.get("client_name") if isinstance(event, dict) else None)
        service = event.get("service_type_code")
        tmpl = payload.get("template_type") if isinstance(payload, dict) else None
        if any([date, client, service, tmpl]):
            return f"{date}|{client}|{service}|{tmpl}"
    return None


def _resolve_open_target(run_dir: Path, target: str):
    if not run_dir.exists():
        raise RuntimeError("OPENPATH-RUN-NOT-FOUND")

    pointers = load_json(run_dir / "pointers.json") if (run_dir / "pointers.json").exists() else {}
    offer_dir = Path(pointers.get("offer", "")) if isinstance(pointers, dict) and pointers.get("offer") else None

    if target == "telegram_reply":
        p = run_dir / "telegram_reply.txt"
        return p if p.exists() else None, None
    if target == "patch_csv":
        p = run_dir / "recipe_review_patch_skeleton.csv"
        return p if p.exists() else None, None
    if target == "run_summary":
        p = run_dir / "run_summary.txt"
        return p if p.exists() else None, None
    if target == "manifest":
        cands = [run_dir / "proposal_filing.json"]
        if offer_dir:
            cands.append(offer_dir / "proposal_filing.json")
        for c in cands:
            if c.exists():
                return c, None
        return None, None
    if target == "filed":
        cands = []
        if offer_dir:
            cands.append(offer_dir / "proposal_filing.json")
            cands.append(offer_dir / "run_summary.txt")
        cands.extend([run_dir / "proposal_filing.json", run_dir / "run_summary.txt"])
        for c in cands:
            if c.name == "proposal_filing.json" and c.exists():
                f = load_json(c)
                abs_path = f.get("filed_path_abs") or f.get("filed_abs") or f.get("filed_path")
                if abs_path:
                    return Path(abs_path), _menu_offer_summary_line(run_dir)
            if c.name == "run_summary.txt" and c.exists():
                sm = _read_run_summary_map(c)
                fp = sm.get("final_output")
                if fp:
                    return Path(fp), _menu_offer_summary_line(run_dir)
        return None, _menu_offer_summary_line(run_dir)

    return None, None


def _append_open_shortcut(reply_txt: Path, reply_json: Path, cmd_line: str, max_lines=6):
    txt_lines = reply_txt.read_text(encoding="utf-8").splitlines() if reply_txt.exists() else []
    j = load_json(reply_json) if reply_json.exists() else {}
    if not isinstance(j, dict):
        j = {}
    arr = j.get("open_shortcuts", [])
    if not isinstance(arr, list):
        arr = []
    arr.append(cmd_line)
    j["open_shortcuts"] = arr
    reply_json.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(txt_lines) < max_lines:
        txt_lines.append(f"Open: {cmd_line}")
        reply_txt.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")


def cmd_open_path(args):
    out = now_run_dir("open_path")
    obj = {"clipboard": "not_attempted"}

    if bool(args.run) == bool(args.file):
        raise RuntimeError("open-path requires exactly one of --run or --file")

    if args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        if not p.exists():
            obj = {"status": "BLOCKED", "code": "OPENPATH-TARGET-NOT-FOUND", "clipboard": "not_attempted"}
        else:
            obj = {
                "status": "PASS",
                "absolute_path": str(p),
                "relative_path": _resolve_repo_relative(p),
                "summary": p.name,
                "clipboard": "not_attempted",
            }
    else:
        run_dir = Path(args.run)
        p, summary = _resolve_open_target(run_dir, args.target)
        if not run_dir.exists():
            obj = {"status": "BLOCKED", "code": "OPENPATH-RUN-NOT-FOUND", "run": str(run_dir), "clipboard": "not_attempted"}
        elif p is None:
            obj = {"status": "BLOCKED", "code": "OPENPATH-TARGET-NOT-FOUND", "run": str(run_dir), "target": args.target, "clipboard": "not_attempted"}
        else:
            rp = _resolve_repo_relative(p)
            obj = {
                "status": "PASS",
                "run": str(run_dir),
                "target": args.target,
                "absolute_path": str(p.resolve()),
                "relative_path": rp,
                "summary": summary or p.name,
                "clipboard": "not_attempted",
            }

    if obj.get("status") == "PASS" and args.copy_to_clipboard and obj.get("absolute_path"):
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value \"{obj.get('absolute_path')}\""], check=False)
            obj["clipboard"] = "copied"
        except Exception:
            obj["clipboard"] = "failed"

    (out / "open_path.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    if obj.get("status") == "PASS":
        lines = [
            f"abs: {obj.get('absolute_path')}",
            f"rel: {obj.get('relative_path')}",
            str(obj.get("summary") or ""),
        ]
    else:
        lines = [obj.get("code", "OPENPATH-ERROR")]
    (out / "open_path_reply.txt").write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
    write_summary(out / "run_summary.txt", [
        "run_type=open_path",
        f"status={obj.get('status')}",
        f"clipboard={obj.get('clipboard')}",
        f"open_path_json={out / 'open_path.json'}",
    ])
    print(str(out))


def cmd_resume(args):
    original = Path(args.menu_offer_run)
    pointers = load_json(original / "pointers.json")
    if not isinstance(pointers, dict):
        pointers = {}
    summary_map = _read_run_summary_map(original / "run_summary.txt")
    stopped_at = summary_map.get("stage", "") if summary_map.get("status") == "BLOCKED" else ""

    out = now_run_dir(f"menu_offer_resume_{datetime.now().strftime('%H%M%S')}")
    telegram_reply_txt = out / "telegram_reply.txt"
    telegram_reply_json = out / "telegram_reply.json"

    if stopped_at == "intake":
        msg = "BLOCKED: το run σταμάτησε στο intake. Θέλει νέο intake run, όχι resume."
        telegram_reply_txt.write_text(msg + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "intake", "message": msg}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_summary(out / "run_summary.txt", [
            "run_type=resume",
            "status=BLOCKED",
            "stage=intake",
            f"original_run={original}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    if stopped_at != "recipe-review":
        msg = f"BLOCKED: resume υποστηρίζει stopped_at=recipe-review, έλαβε '{stopped_at or 'unknown'}'."
        telegram_reply_txt.write_text(msg + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": stopped_at or "unknown", "message": msg}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_summary(out / "run_summary.txt", [
            "run_type=resume",
            "status=BLOCKED",
            f"stage={stopped_at or 'unknown'}",
            f"original_run={original}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    if not args.apply_recipe_review_csv:
        raise RuntimeError("resume requires --apply-recipe-review-csv when stopped_at=recipe-review")

    intake_dir = Path(pointers.get("intake", ""))
    recipe_dir = Path(pointers.get("recipe", ""))
    recipe_review_dir = Path(pointers.get("recipe_review", ""))

    rr_apply = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "recipe-review",
        "--recipes",
        str(recipe_dir / "recipes_skeleton.json"),
        "--apply-csv",
        str(args.apply_recipe_review_csv),
    ])
    rr_apply_dir = Path(rr_apply)
    rr_summary = load_json(rr_apply_dir / "recipe_review_summary.json")
    if rr_summary.get("status") != "PASS":
        msg = "BLOCKED: recipe-review παραμένει unresolved μετά το apply CSV."
        telegram_reply_txt.write_text(msg + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "recipe-review", "message": msg}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_summary(out / "run_summary.txt", [
            "run_type=resume",
            "status=BLOCKED",
            "stage=recipe-review",
            f"original_run={original}",
            f"recipe_review={rr_apply_dir}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    raw = args.raw or pointers.get("raw") or _latest_run_file("*/prices/raw_merged.json")
    policies = args.policies or pointers.get("policies") or str(ROOT / "policies" / "sourcing_policies.json")

    prices_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "prices",
        "--raw",
        str(raw),
        "--phase",
        "3",
        "--enable-phase2-rules",
        "--policies",
        str(policies),
    ])

    recipe_cost_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "recipe-cost",
        "--recipes-mapped",
        str(rr_apply_dir / "recipes_mapped.json"),
        "--offers",
        str(Path(prices_dir) / "offers_mapped.json"),
        "--decisions",
        str(Path(prices_dir) / "decisions.json"),
    ])
    rc_summary = load_json(Path(recipe_cost_dir) / "recipe_cost_summary.json")
    if rc_summary.get("status") != "PASS":
        msg = "BLOCKED: recipe-cost απέτυχε στο resume."
        telegram_reply_txt.write_text(msg + "\n", encoding="utf-8")
        telegram_reply_json.write_text(json.dumps({"status": "BLOCKED", "stage": "recipe-cost", "message": msg}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_summary(out / "run_summary.txt", [
            "run_type=resume",
            "status=BLOCKED",
            "stage=recipe-cost",
            f"original_run={original}",
            f"recipe_cost={recipe_cost_dir}",
            f"telegram_reply_txt={telegram_reply_txt}",
        ])
        print(str(out))
        return

    mapped = load_json(Path(rr_apply_dir) / "recipes_mapped.json")
    selected_recipe = out / "resume_recipe_selected.json"
    selected_recipe.write_text(json.dumps((mapped or [{}])[0], ensure_ascii=False, indent=2), encoding="utf-8")

    offer_dir = run([
        sys.executable,
        str(SCRIPTS / "run_pipeline.py"),
        "offer",
        "--raw",
        str(raw),
        "--recipe",
        str(selected_recipe),
        "--proposal-request",
        str(intake_dir / "proposal_request.json"),
        "--phase",
        "3",
        "--enable-phase2-rules",
        "--policies",
        str(policies),
        "--file-proposal",
    ])

    run([
        sys.executable,
        str(SCRIPTS / "format_telegram_reply.py"),
        "--intake-summary",
        str(intake_dir / "intake_summary.json"),
        "--template-selection",
        str(intake_dir / "template_selection.json"),
        "--proposal-request",
        str(intake_dir / "proposal_request.json"),
        "--proposal-payload",
        str(Path(offer_dir) / "proposal_payload.json"),
        "--offer-run-summary",
        str(Path(offer_dir) / "run_summary.txt"),
        "--out-txt",
        str(telegram_reply_txt),
        "--out-json",
        str(telegram_reply_json),
    ])

    resume_summary = {
        "status": "PASS",
        "original_run": str(original),
        "resumed_from": "recipe-review",
        "recipe_review": str(rr_apply_dir),
        "prices": str(prices_dir),
        "recipe_cost": str(recipe_cost_dir),
        "offer": str(offer_dir),
    }
    (out / "resume_summary.json").write_text(json.dumps(resume_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "pointers.json").write_text(json.dumps({
        "original_run": str(original),
        "intake": str(intake_dir),
        "recipe": str(recipe_dir),
        "recipe_review": str(rr_apply_dir),
        "prices": str(prices_dir),
        "recipe_cost": str(recipe_cost_dir),
        "offer": str(offer_dir),
        "raw": str(raw),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    write_summary(out / "run_summary.txt", [
        "run_type=resume",
        "status=PASS",
        f"original_run={original}",
        "resumed_from=recipe-review",
        f"recipe_review={rr_apply_dir}",
        f"recipe_cost={recipe_cost_dir}",
        f"offer={offer_dir}",
        f"telegram_reply_txt={telegram_reply_txt}",
    ])
    print(str(out))


def cmd_ops_help(args):
    out = now_run_dir("ops_help")
    txt = out / "telegram_ops_help.txt"
    lines = [
        "Operator Daily Loop (Telegram-first)",
        "A) New Offer -> menu-offer",
        "B) Patch & Resume -> fill CSV then resume",
        "C) Search & Open -> search-proposals then open-result",
        "Outputs:",
        "- runs/<ts>/menu_offer/...",
        "- runs/<ts>/menu_offer_resume_<ts2>/...",
        "- proposals/YYYY/MM/<client>/<date>/...",
        "NEW OFFER:",
        "python skills/evochia-ops/scripts/run_pipeline.py menu-offer --text \"2026-04-10 | 40 άτομα | DEL finger | 30€/άτομο | client: Demo\\nNigiri Salmon — 40 portions | σολομός 200g, ρύζι sushi 140g\"",
        "PATCH & RESUME:",
        "python skills/evochia-ops/scripts/run_pipeline.py resume --menu-offer-run runs/<ts>/menu_offer --apply-recipe-review-csv skills/evochia-ops/data/imports/recipe_review_patch.csv",
        "SEARCH & OPEN:",
        "python skills/evochia-ops/scripts/run_pipeline.py search-proposals --client demo --date-from 2026-01-01 --service DEL --limit 5 --reindex",
        "python skills/evochia-ops/scripts/run_pipeline.py open-result --search-run runs/<ts>/search --n 1",
    ]
    txt.write_text("\n".join(lines[:20]) + "\n", encoding="utf-8")
    write_summary(out / "run_summary.txt", [
        "run_type=ops_help",
        f"telegram_ops_help_txt={txt}",
        "lines=15",
    ])
    print(str(out))


def _translit_key(s: str):
    greek = {
        "α":"a","β":"v","γ":"g","δ":"d","ε":"e","ζ":"z","η":"i","θ":"th","ι":"i","κ":"k","λ":"l","μ":"m","ν":"n","ξ":"x","ο":"o","π":"p","ρ":"r","σ":"s","ς":"s","τ":"t","υ":"y","φ":"f","χ":"ch","ψ":"ps","ω":"o"
    }
    x = str(s or "").strip().lower()
    x = "".join(greek.get(ch, ch) for ch in x)
    x = unicodedata.normalize("NFKD", x)
    x = "".join(ch for ch in x if not unicodedata.combining(ch))
    x = re.sub(r"[^a-z0-9]+", "-", x)
    x = re.sub(r"-+", "-", x).strip("-")
    return x or "source"


def _valid_source_key(k: str):
    return re.fullmatch(r"[a-z0-9-]+", str(k or "")) is not None


def _registry_path():
    return ROOT / "config" / "daily_refresh_defaults.json"


def _web_registry_path():
    return ROOT / "config" / "web_sources.json"


def _registry_load(path: Path):
    d = load_json(path)
    if not isinstance(d, dict):
        d = {}
    d.setdefault("sources", {})
    d.setdefault("flags", {
        "reindex_proposals": True,
        "run_health_checks": True,
        "reply": True,
        "file_proposal": False,
    })
    if not isinstance(d.get("sources"), dict):
        d["sources"] = {}
    return d


def _registry_save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    srcs = data.get("sources", {}) if isinstance(data, dict) else {}
    ordered = {}
    for k in sorted(srcs.keys()):
        v = dict(srcs[k])
        v["paths"] = sorted(list(dict.fromkeys(v.get("paths", []) or [])))
        ordered[k] = v
    out = {
        "sources": ordered,
        "flags": data.get("flags", {
            "reindex_proposals": True,
            "run_health_checks": True,
            "reply": True,
            "file_proposal": False,
        })
    }
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_obj(o):
    return hashlib.sha1(json.dumps(o, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def _append_source_audit(action: str, key: str, before_obj, after_obj, diff_summary: str, run_id: str):
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": "runner",
        "action": action,
        "key": key,
        "before_hash": _hash_obj(before_obj) if before_obj is not None else None,
        "after_hash": _hash_obj(after_obj) if after_obj is not None else None,
        "diff_summary": diff_summary,
        "run_id": run_id,
    }
    p = ROOT / "audit" / "source_registry_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_source_spec(spec: str):
    m = re.match(r"^([^:]+):(csv|xlsx|ocr|pdf-ocr):(.+)$", str(spec), flags=re.IGNORECASE)
    if not m:
        raise RuntimeError(f"DAILY-SOURCE-INVALID: {spec}")
    return m.group(1).strip(), m.group(2).strip().lower(), m.group(3).strip()


def _is_path_only_source(s: str):
    x = str(s)
    return bool(re.search(r"\\|/|\.[A-Za-z0-9]+$", x))


def _infer_type_from_path(path: Path):
    ext = path.suffix.lower()
    if ext == ".csv":
        return "csv"
    if ext == ".xlsx":
        return "xlsx"
    if ext == ".json":
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(d, dict) and d.get("layout_version") and any(k in d for k in ["anchor", "table", "rows"]):
            return "ocr"
        return None
    return None


def _source_status_path():
    return ROOT / "state" / "source_status.json"


def _load_source_status():
    p = _source_status_path()
    d = load_json(p)
    if not isinstance(d, dict):
        d = {"sources": {}}
    d.setdefault("sources", {})
    return d


def _save_source_status(state):
    p = _source_status_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    sources = state.get("sources", {}) if isinstance(state, dict) else {}
    ordered = {k: sources[k] for k in sorted(sources.keys())}
    p.write_text(json.dumps({"sources": ordered}, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_source_status(key, updater):
    st = _load_source_status()
    cur = dict(st["sources"].get(key, {}))
    cur = updater(cur) or cur
    st["sources"][key] = cur
    _save_source_status(st)


def _touch_source_status_success(key, typ, paths, run_id, run_path, success_field):
    now = datetime.now(timezone.utc).isoformat()
    def upd(cur):
        cur["key"] = key
        cur["type"] = typ
        cur["paths"] = sorted(list(dict.fromkeys(paths or cur.get("paths", []))))
        cur["last_seen_ts"] = now
        cur[success_field] = now
        cur["last_success_ts"] = now
        cur["last_error_code"] = None
        cur["last_run_id"] = run_id
        cur["last_run_path"] = run_path
        return cur
    _update_source_status(key, upd)


def _touch_source_status_error(key, typ, paths, run_id, run_path, error_code):
    now = datetime.now(timezone.utc).isoformat()
    def upd(cur):
        cur["key"] = key
        cur["type"] = typ
        cur["paths"] = sorted(list(dict.fromkeys(paths or cur.get("paths", []))))
        cur["last_seen_ts"] = now
        cur["last_error_code"] = error_code
        cur["last_run_id"] = run_id
        cur["last_run_path"] = run_path
        return cur
    _update_source_status(key, upd)


def _check_file_source(key, stype, path):
    p = Path(path)
    if not p.exists():
        return "BROKEN", "HEALTH-PATH-NOT-FOUND", "path missing"
    try:
        with p.open("rb") as f:
            _ = f.read(1)
    except Exception:
        return "BROKEN", "HEALTH-NOT-READABLE", "not readable"
    if p.stat().st_size <= 0:
        return "BROKEN", "HEALTH-EMPTY-FILE", "empty file"

    ext = p.suffix.lower()
    expected = {"csv": ".csv", "xlsx": ".xlsx", "ocr": ".json", "pdf-ocr": ".json"}.get(stype)
    if expected and ext != expected:
        return "WARNING", "HEALTH-UNSUPPORTED-EXT", f"ext {ext} expected {expected}"

    if stype == "csv":
        try:
            first = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not first:
                return "BROKEN", "HEALTH-CSV-NO-HEADER", "no header"
        except Exception:
            return "BROKEN", "HEALTH-NOT-READABLE", "csv read fail"
    elif stype == "xlsx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(p, "r") as z:
                wb = ET.fromstring(z.read("xl/workbook.xml"))
                ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                sheets = wb.findall("x:sheets/x:sheet", ns)
                if not sheets:
                    return "BROKEN", "HEALTH-XLSX-OPEN-FAIL", "no sheets"
        except Exception:
            return "BROKEN", "HEALTH-XLSX-OPEN-FAIL", "xlsx open fail"
    elif stype in {"ocr", "pdf-ocr"}:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not (isinstance(d, dict) and d.get("layout_version") and any(k in d for k in ["anchor", "table", "rows"])):
                return "BROKEN", "HEALTH-JSON-NOT-OCR-SHAPE", "json not ocr shape"
        except Exception:
            return "BROKEN", "HEALTH-JSON-NOT-OCR-SHAPE", "json parse fail"

    if p.stat().st_size < 50:
        return "WARNING", "HEALTH-TINY-FILE", "tiny file"
    return "OK", None, "ok"


def _expand_sources_for_health(sources_args, defaults, auto_register=False, no_auto_update=False, out=None):
    reg_sources = (defaults.get("sources") or {}) if isinstance(defaults, dict) else {}
    expanded = []
    blocked = []
    auto_log = []

    items = sources_args or list(reg_sources.keys())
    for s in items:
        sx = str(s)
        if re.match(r"^[^:]+:(csv|xlsx|ocr|pdf-ocr):.+$", sx, flags=re.IGNORECASE):
            sid, stype, pth = _parse_source_spec(sx)
            expanded.append((sid, stype, pth, sid))
            continue
        if _is_path_only_source(sx):
            p = Path(sx)
            inferred = _infer_type_from_path(p)
            ikey = _translit_key(p.stem)
            existing = reg_sources.get(ikey)
            if not existing and not auto_register:
                blocked.append({"supplier": ikey, "code": "DAILY-SOURCE-NOT-REGISTERED", "path": sx})
                continue
            if auto_register:
                if not existing:
                    inferred_supplier = "themart" if inferred == "csv" else ("alios" if inferred == "xlsx" else ikey)
                    reg_sources[ikey] = {"type": inferred or "csv", "supplier_id": inferred_supplier, "display_name": ikey, "paths": [str(p)]}
                    auto_log.append({"action": "auto_register", "key": ikey, "path": str(p)})
                elif str(p) not in (existing.get("paths", []) or []) and not no_auto_update:
                    existing.setdefault("paths", []).append(str(p))
                    auto_log.append({"action": "auto_update", "key": ikey, "path": str(p)})
            src = reg_sources.get(ikey)
            if not src:
                blocked.append({"supplier": ikey, "code": "DAILY-SOURCE-NOT-REGISTERED", "path": sx})
                continue
            for pth in src.get("paths", []) or []:
                expanded.append((ikey, str(src.get("type", inferred or "csv")).lower(), str(pth), str(src.get("supplier_id", ikey))))
            continue
        src = reg_sources.get(sx)
        if not src:
            blocked.append({"supplier": sx, "code": "DAILY-UNKNOWN-SOURCE", "path": sx})
            continue
        for pth in src.get("paths", []) or []:
            expanded.append((sx, str(src.get("type", "")).lower(), str(pth), str(src.get("supplier_id", sx))))

    return expanded, blocked, auto_log, reg_sources


def cmd_source_health(args):
    out = now_run_dir("source_health")
    defaults = _registry_load(Path(args.defaults))
    expanded, blocked, _, _ = _expand_sources_for_health(args.sources, defaults, auto_register=False, no_auto_update=True, out=out)

    rows = []
    run_id = out.parent.name
    for key, stype, path, _supplier in expanded:
        status, code, msg = _check_file_source(key, stype, path)
        row = {
            "key": key,
            "type": stype,
            "path": path,
            "status": status,
            "code": code,
            "message": msg,
        }
        rows.append(row)
        if status == "OK":
            _touch_source_status_success(key, stype, [path], run_id, str(out), "last_health_ok_ts")
        else:
            _touch_source_status_error(key, stype, [path], run_id, str(out), code)

    if args.include_web:
        w = load_json(_web_registry_path())
        ws = (w.get("sources") if isinstance(w, dict) else {}) or {}
        for k, v in sorted(ws.items()):
            u = urlparse(str(v.get("url", "")))
            ok = u.scheme in {"http", "https"} and bool(u.netloc)
            rows.append({
                "key": f"web:{k}",
                "type": "web",
                "path": v.get("url"),
                "status": "OK" if ok else "BROKEN",
                "code": None if ok else "WEB-SOURCE-INVALID-URL",
                "message": "ok" if ok else "invalid url",
            })

    for b in blocked:
        rows.append({
            "key": b.get("supplier"),
            "type": "unknown",
            "path": b.get("path"),
            "status": "BROKEN",
            "code": b.get("code"),
            "message": "blocked",
        })

    import csv
    rep = out / "source_health_report.json"
    rep.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "source_health_report.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "type", "path", "status", "code", "message"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    broken = [r for r in rows if r.get("status") == "BROKEN"]
    (out / "broken_sources.json").write_text(json.dumps(broken, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"source-health {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    lines.append(f"ok={sum(1 for r in rows if r.get('status')=='OK')} warning={sum(1 for r in rows if r.get('status')=='WARNING')} broken={len(broken)}")
    for r in broken[:6]:
        lines.append(f"BROKEN {r.get('key')} | {r.get('code')}")
    (out / "source_health_reply.txt").write_text("\n".join(lines[:10]) + "\n", encoding="utf-8")

    write_summary(out / "run_summary.txt", [
        "run_type=source_health",
        f"ok={sum(1 for r in rows if r.get('status')=='OK')}",
        f"warning={sum(1 for r in rows if r.get('status')=='WARNING')}",
        f"broken={len(broken)}",
        f"source_health_report_json={rep}",
        f"source_health_reply_txt={out / 'source_health_reply.txt'}",
    ])
    if args.reply:
        print((out / "source_health_reply.txt").read_text(encoding="utf-8").rstrip())
    else:
        print(str(out))


def cmd_source_status(args):
    out = now_run_dir("source_status")
    st = _load_source_status()
    rows = []
    now = datetime.now(timezone.utc)
    for k, v in sorted((st.get("sources") or {}).items()):
        row = dict(v)
        row.setdefault("key", k)
        ls = row.get("last_success_ts")
        stale = False
        if ls and args.days:
            try:
                dt = datetime.fromisoformat(str(ls).replace("Z", "+00:00"))
                stale = (now - dt).total_seconds() > int(args.days) * 86400
            except Exception:
                stale = True
        row["is_broken"] = bool(row.get("last_error_code"))
        row["is_stale"] = stale
        rows.append(row)

    if args.only_broken:
        rows = [r for r in rows if r.get("is_broken")]
    if args.only_stale:
        rows = [r for r in rows if r.get("is_stale")]

    (out / "source_status.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    import csv
    with (out / "source_status.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["key", "type", "last_success_ts", "last_error_code", "last_run_id", "last_run_path"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    rows_sorted = sorted(rows, key=lambda r: (0 if r.get("last_error_code") else 1, r.get("key", "")))
    lines = [f"source-status: {len(rows_sorted)}"] + [f"{r.get('key')} | {r.get('type')} | err={r.get('last_error_code') or '-'} | last={r.get('last_success_ts') or '-'}" for r in rows_sorted[:11]]
    (out / "source_status_reply.txt").write_text("\n".join(lines[:12]) + "\n", encoding="utf-8")
    if args.reply:
        print((out / "source_status_reply.txt").read_text(encoding="utf-8").rstrip())
    else:
        print(str(out))


def cmd_alias(args):
    out = now_run_dir("alias")
    alias_map = {
        "daily": "python skills/evochia-ops/scripts/run_pipeline.py daily-refresh --sources themart --sources alios --reply",
        "health": "python skills/evochia-ops/scripts/run_pipeline.py source-health --reply",
        "status": "python skills/evochia-ops/scripts/run_pipeline.py source-status --only-broken --reply",
    }
    line = alias_map.get(str(args.name))
    if not line:
        raise RuntimeError("ALIAS-NOT-FOUND")
    (out / f"alias_{args.name}.txt").write_text(line + "\n", encoding="utf-8")
    print(line)


def cmd_add_source(args):
    out = now_run_dir("add_source")
    reg_path = _registry_path()
    reg = _registry_load(reg_path)
    key = str(args.key).strip().lower()
    stype = str(args.type).strip().lower()

    if not _valid_source_key(key):
        obj = {"status": "BLOCKED", "code": "ADD-SOURCE-INVALID-KEY", "key": key}
        (out / "add_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_source_reply.txt").write_text("ADD-SOURCE-INVALID-KEY\n", encoding="utf-8")
        print(str(out)); return
    if stype not in {"csv", "xlsx", "ocr", "pdf-ocr"}:
        obj = {"status": "BLOCKED", "code": "ADD-SOURCE-INVALID-TYPE", "type": stype}
        (out / "add_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_source_reply.txt").write_text("ADD-SOURCE-INVALID-TYPE\n", encoding="utf-8")
        print(str(out)); return
    paths = list(args.path or [])
    if not paths:
        raise RuntimeError("add-source requires --path >=1")
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        obj = {"status": "BLOCKED", "code": "ADD-SOURCE-PATH-NOT-FOUND", "missing": missing}
        (out / "add_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_source_reply.txt").write_text("ADD-SOURCE-PATH-NOT-FOUND\n", encoding="utf-8")
        print(str(out)); return
    if key in reg.get("sources", {}) and not args.replace:
        obj = {"status": "BLOCKED", "code": "ADD-SOURCE-EXISTS", "key": key}
        (out / "add_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_source_reply.txt").write_text("ADD-SOURCE-EXISTS\n", encoding="utf-8")
        print(str(out)); return

    before = reg.get("sources", {}).get(key)
    entry = {
        "type": stype,
        "supplier_id": args.supplier_id or key,
        "display_name": args.display_name or key,
        "paths": sorted(list(dict.fromkeys(paths))),
    }
    after = entry

    diff = {"key": key, "before": before, "after": after}
    (out / "diff_preview.txt").write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.dry_run:
        reg["sources"][key] = entry
        _registry_save(reg_path, reg)
        _append_source_audit("replace" if args.replace and before else "add", key, before, after, "add-source", out.parent.name)
        _touch_source_status_success(key, stype, entry.get("paths", []), out.parent.name, str(out), "last_seen_ts")

    obj = {"status": "PASS", "key": key, "dry_run": bool(args.dry_run), "config": str(reg_path)}
    (out / "add_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "add_source_reply.txt").write_text((f"PASS add-source {key}\nconfig={reg_path}\n")[:1000], encoding="utf-8")
    print(str(out))


def cmd_list_sources(args):
    out = now_run_dir("list_sources")
    reg = _registry_load(_registry_path())
    rows = []
    for k, v in sorted((reg.get("sources") or {}).items()):
        rows.append({
            "key": k,
            "type": v.get("type"),
            "path_count": len(v.get("paths", []) or []),
            "display_name": v.get("display_name"),
            "supplier_id": v.get("supplier_id"),
        })
    (out / "list_sources.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"sources: {len(rows)}"] + [f"{r['key']} | {r['type']} | paths={r['path_count']} | {r.get('display_name')} | {r.get('supplier_id')}" for r in rows[:11]]
    (out / "list_sources_reply.txt").write_text("\n".join(lines[:12]) + "\n", encoding="utf-8")
    print(str(out))


def cmd_remove_source(args):
    out = now_run_dir("remove_source")
    reg_path = _registry_path()
    reg = _registry_load(reg_path)
    key = str(args.key).strip().lower()
    if key not in reg.get("sources", {}):
        obj = {"status": "BLOCKED", "code": "REMOVE-SOURCE-NOT-FOUND", "key": key}
        (out / "remove_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "remove_source_reply.txt").write_text("REMOVE-SOURCE-NOT-FOUND\n", encoding="utf-8")
        print(str(out)); return
    before = reg["sources"][key]
    diff = {"key": key, "before": before, "after": None}
    (out / "diff_preview.txt").write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.dry_run:
        del reg["sources"][key]
        _registry_save(reg_path, reg)
        _append_source_audit("remove", key, before, None, "remove-source", out.parent.name)
        st = _load_source_status()
        if key in st.get("sources", {}):
            del st["sources"][key]
            _save_source_status(st)
    obj = {"status": "PASS", "key": key, "dry_run": bool(args.dry_run)}
    (out / "remove_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "remove_source_reply.txt").write_text(f"PASS remove-source {key}\n", encoding="utf-8")
    print(str(out))


def cmd_edit_source(args):
    out = now_run_dir("edit_source")
    reg_path = _registry_path()
    reg = _registry_load(reg_path)
    key = str(args.key).strip().lower()
    if key not in reg.get("sources", {}):
        obj = {"status": "BLOCKED", "code": "REMOVE-SOURCE-NOT-FOUND", "key": key}
        (out / "edit_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "edit_source_reply.txt").write_text("REMOVE-SOURCE-NOT-FOUND\n", encoding="utf-8")
        print(str(out)); return
    if not any([args.add_path, args.remove_path, args.set_display_name, args.set_supplier_id]):
        obj = {"status": "BLOCKED", "code": "EDIT-SOURCE-NO-CHANGES", "key": key}
        (out / "edit_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "edit_source_reply.txt").write_text("EDIT-SOURCE-NO-CHANGES\n", encoding="utf-8")
        print(str(out)); return

    before = dict(reg["sources"][key])
    cur = dict(before)
    paths = list(cur.get("paths", []) or [])

    for p in args.add_path or []:
        if not Path(p).exists():
            obj = {"status": "BLOCKED", "code": "EDIT-SOURCE-PATH-NOT-FOUND", "path": p}
            (out / "edit_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "edit_source_reply.txt").write_text("EDIT-SOURCE-PATH-NOT-FOUND\n", encoding="utf-8")
            print(str(out)); return
        if p not in paths:
            paths.append(p)

    for p in args.remove_path or []:
        if p not in paths:
            obj = {"status": "BLOCKED", "code": "EDIT-SOURCE-PATH-NOT-IN-ENTRY", "path": p}
            (out / "edit_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "edit_source_reply.txt").write_text("EDIT-SOURCE-PATH-NOT-IN-ENTRY\n", encoding="utf-8")
            print(str(out)); return
        paths.remove(p)

    if args.set_display_name:
        cur["display_name"] = args.set_display_name
    if args.set_supplier_id:
        cur["supplier_id"] = args.set_supplier_id
    cur["paths"] = sorted(paths)

    (out / "diff_preview.txt").write_text(json.dumps({"key": key, "before": before, "after": cur}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.dry_run:
        reg["sources"][key] = cur
        _registry_save(reg_path, reg)
        _append_source_audit("edit", key, before, cur, "edit-source", out.parent.name)
        _touch_source_status_success(key, cur.get("type", "unknown"), cur.get("paths", []), out.parent.name, str(out), "last_seen_ts")

    obj = {"status": "PASS", "key": key, "dry_run": bool(args.dry_run)}
    (out / "edit_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "edit_source_reply.txt").write_text(f"PASS edit-source {key}\n", encoding="utf-8")
    print(str(out))


def cmd_add_web_source(args):
    out = now_run_dir("add_web_source")
    key = str(args.key).strip().lower()
    if not _valid_source_key(key):
        obj = {"status": "BLOCKED", "code": "WEB-SOURCE-INVALID-KEY"}
        (out / "add_web_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_web_source_reply.txt").write_text("WEB-SOURCE-INVALID-KEY\n", encoding="utf-8")
        print(str(out)); return
    u = urlparse(str(args.url))
    if u.scheme not in {"http", "https"} or not u.netloc:
        obj = {"status": "BLOCKED", "code": "WEB-SOURCE-INVALID-URL"}
        (out / "add_web_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_web_source_reply.txt").write_text("WEB-SOURCE-INVALID-URL\n", encoding="utf-8")
        print(str(out)); return

    p = _web_registry_path()
    reg = load_json(p)
    if not isinstance(reg, dict):
        reg = {"sources": {}}
    reg.setdefault("sources", {})
    if key in reg["sources"] and not args.replace:
        obj = {"status": "BLOCKED", "code": "WEB-SOURCE-EXISTS"}
        (out / "add_web_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "add_web_source_reply.txt").write_text("WEB-SOURCE-EXISTS\n", encoding="utf-8")
        print(str(out)); return

    entry = {"url": args.url, "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()]}
    if not args.dry_run:
        reg["sources"][key] = entry
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    obj = {"status": "PASS", "key": key, "dry_run": bool(args.dry_run)}
    (out / "add_web_source_summary.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "add_web_source_reply.txt").write_text(f"PASS add-web-source {key}\n", encoding="utf-8")
    print(str(out))


def cmd_daily_refresh(args):
    out = now_run_dir("daily_refresh")
    pointers = []
    suppliers = []
    blocked = []

    defaults = load_json(args.defaults)
    dflags = defaults.get("flags", {}) if isinstance(defaults, dict) else {}

    argv = sys.argv
    reindex_set = ("--reindex-proposals" in argv) or ("--no-reindex-proposals" in argv)
    health_set = ("--run-health-checks" in argv) or ("--no-run-health-checks" in argv)
    reply_set = ("--reply" in argv) or ("--no-reply" in argv)
    file_set = "--file-proposal" in argv

    reindex_proposals = args.reindex_proposals if reindex_set else bool(dflags.get("reindex_proposals", True))
    run_health_checks = args.run_health_checks if health_set else bool(dflags.get("run_health_checks", True))
    reply_flag = args.reply if reply_set else bool(dflags.get("reply", True))
    file_proposal_flag = args.file_proposal if file_set else bool(dflags.get("file_proposal", False))

    expanded_sources, blocked_expand, auto_log, reg_sources = _expand_sources_for_health(
        args.sources, defaults, auto_register=args.auto_register, no_auto_update=args.no_auto_update, out=out
    )
    blocked.extend(blocked_expand)

    if args.auto_register and auto_log:
        defaults["sources"] = reg_sources
        _registry_save(Path(args.defaults), defaults)
        p = out / "auto_register_log.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for row in auto_log:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if not args.no_preflight:
        sh_cmd = [sys.executable, str(SCRIPTS / "run_pipeline.py"), "source-health", "--defaults", str(args.defaults), "--no-reply"]
        for s in args.sources or []:
            sh_cmd.extend(["--sources", str(s)])
        sh_out = run(sh_cmd)
        broken_pre = load_json(Path(sh_out) / "broken_sources.json")
        if broken_pre:
            blocked.extend([{"supplier": x.get("key"), "code": x.get("code"), "path": x.get("path")} for x in broken_pre])

    for sid, stype, path, supplier_id in ([] if blocked else expanded_sources):
        p = Path(path)
        if not p.exists():
            blocked.append({"supplier": sid, "code": "DAILY-SOURCE-NOT-FOUND", "path": path})
            continue

        profile_path = ROOT / "suppliers" / f"{supplier_id}.json"
        if not profile_path.exists():
            blocked.append({"supplier": sid, "code": "DAILY-SUPPLIER-PROFILE-NOT-FOUND", "path": str(profile_path)})
            continue

        if stype == "csv":
            imp_dir = run([
                sys.executable, str(SCRIPTS / "run_pipeline.py"), "import",
                "--csv-input", str(p),
                "--csv-profile", str(profile_path),
            ])
        elif stype == "xlsx":
            imp_dir = run([
                sys.executable, str(SCRIPTS / "run_pipeline.py"), "import",
                "--xlsx-input", str(p),
                "--xlsx-profile", str(profile_path),
            ])
        else:
            blocked.append({"supplier": sid, "code": "DAILY-SOURCE-TYPE-NOT-SUPPORTED", "path": path})
            continue

        raw = Path(imp_dir) / "raw_merged.json"
        prices_dir = run([
            sys.executable, str(SCRIPTS / "run_pipeline.py"), "prices",
            "--raw", str(raw),
            "--phase", "3",
            "--enable-phase2-rules",
            "--policies", str(args.policies),
        ])

        imp_sum = _read_run_summary_map(Path(imp_dir) / "run_summary.txt")
        pr_sum = _read_run_summary_map(Path(prices_dir) / "run_summary.txt")
        decisions = load_json(Path(prices_dir) / "decisions.json")
        dec_count = len(decisions)

        prev_snap = sorted((ROOT / "runs").glob("*/daily_refresh/daily_refresh_summary.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        prev_count = None
        if prev_snap:
            prev = load_json(prev_snap[0])
            if isinstance(prev, dict):
                for x in prev.get("suppliers", []):
                    if x.get("supplier") == sid:
                        prev_count = x.get("decisions")
        changed = None if prev_count is None else (dec_count - int(prev_count or 0))

        row = {
            "supplier": sid,
            "source_type": stype,
            "source_path": str(p),
            "import_run": imp_dir,
            "prices_run": prices_dir,
            "rows_ok": int(imp_sum.get("lines_ok", 0) or 0),
            "needs_review": int(imp_sum.get("needs_review", 0) or 0),
            "issues_count": int(pr_sum.get("issues", 0) or 0),
            "decisions": dec_count,
            "decisions_changed": changed,
        }
        suppliers.append(row)
        pointers.append({"supplier": sid, "import": imp_dir, "prices": prices_dir})
        if int(row.get("needs_review", 0)) == 0 and int(row.get("issues_count", 0)) == 0:
            _touch_source_status_success(sid, stype, [path], out.parent.name, str(out), "last_daily_refresh_ok_ts")
            _touch_source_status_success(sid, stype, [path], out.parent.name, str(out), "last_import_ok_ts")
        else:
            _touch_source_status_error(sid, stype, [path], out.parent.name, str(out), "DAILY-HAS-NEEDS-OR-ISSUES")

    index_status = "skipped"
    if reindex_proposals:
        run([
            sys.executable, str(SCRIPTS / "run_pipeline.py"), "search-proposals", "--limit", "1", "--reindex"
        ])
        index_status = "reindexed_ok"

    health = {"status": "SKIPPED", "reason": "disabled"}
    if run_health_checks:
        try:
            h_offer = run([
                sys.executable, str(SCRIPTS / "run_pipeline.py"), "offer",
                "--template-type", "B",
                "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
                "--recipe", str(ROOT / "data" / "recipes" / "sample_recipe.json"),
                "--request", str(ROOT / "data" / "sample_proposal_request.json"),
                "--phase", "3",
                "--enable-phase2-rules",
                "--policies", str(args.policies),
            ] + (["--file-proposal"] if file_proposal_flag else []))
            hs = _read_run_summary_map(Path(h_offer) / "run_summary.txt")
            health = {"status": "PASS", "offer_run": h_offer, "top_reason_code": hs.get("proposal_validation", "PASS")}
        except Exception:
            health = {"status": "BLOCK", "top_reason_code": "HEALTH-CHECK-FAILED"}

    summary = {
        "status": "BLOCKED" if blocked else "PASS",
        "timestamp": datetime.now().isoformat(),
        "suppliers": suppliers,
        "blocked_sources": blocked,
        "index_status": index_status,
        "health_checks": health,
        "pointers": pointers,
        "auto_register_actions": auto_log,
    }
    (out / "daily_refresh_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if auto_log:
        p = out / "auto_register_log.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for row in auto_log:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    lines = [f"Daily refresh {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    for s in suppliers[:6]:
        ch = s.get("decisions_changed")
        chs = "n/a" if ch is None else str(ch)
        lines.append(f"{s['supplier']}: ok={s['rows_ok']} nr={s['needs_review']} issues={s['issues_count']} Δdec={chs}")
    lines.append(f"index: {index_status}")
    lines.append(f"health: {health.get('status')} | {health.get('top_reason_code','-')}")
    if blocked:
        lines.append("BROKEN sources: " + ", ".join([str(x.get("supplier")) for x in blocked[:3]]))
        b0 = blocked[0]
        if b0.get("code") == "DAILY-SOURCE-NOT-REGISTERED":
            lines.append(f"Next action: run add-source for {b0.get('path')} or rerun with --auto-register")
        else:
            lines.append(f"Next action: fix source path {b0.get('path')}")
    elif any(int(x.get("needs_review", 0)) > 0 for x in suppliers):
        bad = [x for x in suppliers if int(x.get("needs_review", 0)) > 0][0]
        lines.append(f"Next action: run review for {bad.get('supplier')} needs_review={bad.get('needs_review')}")

    (out / "daily_refresh_reply.txt").write_text("\n".join(lines[:10]) + "\n", encoding="utf-8")
    (out / "telegram_macros.txt").write_text(
        "\n".join([
            "python skills/evochia-ops/scripts/run_pipeline.py daily-refresh --sources themart --sources alios --reply",
            "python skills/evochia-ops/scripts/run_pipeline.py open-path --run runs/<ts>/daily_refresh --target run_summary",
        ]) + "\n",
        encoding="utf-8",
    )
    write_summary(out / "run_summary.txt", [
        "run_type=daily_refresh",
        f"status={summary.get('status')}",
        f"suppliers={len(suppliers)}",
        f"blocked_sources={len(blocked)}",
        f"daily_refresh_summary_json={out / 'daily_refresh_summary.json'}",
        f"daily_refresh_reply_txt={out / 'daily_refresh_reply.txt'}",
        f"telegram_macros_txt={out / 'telegram_macros.txt'}",
    ])

    if reply_flag:
        print((out / "daily_refresh_reply.txt").read_text(encoding="utf-8").rstrip())
    else:
        print(str(out))


def cmd_intake(args):
    out = now_run_dir("intake")
    proposal_request = out / "proposal_request.json"
    intake_summary = out / "intake_summary.json"
    intake_transcript = out / "intake_transcript.json"
    template_selection = out / "template_selection.json"

    run([
        sys.executable,
        str(SCRIPTS / "intake_wizard.py"),
        "--text",
        args.text,
        "--defaults",
        args.defaults,
        "--out-request",
        str(proposal_request),
        "--summary-out",
        str(intake_summary),
        "--transcript-out",
        str(intake_transcript),
        "--template-selection-out",
        str(template_selection),
        "--channel",
        str(getattr(args, "channel", "telegram")),
    ])

    s = load_json(intake_summary)
    summary = [
        "run_type=intake",
        f"status={s.get('status')}",
        f"proposal_request={proposal_request}",
        f"intake_summary={intake_summary}",
        f"intake_transcript={intake_transcript}",
        f"template_selection={template_selection}",
        f"missing_required={','.join(s.get('missing_required', []))}",
        f"next_question={s.get('next_question')}",
    ]

    offer_out = None
    if args.run_offer and s.get("status") == "PASS":
        req = load_json(proposal_request)
        selected_template = load_json(template_selection).get("template_type", "A")
        raw = args.raw
        if not raw:
            candidates = list((ROOT / "runs").glob("*/prices/raw_merged.json"))
            if candidates:
                raw = str(sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0])
        recipe = args.recipe or str(ROOT / "data" / "recipes" / "policy_cases_recipe.json")
        if not raw:
            raise RuntimeError("intake --run-offer requires --raw or an existing runs/*/prices/raw_merged.json")

        cmd = [
            sys.executable,
            str(SCRIPTS / "run_pipeline.py"),
            "offer",
            "--template-type",
            str(selected_template),
            "--raw",
            str(raw),
            "--recipe",
            str(recipe),
            "--request",
            str(proposal_request),
            "--phase",
            "3",
            "--enable-phase2-rules",
            "--policies",
            str(args.policies),
            "--service-tag",
            str(req.get("event", {}).get("service_type_code") or "CAT"),
        ]
        if args.file_proposal:
            cmd.append("--file-proposal")
        if args.client:
            cmd.extend(["--client", args.client])

        offer_out = run(cmd)
        summary.append(f"offer_run={offer_out}")

    telegram_reply_txt = out / "telegram_reply.txt"
    telegram_reply_json = out / "telegram_reply.json"
    fmt_cmd = [
        sys.executable,
        str(SCRIPTS / "format_telegram_reply.py"),
        "--intake-summary",
        str(intake_summary),
        "--template-selection",
        str(template_selection),
        "--proposal-request",
        str(proposal_request),
        "--out-txt",
        str(telegram_reply_txt),
        "--out-json",
        str(telegram_reply_json),
    ]
    if offer_out:
        fmt_cmd.extend([
            "--proposal-payload",
            str(Path(offer_out) / "proposal_payload.json"),
            "--offer-run-summary",
            str(Path(offer_out) / "run_summary.txt"),
        ])
    run(fmt_cmd)
    summary.append(f"telegram_reply_txt={telegram_reply_txt}")
    summary.append(f"telegram_reply_json={telegram_reply_json}")

    write_summary(out / "run_summary.txt", summary)
    if args.reply and telegram_reply_txt.exists():
        print(telegram_reply_txt.read_text(encoding="utf-8").rstrip())
    else:
        print(str(out))


def cmd_offer(args):
    selected_template = args.template_type
    request_path = args.request

    selector_trace = None
    if args.proposal_request:
        sel_json = now_run_dir("selector") / "selection.json"
        run([
            sys.executable,
            str(SCRIPTS / "select_template.py"),
            "--request",
            args.proposal_request,
            "--out",
            str(sel_json),
        ])
        sel = load_json(sel_json)
        selected_template = sel.get("template_type")
        request_path = args.proposal_request
        selector_trace = sel_json

    if selected_template not in {"A", "B", "C"}:
        raise RuntimeError("offer requires --template-type (A|B|C) or --proposal-request resolvable to A|B|C")
    if not request_path:
        raise RuntimeError("offer requires --request or --proposal-request")

    out = now_run_dir(selected_template.lower())
    if selector_trace and Path(selector_trace).exists():
        (out / "template_selection.json").write_text(Path(selector_trace).read_text(encoding="utf-8"), encoding="utf-8")
    else:
        manual_trace = {
            "template_type": selected_template,
            "service_type": None,
            "event_style": None,
            "template_hint": None,
            "rule_fired": "RULE_MANUAL_TEMPLATE_TYPE",
            "timestamp": datetime.now().isoformat(),
        }
        (out / "template_selection.json").write_text(json.dumps(manual_trace, ensure_ascii=False, indent=2), encoding="utf-8")

    normalized_csv = out / "offers_normalized.csv"
    mapped_json = out / "offers_mapped.json"
    needs_review = out / "needs_review.json"
    decisions = out / "decisions.json"
    sourcing_issues = out / "sourcing_issues.json"

    cost_json = out / "cost_breakdown.json"
    cost_issues = out / "cost_issues.json"

    payload = out / "proposal_payload.json"
    validation = out / "proposal_validation.json"
    proposal_issues = out / "proposal_issues.json"

    render_validation = out / "render_validation.json"
    render_issues = out / "render_issues.json"

    final_output = out / ("final_output.html" if selected_template == "C" else "final_output.docx")

    # deterministic chain
    run([sys.executable, str(SCRIPTS / "normalize_prices.py"), "--input", args.raw, "--out", str(normalized_csv)])
    run([
        sys.executable,
        str(SCRIPTS / "map_offers.py"),
        "--raw",
        args.raw,
        "--catalog",
        args.catalog,
        "--out",
        str(mapped_json),
        "--needs-review",
        str(needs_review),
    ])
    run([
        sys.executable,
        str(SCRIPTS / "optimize_sourcing.py"),
        "--offers",
        str(mapped_json),
        "--overrides",
        args.overrides,
        "--defaults",
        args.defaults,
        "--out",
        str(decisions),
        "--issues-out",
        str(sourcing_issues),
        "--phase",
        str(args.phase),
        "--service-tag",
        str(getattr(args, "service_tag", "CAT")),
    ] + (["--policies", args.policies] if getattr(args, "policies", None) else [])
      + (["--enable-phase2-rules"] if args.enable_phase2_rules else [])
      + (["--enable-production-overrides"] if getattr(args, "enable_production_overrides", False) else [])
      + (["--rollout-categories", args.rollout_categories] if getattr(args, "rollout_categories", None) else []))
    run([
        sys.executable,
        str(SCRIPTS / "cost_recipe.py"),
        "--recipe",
        args.recipe,
        "--offers",
        str(mapped_json),
        "--decisions",
        str(decisions),
        "--defaults",
        args.defaults,
        "--out",
        str(cost_json),
        "--issues-out",
        str(cost_issues),
    ] + (["--confirm-stale"] if args.confirm_stale else []))

    if selected_template in {"A", "B"}:
        # ensure request carries selected template type for payload validator
        req_obj = load_json(request_path)
        req_obj["template_type"] = selected_template
        req_for_payload = out / "selected_proposal_request.json"
        req_for_payload.write_text(json.dumps(req_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        run([
            sys.executable,
            str(SCRIPTS / "generate_proposal_payload.py"),
            "--request",
            str(req_for_payload),
            "--cost",
            str(cost_json),
            "--out",
            str(payload),
            "--validation-out",
            str(validation),
            "--issues-out",
            str(proposal_issues),
        ])

        template = TEMPLATES / ("Template_TypeA.docx" if selected_template == "A" else "Template_TypeB.docx")
        pmap = TEMPLATES / ("placeholder_map_type_a.json" if selected_template == "A" else "placeholder_map_type_b.json")
        run([
            sys.executable,
            str(SCRIPTS / "render_docx.py"),
            "--payload",
            str(payload),
            "--template",
            str(template),
            "--placeholder-map",
            str(pmap),
            "--out",
            str(final_output),
            "--validation-out",
            str(render_validation),
            "--issues-out",
            str(render_issues),
        ])
    else:
        build_typec_payload(str(request_path), str(cost_json), str(payload))
        # keep validation/issues files for symmetry
        validation.write_text(json.dumps({"template_type": "C", "compliance_status": "PASS"}, ensure_ascii=False, indent=2), encoding="utf-8")
        proposal_issues.write_text("[]\n", encoding="utf-8")
        run([
            sys.executable,
            str(SCRIPTS / "render_typec_html.py"),
            "--template",
            str(TEMPLATES / "Template_TypeC_OmbreEtDesir.html"),
            "--payload",
            str(payload),
            "--out",
            str(final_output),
            "--validation-out",
            str(render_validation),
            "--issues-out",
            str(render_issues),
        ])

    all_issues = []
    for p in [sourcing_issues, cost_issues, proposal_issues, render_issues]:
        all_issues.extend(load_json(p))
    decisions_rows = load_json(decisions)

    filing_status = "SKIPPED"
    filing_note = "not_requested"
    filed_manifest = out / "proposal_filing.json"

    summary = [
        "run_type=offer",
        f"template_type={selected_template}",
        f"final_output={final_output}",
        f"proposal_payload={payload}",
        f"proposal_validation={validation}",
        f"proposal_issues={proposal_issues}",
        f"render_validation={render_validation}",
        f"render_issues={render_issues}",
        f"flags_stale={sum(1 for x in all_issues if 'STALE' in x.get('code',''))}",
        f"flags_anomaly={sum(1 for x in all_issues if 'ANOMALY' in x.get('code',''))}",
        f"locks_used={sum(1 for x in decisions_rows if x.get('rule_applied') == 'LOCK')}",
    ]
    write_summary(out / "run_summary.txt", summary)

    if args.file_proposal:
        rv = load_json(render_validation)
        compliance = str(rv.get("compliance_status", ""))
        if compliance == "PASS":
            cmd_file = [
                sys.executable,
                str(SCRIPTS / "file_proposal.py"),
                "--run-dir",
                str(out),
                "--template-type",
                str(selected_template),
                "--proposal-request",
                str(request_path),
                "--proposals-root",
                str(args.proposals_root),
                "--out",
                str(filed_manifest),
            ]
            if args.client:
                cmd_file.extend(["--client", str(args.client)])
            run(cmd_file)
            filing_status = "FILED"
            filing_note = str(filed_manifest)
        else:
            filing_status = "SKIPPED"
            filing_note = f"compliance_status={compliance}"
        summary.append(f"filing_status={filing_status}")
        summary.append(f"filing_note={filing_note}")
        write_summary(out / "run_summary.txt", summary)

    print(str(out))


def main():
    ap = argparse.ArgumentParser(description="Evochia deterministic pipeline runner")
    sp = ap.add_subparsers(dest="command")

    imp = sp.add_parser("import", help="imports-first ingress: csv/ocr -> unified price quotes")
    imp.add_argument("--csv-input", default=None)
    imp.add_argument("--csv-profile", default=str(ROOT / "suppliers" / "supplier_x.json"))
    imp.add_argument("--csv-input-2", default=None)
    imp.add_argument("--csv-profile-2", default=str(ROOT / "suppliers" / "supplier_x.json"))
    imp.add_argument("--ocr-input", default=None)
    imp.add_argument("--ocr-profile", default=str(ROOT / "suppliers" / "supplier_y.json"))
    imp.add_argument("--xlsx-input", default=None)
    imp.add_argument("--xlsx-profile", default=str(ROOT / "suppliers" / "alios.json"))
    imp.add_argument("--pdf-ocr-input", default=None)
    imp.add_argument("--pdf-ocr-profile", default=str(ROOT / "suppliers" / "alios.json"))
    imp.set_defaults(func=cmd_import)

    review = sp.add_parser("review", help="resolve needs_review rows with deterministic patch")
    review.add_argument("--needs-review", required=True)
    review.add_argument("--raw", required=True)
    review.add_argument("--price-quotes", required=True)
    review.add_argument("--patch", required=False, default=None)
    review.add_argument("--export-csv-skeleton", required=False, default=None)
    review.add_argument("--apply-csv", required=False, default=None)
    review.add_argument("--supplier-id", required=False, default=None)
    review.set_defaults(func=cmd_review)

    prices = sp.add_parser("prices", help="price intake/export only")
    prices.add_argument("--raw", required=False, default=None)
    prices.add_argument("--catalog", default=str(ROOT / "data" / "catalog.json"))
    prices.add_argument("--overrides", default=str(ROOT / "config" / "overrides.json"))
    prices.add_argument("--defaults", default=str(ROOT / "config" / "defaults.json"))
    prices.add_argument("--phase", type=int, default=1)
    prices.add_argument("--enable-phase2-rules", action="store_true")
    prices.add_argument("--enable-production-overrides", action="store_true")
    prices.add_argument("--rollout-categories", default="")
    prices.add_argument("--policies", default=None)
    prices.add_argument("--service-tag", default="CAT")
    prices.add_argument("--refresh-needed", action="store_true")
    prices.set_defaults(func=cmd_prices)

    cost = sp.add_parser("cost", help="recipe to cost only")
    cost.add_argument("--recipe", required=True)
    cost.add_argument("--offers", required=True)
    cost.add_argument("--decisions", required=True)
    cost.add_argument("--defaults", default=str(ROOT / "config" / "defaults.json"))
    cost.add_argument("--confirm-stale", action="store_true")
    cost.set_defaults(func=cmd_cost)

    onboard = sp.add_parser("onboard-supplier", help="generate supplier onboarding skeleton and fixture tests")
    onboard.add_argument("--supplier-id", required=True)
    onboard.add_argument("--display-name", required=False, default=None)
    onboard.add_argument("--mode", choices=["xlsx", "pdf-ocr", "both"], default="both")
    onboard.add_argument("--templates-root", default=str(ROOT / "suppliers" / "_templates"))
    onboard.add_argument("--out-dir", default=str(ROOT / "suppliers"))
    onboard.add_argument("--fixtures-dir", default=str(ROOT / "data" / "imports"))
    onboard.add_argument("--run-tests", action="store_true", default=True)
    onboard.add_argument("--no-run-tests", dest="run_tests", action="store_false")
    onboard.set_defaults(func=cmd_onboard_supplier)

    searchp = sp.add_parser("search-proposals", help="search proposal library index")
    searchp.add_argument("--client", default=None)
    searchp.add_argument("--date-from", default=None)
    searchp.add_argument("--date-to", default=None)
    searchp.add_argument("--service", default=None)
    searchp.add_argument("--template", default=None)
    searchp.add_argument("--contains", default=None)
    searchp.add_argument("--limit", type=int, default=20)
    searchp.add_argument("--reindex", action="store_true")
    searchp.set_defaults(func=cmd_search_proposals)

    openr = sp.add_parser("open-result", help="open a result from a pinned search run")
    openr.add_argument("--search-run", required=True)
    openr.add_argument("--n", required=True, type=int)
    openr.add_argument("--copy-to-clipboard", action="store_true")
    openr.set_defaults(func=cmd_open_result)

    opath = sp.add_parser("open-path", help="resolve common run/file targets to absolute+relative paths")
    opath.add_argument("--run", default=None)
    opath.add_argument("--target", choices=["filed", "telegram_reply", "patch_csv", "manifest", "run_summary"], default=None)
    opath.add_argument("--file", default=None)
    opath.add_argument("--copy-to-clipboard", action="store_true")
    opath.set_defaults(func=cmd_open_path)

    rs = sp.add_parser("recipe-skeleton", help="build deterministic recipe skeletons from menu text/items")
    rs.add_argument("--text", default=None)
    rs.add_argument("--items-json", default=None)
    rs.add_argument("--autofill-portions", type=float, default=None)
    rs.set_defaults(func=cmd_recipe_skeleton)

    rr = sp.add_parser("recipe-review", help="map recipe ingredients from null product_id via CSV review")
    rr.add_argument("--recipes", required=True)
    rr.add_argument("--export-csv-skeleton", default=None)
    rr.add_argument("--apply-csv", default=None)
    rr.add_argument("--persist-mode", default="off", choices=["off", "catalog_alias"])
    rr.set_defaults(func=cmd_recipe_review)

    rc = sp.add_parser("recipe-cost", help="cost mapped recipe list using offers/decisions")
    rc.add_argument("--recipes-mapped", required=True)
    rc.add_argument("--offers", default=None)
    rc.add_argument("--decisions", default=None)
    rc.add_argument("--defaults", default=str(ROOT / "config" / "defaults.json"))
    rc.add_argument("--confirm-stale", action="store_true")
    rc.set_defaults(func=cmd_recipe_cost)

    mo = sp.add_parser("menu-offer", help="one-shot menu->offer deterministic chain")
    mo.add_argument("--text", required=True)
    mo.add_argument("--raw", default=None)
    mo.add_argument("--policies", default=str(ROOT / "policies" / "sourcing_policies.json"))
    mo.add_argument("--template-hint", choices=["A", "B", "C"], default=None)
    mo.add_argument("--client", default=None)
    mo.add_argument("--file-proposal", dest="file_proposal", action="store_true", default=True)
    mo.add_argument("--no-file-proposal", dest="file_proposal", action="store_false")
    mo.add_argument("--reply", dest="reply", action="store_true", default=True)
    mo.add_argument("--no-reply", dest="reply", action="store_false")
    mo.set_defaults(func=cmd_menu_offer)

    rsu = sp.add_parser("resume", help="resume blocked menu-offer run deterministically")
    rsu.add_argument("--menu-offer-run", required=True)
    rsu.add_argument("--apply-recipe-review-csv", default=None)
    rsu.add_argument("--raw", default=None)
    rsu.add_argument("--policies", default=None)
    rsu.set_defaults(func=cmd_resume)

    dr = sp.add_parser("daily-refresh", help="supplier round refresh + compact daily digest")
    dr.add_argument("--sources", action="append", default=[])
    dr.add_argument("--defaults", default=str(ROOT / "config" / "daily_refresh_defaults.json"))
    dr.add_argument("--reindex-proposals", dest="reindex_proposals", action="store_true")
    dr.add_argument("--no-reindex-proposals", dest="reindex_proposals", action="store_false")
    dr.add_argument("--run-health-checks", dest="run_health_checks", action="store_true")
    dr.add_argument("--no-run-health-checks", dest="run_health_checks", action="store_false")
    dr.add_argument("--policies", default=str(ROOT / "policies" / "sourcing_policies.json"))
    dr.add_argument("--no-preflight", action="store_true", default=False)
    dr.add_argument("--auto-register", action="store_true", default=False)
    dr.add_argument("--no-auto-update", action="store_true", default=False)
    dr.add_argument("--auto-register-web", action="store_true", default=False)
    dr.add_argument("--reply", dest="reply", action="store_true")
    dr.add_argument("--no-reply", dest="reply", action="store_false")
    dr.add_argument("--file-proposal", dest="file_proposal", action="store_true")
    dr.set_defaults(func=cmd_daily_refresh, reindex_set=False, health_set=False, reply_set=False, file_proposal_set=False)

    sh = sp.add_parser("source-health", help="preflight registry source health checks")
    sh.add_argument("--sources", action="append", default=[])
    sh.add_argument("--defaults", default=str(ROOT / "config" / "daily_refresh_defaults.json"))
    sh.add_argument("--include-web", action="store_true", default=False)
    sh.add_argument("--reply", dest="reply", action="store_true", default=True)
    sh.add_argument("--no-reply", dest="reply", action="store_false")
    sh.set_defaults(func=cmd_source_health)

    ss = sp.add_parser("source-status", help="show persisted source last-seen/last-success state")
    ss.add_argument("--only-broken", action="store_true", default=False)
    ss.add_argument("--only-stale", action="store_true", default=False)
    ss.add_argument("--days", type=int, default=7)
    ss.add_argument("--reply", dest="reply", action="store_true", default=True)
    ss.add_argument("--no-reply", dest="reply", action="store_false")
    ss.set_defaults(func=cmd_source_status)

    al = sp.add_parser("alias", help="print deterministic one-liner alias command")
    al.add_argument("--name", required=True, choices=["daily", "health", "status"])
    al.set_defaults(func=cmd_alias)

    adds = sp.add_parser("add-source", help="add or replace source registry entry")
    adds.add_argument("--key", required=True)
    adds.add_argument("--type", required=True)
    adds.add_argument("--path", action="append", required=True)
    adds.add_argument("--display-name", default=None)
    adds.add_argument("--supplier-id", default=None)
    adds.add_argument("--replace", action="store_true")
    adds.add_argument("--dry-run", action="store_true")
    adds.add_argument("--reply", action="store_true", default=True)
    adds.set_defaults(func=cmd_add_source)

    lss = sp.add_parser("list-sources", help="list source registry entries")
    lss.set_defaults(func=cmd_list_sources)

    rms = sp.add_parser("remove-source", help="remove source registry entry")
    rms.add_argument("--key", required=True)
    rms.add_argument("--dry-run", action="store_true")
    rms.add_argument("--reply", action="store_true", default=True)
    rms.set_defaults(func=cmd_remove_source)

    eds = sp.add_parser("edit-source", help="edit source registry entry")
    eds.add_argument("--key", required=True)
    eds.add_argument("--add-path", action="append", default=[])
    eds.add_argument("--remove-path", action="append", default=[])
    eds.add_argument("--set-display-name", default=None)
    eds.add_argument("--set-supplier-id", default=None)
    eds.add_argument("--dry-run", action="store_true")
    eds.set_defaults(func=cmd_edit_source)

    aws = sp.add_parser("add-web-source", help="add or replace lightweight web source")
    aws.add_argument("--key", required=True)
    aws.add_argument("--url", required=True)
    aws.add_argument("--tags", default="")
    aws.add_argument("--replace", action="store_true")
    aws.add_argument("--dry-run", action="store_true")
    aws.set_defaults(func=cmd_add_web_source)

    oh = sp.add_parser("ops-help", help="telegram-first operator daily loop help")
    oh.set_defaults(func=cmd_ops_help)

    intake = sp.add_parser("intake", help="telegram-first intake from free text")
    intake.add_argument("--text", required=True)
    intake.add_argument("--defaults", default=str(ROOT / "config" / "defaults.json"))
    intake.add_argument("--channel", default="telegram")
    intake.add_argument("--run-offer", action="store_true")
    intake.add_argument("--file-proposal", action="store_true")
    intake.add_argument("--reply", action="store_true")
    intake.add_argument("--raw", required=False, default=None)
    intake.add_argument("--recipe", required=False, default=None)
    intake.add_argument("--policies", default=str(ROOT / "policies" / "sourcing_policies.json"))
    intake.add_argument("--client", required=False, default=None)
    intake.set_defaults(func=cmd_intake)

    offer = sp.add_parser("offer", help="cost + payload + render")
    offer.add_argument("--template-type", required=False, choices=["A", "B", "C"])
    offer.add_argument("--proposal-request", required=False)
    offer.add_argument("--raw", required=True)
    offer.add_argument("--recipe", required=True)
    offer.add_argument("--request", required=False)
    offer.add_argument("--catalog", default=str(ROOT / "data" / "catalog.json"))
    offer.add_argument("--overrides", default=str(ROOT / "config" / "overrides.json"))
    offer.add_argument("--defaults", default=str(ROOT / "config" / "defaults.json"))
    offer.add_argument("--phase", type=int, default=1)
    offer.add_argument("--enable-phase2-rules", action="store_true")
    offer.add_argument("--enable-production-overrides", action="store_true")
    offer.add_argument("--rollout-categories", default="")
    offer.add_argument("--policies", default=None)
    offer.add_argument("--service-tag", default="CAT")
    offer.add_argument("--confirm-stale", action="store_true")
    offer.add_argument("--file-proposal", action="store_true")
    offer.add_argument("--proposals-root", default=str(ROOT / "proposals"))
    offer.add_argument("--client", required=False, default=None)
    offer.set_defaults(func=cmd_offer)

    args = ap.parse_args()
    if not hasattr(args, "func"):
        print(
            "Usage examples:\n"
            "  import: python scripts/run_pipeline.py import --csv-input data/imports/supplier_x_prices.csv --ocr-input data/imports/supplier_y_ocr_rows.json\n"
            "  review: python scripts/run_pipeline.py review --needs-review runs/<ts>/prices/needs_review_import.json --raw runs/<ts>/prices/raw_merged.json --price-quotes runs/<ts>/prices/price_quotes.json --supplier-id 4fsa --export-csv-skeleton data/imports/review_patch_skeleton.csv\n"
            "  prices: python scripts/run_pipeline.py prices --raw data/prices/sample_offers.json\n"
            "  cost:   python scripts/run_pipeline.py cost --recipe data/recipes/sample_recipe.json --offers data/prices/sample_offers_mapped.json --decisions data/prices/sample_decisions.json\n"
            "  offer:  python scripts/run_pipeline.py offer --template-type B --raw data/prices/sample_offers.json --recipe data/recipes/sample_recipe.json --request data/sample_proposal_request.json"
        )
        return
    args.func(args)


if __name__ == "__main__":
    main()
