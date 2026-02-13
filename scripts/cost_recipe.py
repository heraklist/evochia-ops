import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path


BASE_UNITS = {"kg", "lt", "pcs"}
SUPPORTED_INPUT_UNITS = {"g", "kg", "ml", "lt", "pcs"}


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def age_days(from_dt, to_dt):
    return max(0.0, (to_dt - from_dt).total_seconds() / 86400.0)


def unit_family(u):
    u = (u or "").lower()
    if u in {"g", "kg"}:
        return "weight"
    if u in {"ml", "lt"}:
        return "volume"
    if u == "pcs":
        return "count"
    return "unknown"


def to_base(qty, from_unit, base_unit):
    from_unit = (from_unit or "").lower()
    base_unit = (base_unit or "").lower()

    if from_unit == base_unit:
        return float(qty)

    if from_unit == "g" and base_unit == "kg":
        return float(qty) / 1000.0
    if from_unit == "kg" and base_unit == "kg":
        return float(qty)

    if from_unit == "ml" and base_unit == "lt":
        return float(qty) / 1000.0
    if from_unit == "lt" and base_unit == "lt":
        return float(qty)

    if from_unit == "pcs" and base_unit == "pcs":
        return float(qty)

    raise ValueError(f"Unsupported conversion: {from_unit} -> {base_unit}")


def add_issue(issues, severity, code, message, **extra):
    item = {"severity": severity, "code": code, "message": message}
    item.update(extra)
    issues.append(item)


def has_block(issues):
    return any(i.get("severity") == "BLOCK" for i in issues)


def main():
    p = argparse.ArgumentParser(description="Phase-1 cost recipe using sourcing decisions as source of truth")
    p.add_argument("--recipe", required=True)
    p.add_argument("--offers", required=True, help="mapped offers json")
    p.add_argument("--decisions", required=True, help="sourcing decisions json")
    p.add_argument("--defaults", required=True)
    p.add_argument("--out", required=True, help="cost_breakdown json out")
    p.add_argument("--issues-out", required=True, help="issues json out")
    p.add_argument("--confirm-stale", action="store_true", help="explicit confirmation to allow 15-28 day prices")
    args = p.parse_args()

    recipe = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
    offers = json.loads(Path(args.offers).read_text(encoding="utf-8"))
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    defaults = json.loads(Path(args.defaults).read_text(encoding="utf-8"))

    validity = defaults.get("phase1_price_validity", {})
    max_age_days = int(validity.get("max_age_days", 14))
    block_after_days = int(validity.get("block_after_days", 28))

    issues = []

    portions = recipe.get("portions")
    if portions in (None, 0):
        add_issue(issues, "BLOCK", "COST-MISSING-PORTIONS", "Recipe is missing valid portions", recipe_id=recipe.get("recipe_id"))

    ingredients = recipe.get("ingredients") or []
    if not ingredients:
        add_issue(issues, "BLOCK", "COST-NO-INGREDIENTS", "Recipe has no ingredients", recipe_id=recipe.get("recipe_id"))

    offer_by_id = {o.get("offer_id"): o for o in offers}
    chosen_by_product = {
        d.get("product_id"): d.get("chosen_offer_id")
        for d in decisions
        if d.get("product_id") and d.get("chosen_offer_id")
    }

    now = datetime.now(timezone.utc)

    lines = []
    food_total = 0.0

    for idx, ing in enumerate(ingredients, start=1):
        line_id = ing.get("line_id") or f"L{idx}"
        product_id = ing.get("product_id")
        gross_qty = ing.get("gross_qty")
        unit = (ing.get("unit") or "").lower()
        yield_pct = float(ing.get("yield_pct", 100) or 100)
        waste_pct = float(ing.get("waste_pct", 0) or 0)

        if not product_id:
            add_issue(issues, "BLOCK", "COST-UNMAPPED-PRODUCT", "Ingredient product_id is null/unmapped", line_id=line_id)
            continue

        if gross_qty in (None, 0):
            add_issue(issues, "BLOCK", "COST-MISSING-GROSS-QTY", "Ingredient gross_qty missing/zero", line_id=line_id, product_id=product_id)
            continue

        if unit not in SUPPORTED_INPUT_UNITS:
            add_issue(issues, "BLOCK", "COST-UNSUPPORTED-UNIT", "Unsupported ingredient unit", line_id=line_id, unit=unit)
            continue

        chosen_offer_id = chosen_by_product.get(product_id)
        if not chosen_offer_id:
            add_issue(issues, "BLOCK", "COST-NO-SOURCING-DECISION", "No chosen_offer for product_id", line_id=line_id, product_id=product_id)
            continue

        offer = offer_by_id.get(chosen_offer_id)
        if not offer:
            add_issue(issues, "BLOCK", "COST-CHOSEN-OFFER-NOT-FOUND", "chosen_offer_id not found in offers", line_id=line_id, chosen_offer_id=chosen_offer_id)
            continue

        base_unit = (offer.get("pack_unit") or "").lower()
        if base_unit not in BASE_UNITS:
            add_issue(issues, "BLOCK", "COST-UNSUPPORTED-BASE-UNIT", "Offer pack/base unit unsupported", line_id=line_id, chosen_offer_id=chosen_offer_id, pack_unit=base_unit)
            continue

        if unit_family(unit) != unit_family(base_unit):
            add_issue(issues, "BLOCK", "COST-CONVERSION-MISMATCH", "Unsupported unit family conversion", line_id=line_id, from_unit=unit, to_unit=base_unit)
            continue

        captured_at = parse_dt(offer.get("captured_at"))
        if not captured_at:
            add_issue(issues, "BLOCK", "COST-MISSING-CAPTURED-AT", "Offer missing/invalid captured_at", line_id=line_id, chosen_offer_id=chosen_offer_id)
            continue

        age = age_days(captured_at, now)
        if age > block_after_days:
            add_issue(issues, "BLOCK", "COST-PRICE-TOO-OLD", "Chosen price age > 28 days", line_id=line_id, chosen_offer_id=chosen_offer_id, age_days=round(age, 2))
            continue

        if age > max_age_days:
            add_issue(issues, "WARNING", "COST-PRICE-STALE", "Chosen price age is 15-28 days; explicit confirmation required", line_id=line_id, chosen_offer_id=chosen_offer_id, age_days=round(age, 2))
            if not args.confirm_stale:
                add_issue(issues, "BLOCK", "COST-STALE-NOT-CONFIRMED", "Stale price used without explicit confirm", line_id=line_id, chosen_offer_id=chosen_offer_id)
                continue

        try:
            gross_base = to_base(float(gross_qty), unit, base_unit)
        except Exception as e:
            add_issue(issues, "BLOCK", "COST-CONVERSION-FAILED", str(e), line_id=line_id)
            continue

        if waste_pct >= 100:
            add_issue(issues, "BLOCK", "COST-INVALID-WASTE", "waste_pct must be < 100", line_id=line_id)
            continue

        net_base = gross_base * (yield_pct / 100.0)
        actual_needed = net_base / (1.0 - (waste_pct / 100.0))

        ppu = offer.get("price_per_base_unit")
        if ppu in (None, ""):
            add_issue(issues, "BLOCK", "COST-MISSING-PRICE-PER-UNIT", "Offer missing price_per_base_unit", line_id=line_id, chosen_offer_id=chosen_offer_id)
            continue

        ppu = float(ppu)
        line_cost = actual_needed * ppu

        pack_size = offer.get("pack_size")
        if pack_size in (None, 0):
            add_issue(issues, "BLOCK", "COST-MISSING-PACK-SIZE", "Offer missing pack_size", line_id=line_id, chosen_offer_id=chosen_offer_id)
            continue

        try:
            pack_qty_base = to_base(float(pack_size), base_unit, base_unit)
        except Exception as e:
            add_issue(issues, "BLOCK", "COST-PACK-CONVERSION-FAILED", str(e), line_id=line_id)
            continue

        packs = int(math.ceil(actual_needed / pack_qty_base)) if pack_qty_base > 0 else 0
        bought_qty = packs * pack_qty_base
        leftover_qty = max(0.0, bought_qty - actual_needed)

        flags = []
        if leftover_qty > (0.5 * pack_qty_base):
            flags.append("LEFTOVER_GT_50_PCT_PACK")

        anomaly_flags = offer.get("anomaly_flags") or []
        if anomaly_flags:
            add_issue(
                issues,
                "WARNING",
                "COST-ANOMALY-FLAG",
                "Offer has anomaly flags",
                line_id=line_id,
                chosen_offer_id=chosen_offer_id,
                anomaly_flags=anomaly_flags,
            )
            flags.extend([f"ANOMALY:{x}" for x in anomaly_flags])

        food_total += line_cost
        lines.append(
            {
                "line_id": line_id,
                "product_id": product_id,
                "chosen_offer_id": chosen_offer_id,
                "supplier": offer.get("supplier"),
                "supplier_sku": offer.get("supplier_sku"),
                "base_unit": base_unit,
                "gross_qty_input": gross_qty,
                "gross_qty_base": round(gross_base, 6),
                "yield_pct": yield_pct,
                "waste_pct": waste_pct,
                "actual_needed_base": round(actual_needed, 6),
                "price_per_base_unit": ppu,
                "line_cost": round(line_cost, 4),
                "packs_to_buy": packs,
                "pack_size": pack_size,
                "pack_unit": base_unit,
                "leftover_qty_base": round(leftover_qty, 6),
                "price_age_days": round(age, 2),
                "flags": flags,
            }
        )

    packaging_total = 0.0
    for item in recipe.get("packaging_items", []) or []:
        qty = float(item.get("qty", 0) or 0)
        unit_cost = float(item.get("unit_cost", 0) or 0)
        packaging_total += qty * unit_cost
    for item in recipe.get("packaging_event_items", []) or []:
        packaging_total += float(item.get("flat_cost", 0) or 0)

    guests = float(portions or 0)
    consumable_rate = float(recipe.get("consumable_rate_per_person", 0) or 0)
    packaging_total += guests * consumable_rate

    hourly_rate = float(defaults.get("costing", {}).get("hourly_rate", 16.0) or 16.0)
    prep_minutes = float(recipe.get("prep_minutes", 0) or 0)
    labor_total = (prep_minutes / 60.0) * hourly_rate

    total_cost = food_total + packaging_total + labor_total
    per_portion = (total_cost / float(portions)) if portions not in (None, 0) else 0.0

    result = {
        "recipe_id": recipe.get("recipe_id", "UNKNOWN"),
        "food_cost_total": round(food_total, 4),
        "packaging_cost_total": round(packaging_total, 4),
        "labor_cost_total": round(labor_total, 4),
        "total_cost": round(total_cost, 4),
        "per_portion": round(per_portion, 6),
        "lines": lines,
        "status": "BLOCKED" if has_block(issues) else "OK",
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    issues_path = Path(args.issues_out)
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    issues_path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"status": result["status"], "lines": len(lines), "issues": len(issues)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
