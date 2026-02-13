import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path, row):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def to_float(v, fallback=None):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return fallback


def export_csv_skeleton(needs, raw_rows, out_csv):
    raw_by_offer = {r.get("offer_id"): r for r in raw_rows if r.get("offer_id")}
    cols = [
        "needs_review_id",
        "supplier_sku",
        "raw_desc",
        "qty",
        "unit_raw",
        "net_price",
        "issue_code",
        "suggestion_1",
        "suggestion_2",
        "suggestion_3",
        "set_product_id",
        "set_unit",
        "set_pack_size",
        "set_pack_unit",
        "persist_mode",
        "reason",
    ]
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_csv).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for n in needs:
            oid = n.get("offer_id", "")
            rr = raw_by_offer.get(oid, {})
            w.writerow(
                {
                    "needs_review_id": oid,
                    "supplier_sku": n.get("supplier_sku", rr.get("supplier_sku", "")),
                    "raw_desc": n.get("product_name", rr.get("product_name", "")),
                    "qty": rr.get("pack_size", ""),
                    "unit_raw": n.get("raw_unit", rr.get("pack_unit", "")),
                    "net_price": rr.get("price", ""),
                    "issue_code": n.get("reason", n.get("code", "UNKNOWN")),
                    "suggestion_1": "",
                    "suggestion_2": "",
                    "suggestion_3": "",
                    "set_product_id": "",
                    "set_unit": "",
                    "set_pack_size": "",
                    "set_pack_unit": "",
                    "persist_mode": "",
                    "reason": "",
                }
            )


def csv_to_patch(csv_path):
    patch = {}
    rows_meta = {}
    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            oid = (r.get("needs_review_id") or "").strip()
            if not oid:
                continue
            patch[oid] = {
                "product_id": (r.get("set_product_id") or "").strip() or None,
                "pack_unit": (r.get("set_pack_unit") or r.get("set_unit") or "").strip() or None,
                "pack_size": to_float(r.get("set_pack_size"), None),
                "price": to_float(r.get("net_price"), None),
                "product_name": (r.get("raw_desc") or "").strip(),
                "persist_mode": (r.get("persist_mode") or "").strip(),
                "reason": (r.get("reason") or "").strip(),
                "supplier_sku": (r.get("supplier_sku") or "").strip(),
            }
            rows_meta[oid] = dict(r)
    return patch, rows_meta


def build_template_patch(needs):
    template_patch = {
        "instructions": "Fill values by offer_id. Required for resolution: set_product_id, set_pack_unit or set_unit, set_pack_size, net_price.",
        "entries": {},
    }
    for n in needs:
        oid = n.get("offer_id")
        template_patch["entries"][oid] = {
            "set_product_id": "",
            "set_unit": "",
            "set_pack_size": "",
            "set_pack_unit": "",
            "net_price": "",
            "persist_mode": "",
            "reason": "",
        }
    return template_patch


def main():
    p = argparse.ArgumentParser(description="Review + resolve needs_review rows with deterministic patch")
    p.add_argument("--needs-review", required=True)
    p.add_argument("--raw", required=True, help="raw_merged.json from import run")
    p.add_argument("--price-quotes", required=True, help="existing price_quotes.json")
    p.add_argument("--patch", required=False, default=None, help="json patch keyed by offer_id")
    p.add_argument("--apply-csv", required=False, default=None, help="csv patch form")
    p.add_argument("--export-csv-skeleton", required=False, default=None)
    p.add_argument("--out-price-quotes", required=True)
    p.add_argument("--out-needs-review", required=True)
    p.add_argument("--out-issues", required=True)
    p.add_argument("--mapping-patch-out", required=True)
    p.add_argument("--summary-out", required=True)
    p.add_argument("--supplier-id", required=False, default=None)
    p.add_argument("--sku-map", required=False, default=None)
    p.add_argument("--unit-rules", required=False, default=None)
    p.add_argument("--catalog-aliases", required=False, default=str(ROOT / "mappings" / "catalog_aliases.jsonl"))
    p.add_argument("--audit-log", required=False, default=str(ROOT / "audit" / "mapping_persist_log.jsonl"))
    p.add_argument("--audit-out", required=False, default=None)
    args = p.parse_args()

    needs = load_json(args.needs_review, [])
    raw = load_json(args.raw, [])

    if args.supplier_id:
        if args.sku_map is None:
            args.sku_map = str(ROOT / "mappings" / "supplier_sku_map" / f"{args.supplier_id}.json")
        if args.unit_rules is None:
            args.unit_rules = str(ROOT / "mappings" / "unit_rules" / f"{args.supplier_id}.json")

    if args.export_csv_skeleton:
        export_csv_skeleton(needs, raw, args.export_csv_skeleton)

    if args.apply_csv:
        if not args.supplier_id:
            raise RuntimeError("BLOCK: supplier_id is required for --apply-csv persist")
        patch, _ = csv_to_patch(args.apply_csv)
    elif args.patch:
        patch = load_json(args.patch, {})
    else:
        patch = {}

    by_offer = {r.get("offer_id"): dict(r) for r in raw if r.get("offer_id")}

    code_counts = Counter()
    for n in needs:
        code_counts[n.get("reason") or n.get("code") or "UNKNOWN"] += 1

    template_patch = build_template_patch(needs)

    sku_map = load_json(args.sku_map, {}) if args.sku_map else {}
    unit_rules = load_json(args.unit_rules, {}) if args.unit_rules else {}
    audit = []

    resolved = 0
    unresolved = []
    issues = []

    for n in needs:
        oid = n.get("offer_id")
        row_patch = patch.get(oid)
        if not row_patch:
            unresolved.append(n)
            continue

        base = by_offer.get(
            oid,
            {
                "offer_id": oid,
                "supplier": n.get("supplier", ""),
                "supplier_sku": n.get("supplier_sku", ""),
                "product_name": n.get("product_name", ""),
                "category": "",
                "tier": "standard",
                "currency": "EUR",
                "vat_rate": 0.13,
                "captured_at": None,
                "valid_until": None,
                "in_stock": True,
            },
        )

        product_id = row_patch.get("product_id")
        unit = (row_patch.get("pack_unit") or "").strip() if row_patch.get("pack_unit") else ""
        size = to_float(row_patch.get("pack_size"), None)
        price = to_float(row_patch.get("price"), None)

        if not product_id:
            unresolved.append(n)
            issues.append(
                {
                    "severity": "WARNING",
                    "code": "REVIEW-PATCH-MISSING-PRODUCT-ID",
                    "message": "set_product_id missing; row unresolved",
                    "offer_id": oid,
                }
            )
            continue

        supplier = base.get("supplier", "")
        supplier_sku = (row_patch.get("supplier_sku") or base.get("supplier_sku") or "").strip()
        sku_key = f"{supplier}::{supplier_sku}"
        existing = sku_map.get(sku_key)
        if existing and existing != product_id:
            unresolved.append(n)
            entry = {
                "severity": "BLOCK",
                "code": "REVIEW-SKU-MAP-CONFLICT",
                "message": "set_product_id conflicts with existing sku_map",
                "offer_id": oid,
                "supplier_id": args.supplier_id,
                "sku_key": sku_key,
                "existing_product_id": existing,
                "new_product_id": product_id,
            }
            issues.append(entry)
            audit.append(entry)
            append_jsonl(args.audit_log, {**entry, "ts": datetime.now(timezone.utc).isoformat()})
            continue

        if unit == "" or size is None or price is None:
            unresolved.append(n)
            issues.append(
                {
                    "severity": "WARNING",
                    "code": "REVIEW-PATCH-INCOMPLETE",
                    "message": "Patch row missing required fields",
                    "offer_id": oid,
                }
            )
            continue

        base["product_id"] = product_id
        base["pack_unit"] = unit
        base["pack_size"] = size
        base["price"] = price
        if row_patch.get("product_name"):
            base["product_name"] = row_patch.get("product_name")

        by_offer[oid] = base
        resolved += 1

        persist_mode = (row_patch.get("persist_mode") or "").strip()
        if persist_mode == "sku_map" and supplier_sku:
            sku_map[sku_key] = product_id
            entry = {
                "severity": "INFO",
                "code": "REVIEW-SKU-MAP-PERSISTED",
                "offer_id": oid,
                "sku_key": sku_key,
                "product_id": product_id,
                "supplier_id": args.supplier_id,
                "reason": row_patch.get("reason", ""),
            }
            audit.append(entry)
            append_jsonl(args.audit_log, {**entry, "ts": datetime.now(timezone.utc).isoformat()})
        elif persist_mode == "unit_rule" and supplier_sku:
            unit_rules[supplier_sku] = {
                "set_unit": row_patch.get("pack_unit"),
                "set_pack_size": row_patch.get("pack_size"),
            }
            entry = {
                "severity": "INFO",
                "code": "REVIEW-UNIT-RULE-PERSISTED",
                "offer_id": oid,
                "supplier_sku": supplier_sku,
                "supplier_id": args.supplier_id,
                "reason": row_patch.get("reason", ""),
            }
            audit.append(entry)
            append_jsonl(args.audit_log, {**entry, "ts": datetime.now(timezone.utc).isoformat()})
        elif persist_mode == "alias":
            alias_row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "supplier_id": args.supplier_id,
                "offer_id": oid,
                "supplier_sku": supplier_sku,
                "raw_desc": base.get("product_name", ""),
                "product_id": product_id,
                "reason": row_patch.get("reason", ""),
            }
            append_jsonl(args.catalog_aliases, alias_row)
            entry = {
                "severity": "INFO",
                "code": "REVIEW-ALIAS-PERSISTED",
                "offer_id": oid,
                "supplier_id": args.supplier_id,
                "product_id": product_id,
            }
            audit.append(entry)
            append_jsonl(args.audit_log, {**entry, "ts": datetime.now(timezone.utc).isoformat()})

    if args.sku_map:
        save_json(args.sku_map, sku_map)
    if args.unit_rules:
        save_json(args.unit_rules, unit_rules)

    reviewed_raw = list(by_offer.values())
    tmp_raw = Path(args.out_price_quotes).with_suffix(".review_raw.json")
    save_json(tmp_raw, reviewed_raw)

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "normalize_import_batch.py"),
        "--input",
        str(tmp_raw),
        "--out",
        args.out_price_quotes,
        "--needs-review",
        str(args.out_needs_review),
        "--issues-out",
        str(args.out_issues),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"normalize failed\n{r.stdout}\n{r.stderr}")

    post_needs = load_json(args.out_needs_review, [])
    post_issues = load_json(args.out_issues, [])
    merged_issues = issues + post_issues
    save_json(args.out_issues, merged_issues)

    if args.audit_out:
        save_json(args.audit_out, audit)

    save_json(args.mapping_patch_out, template_patch)

    remaining_total = len(unresolved) + len(post_needs)
    summary = {
        "needs_review_total": len(needs),
        "counts_by_code": dict(code_counts),
        "top_ambiguous_lines": needs[:10],
        "resolved_via_patch": resolved,
        "remaining_needs_review": remaining_total,
        "next_action": "DONE" if remaining_total == 0 else f"run review again to resolve {remaining_total} lines",
    }
    save_json(args.summary_out, summary)

    print(json.dumps({"resolved": resolved, "remaining": len(post_needs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
