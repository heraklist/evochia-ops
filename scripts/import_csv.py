import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


def to_bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def to_float(v, default=None):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def parse_price_text(v):
    s = str(v or "").strip().lower()
    if not s:
        return None
    s = s.replace("ευρώ", "").replace("euro", "").replace("€", "")
    s = s.replace("χωρίς φπα", "").replace("χωρις φπα", "")
    s = s.replace("χωρίς", "").replace("χωρις", "").replace("φπα", "")
    m = re.search(r"(\d+(?:[\.,]\d+)?)", s)
    if not m:
        return None
    return to_float(m.group(1), None)


def infer_pack_from_name(name: str, assume_per_kg: bool):
    txt = str(name or "")
    low = txt.lower()

    # keyword rule
    if "γλαστράκι" in low or "γλαστρακι" in low:
        return 1.0, "pcs", "RULE_GLASTRAKI_PCS"

    # strict unambiguous extraction from (...) first
    for pat, unit in [
        (r"\((\d+(?:[\.,]\d+)?)\s*(g|gr)\)", "g"),
        (r"\((\d+(?:[\.,]\d+)?)\s*(kg)\)", "kg"),
    ]:
        m = re.search(pat, low)
        if m:
            return to_float(m.group(1), 1.0), unit, "RULE_PACK_FROM_PARENS"

    if assume_per_kg:
        return 1.0, "kg", "RULE_THEMART_ASSUME_PER_KG"

    return 1.0, "", "RULE_NO_PACK"


def main():
    p = argparse.ArgumentParser(description="Import supplier CSV -> RawOffer[]")
    p.add_argument("--input", required=True)
    p.add_argument("--supplier-profile", required=True)
    p.add_argument("--captured-at", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--batch-out", required=True)
    args = p.parse_args()

    profile = json.loads(Path(args.supplier_profile).read_text(encoding="utf-8"))
    cmap = profile.get("column_map", {})
    defaults = profile.get("defaults", {})
    csv_rules = profile.get("csv_rules", {})

    captured = datetime.now(timezone.utc) if not args.captured_at else datetime.fromisoformat(args.captured_at.replace("Z", "+00:00"))
    catalog_valid_days = int(profile.get("catalog_valid_days", defaults.get("max_age_days", 14)))
    valid_until = captured + timedelta(days=catalog_valid_days)

    file_bytes = Path(args.input).read_bytes()
    source_hash = hashlib.sha1(file_bytes).hexdigest()[:10]

    rows = []
    with Path(args.input).open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for i, x in enumerate(r, start=1):
            sku = x.get(cmap.get("supplier_sku", "supplier_sku"), "")
            name = x.get(cmap.get("product_name", "product_name"), "")

            # price parse (supports raw textual price like "3,07€ χωρίς ΦΠΑ")
            raw_price = x.get(cmap.get("price", "price"), x.get(cmap.get("net_price_raw", "net_price_raw"), ""))
            if csv_rules.get("price_text_parse", False):
                price = parse_price_text(raw_price)
            else:
                price = to_float(raw_price, None)

            # pack/unit inference
            pack_size_src = x.get(cmap.get("pack_size", "pack_size"), None)
            pack_unit_src = x.get(cmap.get("pack_unit", "pack_unit"), "")
            pack_size = to_float(pack_size_src, None)
            pack_unit = str(pack_unit_src or "").strip()

            if csv_rules.get("infer_pack_from_name", False):
                if pack_size is None or not pack_unit:
                    ps, pu, _ = infer_pack_from_name(name, bool(csv_rules.get("themart_assume_per_kg", False)))
                    pack_size = ps if pack_size is None else pack_size
                    pack_unit = pu if not pack_unit else pack_unit

            if pack_size is None:
                pack_size = 1.0

            row = {
                "offer_id": f"OFF-{profile.get('supplier_code','SUP')}-{captured.strftime('%Y%m%d')}-{i:04d}",
                "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                "supplier_sku": sku,
                "product_name": name,
                "category": x.get(cmap.get("category", "category"), csv_rules.get("default_category", "produce")),
                "tier": defaults.get("tier", "standard"),
                "pack_size": pack_size,
                "pack_unit": pack_unit,
                "price": price if price is not None else 0.0,
                "price_per_base_unit": None,
                "currency": x.get(cmap.get("currency", "currency"), defaults.get("currency", "EUR")),
                "vat_rate": to_float(x.get(cmap.get("vat_rate", "vat_rate"), defaults.get("vat_rate", 0.13)), 0.13),
                "captured_at": captured.isoformat(),
                "valid_until": valid_until.isoformat(),
                "source": f"import_csv:{Path(args.input).name}",
                "in_stock": to_bool(x.get(cmap.get("in_stock", "in_stock"), True)),
                "notes": "",
                "metadata": {
                    "raw_desc": x.get(cmap.get("raw_desc", "raw_desc"), ""),
                    "net_price_raw": x.get(cmap.get("net_price_raw", "net_price_raw"), raw_price),
                    "url": x.get(cmap.get("url", "url"), ""),
                    "diff_status": x.get(cmap.get("diff_status", "diff_status"), ""),
                    "sources": x.get(cmap.get("sources", "sources"), ""),
                },
            }
            rows.append(row)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    batch = {
        "batch_id": f"BATCH-{profile.get('supplier_id','unknown')}-{captured.strftime('%Y%m%d-%H%M%S')}-{source_hash}",
        "source": "csv",
        "source_hash": source_hash,
        "supplier_id": profile.get("supplier_id", "unknown"),
        "layout_version": profile.get("layout_version", "v1"),
        "captured_at": captured.isoformat(),
        "catalog_valid_days": catalog_valid_days,
        "files": [{"path": str(args.input), "kind": "csv"}],
        "stats": {
            "rows_in": len(rows),
            "rows_out": len(rows),
            "rows_needs_review": 0
        }
    }
    Path(args.batch_out).write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "batch": batch["batch_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
