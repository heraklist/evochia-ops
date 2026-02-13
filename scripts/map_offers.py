import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_iso(dt: str):
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


def load_supplier_sku_map(root: Path):
    mdir = root / "mappings" / "supplier_sku_map"
    merged = {}
    if not mdir.exists():
        return merged
    for f in mdir.glob("*.json"):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                merged.update(obj)
        except Exception:
            continue
    return merged


def canonical_category(v: str):
    s = norm(v)
    if s in {"produce", "λαχανικά", "οπωροπωλείο", "φρούτα", "vegetables", "fruit"}:
        return "produce"
    if s in {"seafood", "ψάρια", "ιχθυηρά", "fish", "fish/seafood"}:
        return "seafood"
    if s in {"frozen", "κατεψυγμένα", "frozen products"}:
        return "frozen"
    if s in {"dry", "παντοπωλείο", "ξηρά", "dry products"}:
        return "dry"
    if s in {"sauces", "σάλτσες"}:
        return "sauces"
    if s in {"condiments", "καρυκεύματα", "μπαχαρικά"}:
        return "condiments"
    return "unknown"


def main():
    p = argparse.ArgumentParser(description="Manual-first mapping RawOffer -> PriceQuote with needs_review queue")
    p.add_argument("--raw", required=True, help="raw offers json file")
    p.add_argument("--catalog", required=True, help="catalog json file")
    p.add_argument("--out", required=True, help="mapped quotes json file")
    p.add_argument("--needs-review", required=True, help="needs review queue json file")
    args = p.parse_args()

    raw_rows = load_json(Path(args.raw), [])
    catalog = load_json(Path(args.catalog), {"items": []})
    root = Path(__file__).resolve().parents[1]
    sku_map = load_supplier_sku_map(root)
    items = catalog.get("items", [])

    alias_index = {}
    item_by_pid = {}
    for item in items:
        pid = item.get("product_id")
        if pid:
            item_by_pid[pid] = item
        aliases = set(item.get("aliases", []) + [item.get("canonical_name", "")])
        for a in aliases:
            k = norm(a)
            if not k:
                continue
            alias_index.setdefault(k, []).append(pid)

    mapped = []
    needs_review = []

    for r in raw_rows:
        name = r.get("product_name", "")
        name_key = norm(name)
        candidate_pids = alias_index.get(name_key, [])

        product_id = None
        confidence = "low"

        supplier = r.get("supplier", "")
        supplier_sku = r.get("supplier_sku", "")
        sku_key = f"{supplier}::{supplier_sku}"

        if sku_key in sku_map:
            product_id = sku_map[sku_key]
            confidence = "high"
        elif len(candidate_pids) == 1:
            product_id = candidate_pids[0]
            confidence = "high"
        elif len(candidate_pids) > 1:
            confidence = "ambiguous"
        else:
            confidence = "unmapped"

        captured = parse_iso(r.get("captured_at", "")) or datetime.now(timezone.utc)
        valid_until = parse_iso(r.get("valid_until", ""))
        if valid_until is None:
            valid_until = captured + timedelta(days=14)

        item = item_by_pid.get(product_id) if product_id else None
        cat_raw = (item or {}).get("category", r.get("category", ""))
        cat_canonical = canonical_category(cat_raw)

        row = {
            "offer_id": r.get("offer_id"),
            "product_id": product_id,
            "supplier": r.get("supplier"),
            "supplier_sku": r.get("supplier_sku", ""),
            "product_name": name,
            "category": cat_canonical,
            "category_raw": r.get("category", ""),
            "tier": r.get("tier", "standard"),
            "pack_size": r.get("pack_size", 1),
            "pack_unit": r.get("pack_unit", ""),
            "price": r.get("price"),
            "price_per_base_unit": r.get("price_per_base_unit"),
            "currency": r.get("currency", "EUR"),
            "vat_rate": r.get("vat_rate", 0.13),
            "captured_at": captured.isoformat(),
            "valid_until": valid_until.isoformat(),
            "valid_from": r.get("valid_from"),
            "valid_to": r.get("valid_to"),
            "max_age_days": r.get("max_age_days", 14),
            "in_stock": bool(r.get("in_stock", True))
        }
        mapped.append(row)

        if confidence != "high":
            suggestions = candidate_pids[:3] if candidate_pids else []
            needs_review.append({
                "offer_id": r.get("offer_id"),
                "product_name": name,
                "supplier": r.get("supplier"),
                "supplier_sku": r.get("supplier_sku", ""),
                "reason": confidence,
                "suggestions": suggestions,
                "action": "BLOCK_UNTIL_MAPPED"
            })

    save_json(Path(args.out), mapped)
    save_json(Path(args.needs_review), needs_review)

    print(json.dumps({
        "total": len(mapped),
        "mapped_high": len(mapped) - len(needs_review),
        "needs_review": len(needs_review)
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
