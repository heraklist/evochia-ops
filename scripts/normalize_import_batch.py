import argparse
import json
from pathlib import Path


def base_unit(pack_unit: str):
    u = (pack_unit or "").strip().lower()
    if u in {"g", "kg"}:
        return "kg"
    if u in {"ml", "lt"}:
        return "lt"
    if u in {"pcs", "pc", "piece", "pieces"}:
        return "pcs"
    return None


def to_base_size(pack_size, pack_unit):
    u = (pack_unit or "").lower()
    s = float(pack_size or 1)
    if u == "g":
        return s / 1000.0
    if u == "ml":
        return s / 1000.0
    return s


def main():
    p = argparse.ArgumentParser(description="Normalize imported RawOffer[] -> PriceQuote[]")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--needs-review", required=False, default=None)
    p.add_argument("--issues-out", required=False, default=None)
    args = p.parse_args()

    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out_rows = []
    needs_review = []
    issues = []

    for r in rows:
        raw_unit = r.get("pack_unit", "")
        bu = base_unit(raw_unit)
        if bu is None:
            issues.append({
                "severity": "WARNING",
                "code": "IMPORT-UNSUPPORTED-UNIT",
                "message": "Unsupported unit from import; sent to needs_review",
                "offer_id": r.get("offer_id"),
                "supplier": r.get("supplier"),
                "raw_unit": raw_unit,
            })
            needs_review.append({
                "offer_id": r.get("offer_id"),
                "supplier": r.get("supplier"),
                "supplier_sku": r.get("supplier_sku", ""),
                "product_name": r.get("product_name", ""),
                "reason": "IMPORT-UNSUPPORTED-UNIT",
                "raw_unit": raw_unit,
                "action": "BLOCK_UNTIL_REVIEWED"
            })
            continue

        bsize = to_base_size(r.get("pack_size", 1), raw_unit)
        price = float(r.get("price", 0) or 0)
        ppu = price / bsize if bsize else 0
        out_rows.append({
            "offer_id": r.get("offer_id"),
            "product_id": r.get("product_id", None),
            "supplier": r.get("supplier"),
            "supplier_sku": r.get("supplier_sku", ""),
            "product_name": r.get("product_name", ""),
            "category": r.get("category", ""),
            "tier": r.get("tier", "standard"),
            "pack_size": float(r.get("pack_size", 1) or 1),
            "pack_unit": bu,
            "price": price,
            "price_per_base_unit": ppu,
            "currency": r.get("currency", "EUR"),
            "vat_rate": float(r.get("vat_rate", 0.13) or 0.13),
            "captured_at": r.get("captured_at"),
            "valid_until": r.get("valid_until"),
            "valid_from": None,
            "valid_to": None,
            "max_age_days": r.get("max_age_days", 14),
            "in_stock": bool(r.get("in_stock", True))
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.needs_review:
        Path(args.needs_review).parent.mkdir(parents=True, exist_ok=True)
        Path(args.needs_review).write_text(json.dumps(needs_review, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.issues_out:
        Path(args.issues_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.issues_out).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"rows": len(out_rows), "needs_review": len(needs_review), "issues": len(issues)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
