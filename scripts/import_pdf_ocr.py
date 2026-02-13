import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CRITICAL_FIELDS = ["desc", "qty", "unit", "net"]


def add_issue(issues, severity, code, message, **extra):
    row = {"severity": severity, "code": code, "message": message}
    row.update(extra)
    issues.append(row)


def to_float(v, default=None):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def main():
    p = argparse.ArgumentParser(description="PDF+OCR import -> RawOffer[]")
    p.add_argument("--input", required=True, help="OCR structured rows json from PDF")
    p.add_argument("--pdf-path", required=False, default=None)
    p.add_argument("--supplier-profile", required=True)
    p.add_argument("--captured-at", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--batch-out", required=True)
    p.add_argument("--needs-review", required=False, default=None)
    p.add_argument("--issues-out", required=False, default=None)
    args = p.parse_args()

    profile = json.loads(Path(args.supplier_profile).read_text(encoding="utf-8"))
    defaults = profile.get("defaults", {})
    cmap = profile.get("column_map", {})
    unit_map = {str(k).upper(): v for k, v in (profile.get("unit_map", {}) or {}).items()}
    layout_rules = profile.get("layout_rules", {})

    captured = datetime.now(timezone.utc) if not args.captured_at else datetime.fromisoformat(args.captured_at.replace("Z", "+00:00"))
    catalog_valid_days = int(profile.get("catalog_valid_days", defaults.get("max_age_days", 14)))
    valid_until = captured + timedelta(days=catalog_valid_days)

    input_path = Path(args.input)
    src = json.loads(input_path.read_text(encoding="utf-8"))
    source_hash = hashlib.sha1(input_path.read_bytes()).hexdigest()[:10]

    if isinstance(src, dict):
        rows_in = src.get("rows", [])
        anchors_detected = src.get("anchors_detected", [])
        table_pattern = src.get("table_pattern")
    else:
        rows_in = src
        anchors_detected = []
        table_pattern = None

    issues = []
    needs_review = []
    rows = []

    required_anchors = layout_rules.get("required_anchors", [])
    required_pattern = layout_rules.get("required_table_pattern")

    anchors_ok = all(a in anchors_detected for a in required_anchors)
    pattern_ok = (required_pattern is None or table_pattern == required_pattern)

    if not anchors_ok or not pattern_ok:
        add_issue(
            issues,
            "BLOCK",
            "SUPPLIER-LAYOUT-UNKNOWN",
            "Layout anchors/table pattern mismatch; parse blocked",
            supplier_id=profile.get("supplier_id"),
            layout_version=profile.get("layout_version", "v1"),
            required_anchors=required_anchors,
            anchors_detected=anchors_detected,
            required_table_pattern=required_pattern,
            table_pattern=table_pattern,
        )
        for i, r in enumerate(rows_in, start=1):
            needs_review.append(
                {
                    "offer_id": f"OFF-{profile.get('supplier_code','SUP')}-{captured.strftime('%Y%m%d')}-{i:04d}",
                    "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                    "supplier_sku": r.get(cmap.get("supplier_sku", "item_code"), ""),
                    "product_name": r.get(cmap.get("product_name", "desc"), ""),
                    "reason": "SUPPLIER-LAYOUT-UNKNOWN",
                    "action": "BLOCK_UNTIL_REVIEWED",
                }
            )
    else:
        for i, x in enumerate(rows_in, start=1):
            offer_id = f"OFF-{profile.get('supplier_code','SUP')}-{captured.strftime('%Y%m%d')}-{i:04d}"
            row_raw = {
                "item_code": x.get(cmap.get("supplier_sku", "item_code"), ""),
                "desc": x.get(cmap.get("product_name", "desc"), ""),
                "qty": x.get(cmap.get("qty", "qty")),
                "unit": x.get(cmap.get("unit", "unit")),
                "net": x.get(cmap.get("price", "net"), x.get(cmap.get("net", "net"))),
                "vat_rate": x.get(cmap.get("vat_rate", "vat_rate"), defaults.get("vat_rate", 0.13)),
            }

            missing = [f for f in CRITICAL_FIELDS if row_raw.get(f) in (None, "")]
            if missing:
                add_issue(issues, "WARNING", "IMPORT-MISSING-CRITICAL-FIELD", "Critical field missing; row sent to needs_review", offer_id=offer_id, missing_fields=missing)
                needs_review.append({
                    "offer_id": offer_id,
                    "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                    "supplier_sku": row_raw.get("item_code", ""),
                    "product_name": row_raw.get("desc", ""),
                    "reason": "IMPORT-MISSING-CRITICAL-FIELD",
                    "missing_fields": missing,
                    "action": "BLOCK_UNTIL_REVIEWED",
                })
                continue

            unit_src = str(row_raw.get("unit", "")).upper().strip()
            unit_norm = unit_map.get(unit_src)
            if unit_norm is None:
                add_issue(issues, "WARNING", "IMPORT-UNSUPPORTED-UNIT", "Unsupported OCR unit; row sent to needs_review", offer_id=offer_id, raw_unit=unit_src)
                needs_review.append({
                    "offer_id": offer_id,
                    "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                    "supplier_sku": row_raw.get("item_code", ""),
                    "product_name": row_raw.get("desc", ""),
                    "reason": "IMPORT-UNSUPPORTED-UNIT",
                    "raw_unit": unit_src,
                    "action": "BLOCK_UNTIL_REVIEWED",
                })
                continue

            qty = to_float(row_raw.get("qty"), None)
            price = to_float(row_raw.get("net"), None)
            if qty is None or qty <= 0 or price is None:
                add_issue(issues, "WARNING", "IMPORT-NUMERIC-PARSE-FAILED", "qty/net parse failed; row sent to needs_review", offer_id=offer_id)
                needs_review.append({
                    "offer_id": offer_id,
                    "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                    "supplier_sku": row_raw.get("item_code", ""),
                    "product_name": row_raw.get("desc", ""),
                    "reason": "IMPORT-NUMERIC-PARSE-FAILED",
                    "action": "BLOCK_UNTIL_REVIEWED",
                })
                continue

            rows.append({
                "offer_id": offer_id,
                "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                "supplier_sku": row_raw.get("item_code", ""),
                "product_name": row_raw.get("desc", ""),
                "category": x.get("category", ""),
                "tier": defaults.get("tier", "standard"),
                "pack_size": qty,
                "pack_unit": unit_norm,
                "price": price,
                "price_per_base_unit": None,
                "currency": x.get("currency", defaults.get("currency", "EUR")),
                "vat_rate": to_float(row_raw.get("vat_rate"), defaults.get("vat_rate", 0.13)),
                "captured_at": captured.isoformat(),
                "valid_until": valid_until.isoformat(),
                "source": f"import_pdf_ocr:{Path(args.input).name}",
                "in_stock": x.get("in_stock", True),
                "notes": x.get("notes", ""),
            })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    files = [{"path": str(args.input), "kind": "pdf_ocr_json"}]
    if args.pdf_path:
        files.append({"path": str(args.pdf_path), "kind": "pdf"})

    batch = {
        "batch_id": f"BATCH-{profile.get('supplier_id','unknown')}-{captured.strftime('%Y%m%d-%H%M%S')}-{source_hash}",
        "source": "pdf_ocr",
        "source_hash": source_hash,
        "supplier_id": profile.get("supplier_id", "unknown"),
        "layout_version": profile.get("layout_version", "v1"),
        "captured_at": captured.isoformat(),
        "catalog_valid_days": catalog_valid_days,
        "files": files,
        "stats": {
            "rows_in": len(rows_in),
            "rows_out": len(rows),
            "rows_needs_review": len(needs_review),
        },
    }
    Path(args.batch_out).write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.needs_review:
        Path(args.needs_review).parent.mkdir(parents=True, exist_ok=True)
        Path(args.needs_review).write_text(json.dumps(needs_review, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.issues_out:
        Path(args.issues_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.issues_out).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"rows": len(rows), "needs_review": len(needs_review), "issues": len(issues), "batch": batch["batch_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
