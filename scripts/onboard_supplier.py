import argparse
import json
from pathlib import Path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suf = path.suffix
    n = 2
    while True:
        p = path.with_name(f"{stem}_v{n}{suf}")
        if not p.exists():
            return p
        n += 1


def write_json_no_overwrite(path: Path, obj: dict):
    target = unique_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_text_no_overwrite(path: Path, text: str):
    target = unique_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def build_profile(supplier_id: str, display_name: str):
    return {
        "supplier_id": supplier_id,
        "supplier_name": display_name,
        "supplier_code": supplier_id[:3].upper(),
        "layout_version": "v1",
        "layout_rules": {
            "required_anchors": ["ΤΙΜΟΛΟΓΙΟ", "ΠΕΡΙΓΡΑΦΗ", "ΤΙΜΗ"],
            "required_table_pattern": "line_items_v1"
        },
        "column_map": {
            "supplier_sku": "item_code",
            "product_name": "desc",
            "category": "category",
            "pack_size": "qty",
            "pack_unit": "unit",
            "price": "net",
            "currency": "currency",
            "vat_rate": "vat_rate",
            "in_stock": "in_stock"
        },
        "unit_map": {
            "ΚΙΛ": "kg",
            "KG": "kg",
            "ΤΕΜ": "pcs",
            "PCS": "pcs",
            "ΛΙΤ": "lt",
            "LT": "lt"
        },
        "xlsx": {
            "sheet": None,
            "header_row": 1,
            "column_map": {
                "supplier_sku": "item_code",
                "product_name": "desc",
                "category": "category",
                "pack_size": "qty",
                "pack_unit": "unit",
                "price": "net",
                "currency": "currency",
                "vat_rate": "vat_rate",
                "in_stock": "in_stock"
            },
            "required_columns": ["item_code", "desc", "qty", "unit", "net"],
            "stop_rules": {"blank_product_name": True}
        },
        "pdf_ocr": {
            "required_anchors": ["ΤΙΜΟΛΟΓΙΟ", "ΠΕΡΙΓΡΑΦΗ", "ΤΙΜΗ"],
            "required_table_pattern": "line_items_v1"
        },
        "defaults": {
            "currency": "EUR",
            "vat_rate": 0.13,
            "tier": "standard",
            "max_age_days": 14
        }
    }


def main():
    p = argparse.ArgumentParser(description="Generate deterministic supplier onboarding skeleton")
    p.add_argument("--supplier-id", required=True)
    p.add_argument("--display-name", required=False, default=None)
    p.add_argument("--mode", choices=["xlsx", "pdf-ocr", "both"], default="both")
    p.add_argument("--templates-root", default="skills/evochia-ops/suppliers/_templates")
    p.add_argument("--out-dir", default="skills/evochia-ops/suppliers")
    p.add_argument("--fixtures-dir", default="skills/evochia-ops/data/imports")
    p.add_argument("--run-tests", action="store_true", default=True)
    p.add_argument("--no-run-tests", dest="run_tests", action="store_false")
    p.add_argument("--summary-out", required=False, default=None)
    args = p.parse_args()

    sid = args.supplier_id.strip().lower()
    dname = args.display_name or sid.replace("_", " ").title()

    out_dir = Path(args.out_dir)
    fx_root = Path(args.fixtures_dir) / "fixtures" / sid

    profile = build_profile(sid, dname)
    if args.mode == "xlsx":
        profile.pop("pdf_ocr", None)
    elif args.mode == "pdf-ocr":
        profile.pop("xlsx", None)

    created = []

    profile_path = write_json_no_overwrite(out_dir / f"{sid}.json", profile)
    created.append(str(profile_path))

    # xlsx fixtures (structured skeleton)
    if args.mode in {"xlsx", "both"}:
        xlsx_complete = {
            "rows": [
                {"item_code": f"{sid[:3].upper()}-001", "desc": "Demo Item 1", "qty": "10", "unit": "KG", "net": "9.90", "currency": "EUR", "vat_rate": "0.13", "in_stock": True, "category": "dry"}
            ]
        }
        xlsx_broken = {
            "rows": [
                {"item_code": f"{sid[:3].upper()}-002", "desc": "Demo Item 2", "qty": "10", "unit": "KG", "currency": "EUR", "vat_rate": "0.13", "in_stock": True, "category": "dry"}
            ]
        }
        created.append(str(write_json_no_overwrite(fx_root / "xlsx_v1_complete.json", xlsx_complete)))
        created.append(str(write_json_no_overwrite(fx_root / "xlsx_v1_broken_missing_price.json", xlsx_broken)))

    # pdf-ocr fixtures
    if args.mode in {"pdf-ocr", "both"}:
        pdf_complete = {
            "anchors_detected": ["ΤΙΜΟΛΟΓΙΟ", "ΠΕΡΙΓΡΑΦΗ", "ΤΙΜΗ"],
            "table_pattern": "line_items_v1",
            "rows": [
                {"item_code": f"{sid[:3].upper()}-PDF-001", "desc": "Demo PDF Item", "qty": "5", "unit": "KG", "net": "12.50", "currency": "EUR", "vat_rate": "0.13", "in_stock": True, "category": "seafood"}
            ]
        }
        pdf_layout_unknown = {
            "anchors_detected": ["WRONG", "ANCHOR"],
            "table_pattern": "unknown_pattern",
            "rows": [
                {"item_code": f"{sid[:3].upper()}-PDF-002", "desc": "Broken Layout Item", "qty": "5", "unit": "KG", "net": "12.50", "currency": "EUR", "vat_rate": "0.13", "in_stock": True, "category": "seafood"}
            ]
        }
        created.append(str(write_json_no_overwrite(fx_root / "pdfocr_v1_complete.json", pdf_complete)))
        created.append(str(write_json_no_overwrite(fx_root / "pdfocr_v1_layout_unknown.json", pdf_layout_unknown)))

    report = (
        f"# ONBOARDING_REPORT ({sid})\n\n"
        f"status: READY\n\n"
        f"Generated artifacts:\n" + "\n".join([f"- {x}" for x in created]) + "\n\n"
        "Next actions:\n"
        "- Fill real anchors/table pattern from real supplier docs\n"
        "- Adjust column_map for actual headers\n"
        "- Extend unit_map if new units appear\n"
    )
    rep_path = write_text_no_overwrite(fx_root / "ONBOARDING_REPORT.md", report)
    created.append(str(rep_path))

    out = {
        "status": "READY",
        "supplier_id": sid,
        "profile": str(profile_path),
        "fixtures_root": str(fx_root),
        "artifacts": created,
    }

    if args.summary_out:
        Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
