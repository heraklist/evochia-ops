import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def age_days(from_dt, to_dt):
    return max(0.0, (to_dt - from_dt).total_seconds() / 86400.0)


def best_lowest(rows):
    return min(rows, key=lambda x: float(x.get("price_per_base_unit", 1e18) or 1e18))


def add_issue(issues, severity, code, message, **extra):
    row = {"severity": severity, "code": code, "message": message}
    row.update(extra)
    issues.append(row)


def selectors_match(rule, service_tag: str, tier: str):
    sel = rule.get("selectors") or {}
    s_ok = True
    t_ok = True
    if "service_type" in sel:
        allowed = sel.get("service_type")
        if not isinstance(allowed, list):
            allowed = [allowed]
        s_ok = str(service_tag or "").upper() in {str(x).upper() for x in allowed}
    if "tier" in sel:
        allowed_t = sel.get("tier")
        if not isinstance(allowed_t, list):
            allowed_t = [allowed_t]
        t_ok = str(tier or "").lower() in {str(x).lower() for x in allowed_t}
    return s_ok and t_ok


def main():
    p = argparse.ArgumentParser(description="Sourcing optimizer with Phase-1 safe defaults and Phase-2 BAN/PREFER toggle")
    p.add_argument("--offers", required=True)
    p.add_argument("--overrides", required=True)
    p.add_argument("--defaults", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--issues-out", required=True)
    p.add_argument("--phase", type=int, default=1)
    p.add_argument("--enable-phase2-rules", action="store_true")
    p.add_argument("--enable-production-overrides", action="store_true")
    p.add_argument("--rollout-categories", default="")
    p.add_argument("--policies", required=False, default=None)
    p.add_argument("--service-tag", required=False, default="CAT")
    args = p.parse_args()

    offers = json.loads(Path(args.offers).read_text(encoding="utf-8"))
    overrides = json.loads(Path(args.overrides).read_text(encoding="utf-8")).get("overrides", [])
    if args.policies:
        pobj = json.loads(Path(args.policies).read_text(encoding="utf-8"))
        overrides = pobj.get("policies", overrides)
    defaults = json.loads(Path(args.defaults).read_text(encoding="utf-8"))

    phase2_active = args.enable_phase2_rules or args.phase >= 2
    production_overrides_active = bool(args.enable_production_overrides)
    rollout_categories = {x.strip().lower() for x in str(args.rollout_categories or "").split(",") if x.strip()}

    vcfg = defaults.get("phase1_price_validity", {})
    max_age = int(vcfg.get("max_age_days", 14))
    block_after = int(vcfg.get("block_after_days", 28))

    locks = {}
    bans = []
    prefers = []

    for r in overrides:
        rule = (r.get("rule") or "").upper()
        if rule == "LOCK" and r.get("product_id") and r.get("supplier"):
            locks[r["product_id"]] = r
        elif rule == "BAN":
            bans.append(r)
        elif rule == "PREFER":
            prefers.append(r)

    now = datetime.now(timezone.utc)
    by_product = {}
    issues = []

    for off in offers:
        pid = off.get("product_id")
        if not pid:
            add_issue(issues, "BLOCK", "SRC-UNMAPPED", "Offer has no product_id (needs mapping)", offer_id=off.get("offer_id"))
            continue

        cap = parse_dt(off.get("captured_at"))
        vul = parse_dt(off.get("valid_until"))
        if not cap:
            add_issue(issues, "BLOCK", "SRC-NO-CAPTURED-AT", "Missing/invalid captured_at", offer_id=off.get("offer_id"))
            continue

        ad = age_days(cap, now)
        if ad > block_after:
            add_issue(issues, "BLOCK", "SRC-PRICE-TOO-OLD", f"Price older than {block_after} days", offer_id=off.get("offer_id"), product_id=pid, age_days=round(ad, 2))
            continue
        if ad > max_age:
            add_issue(issues, "WARNING", "SRC-PRICE-STALE", f"Price older than {max_age} days", offer_id=off.get("offer_id"), product_id=pid, age_days=round(ad, 2))
        if vul and now > vul:
            add_issue(issues, "WARNING", "SRC-VALID-UNTIL-PASSED", "valid_until has passed", offer_id=off.get("offer_id"), product_id=pid)

        by_product.setdefault(pid, []).append(off)

    decisions = []
    for pid, group in by_product.items():
        in_stock = [g for g in group if g.get("in_stock", True)]
        if not in_stock:
            add_issue(issues, "BLOCK", "SRC-NO-INSTOCK", "No in-stock offers", product_id=pid)
            continue

        candidates = in_stock[:]
        rule_applied = "LOWEST"
        override_ref = None
        reason_codes = []
        policy_hits = []
        tier = str(candidates[0].get("tier", "standard"))

        # LOCK always active
        lock_rule = locks.get(pid)
        if lock_rule and selectors_match(lock_rule, args.service_tag, tier):
            lock_supplier = lock_rule.get("supplier")
            lock_sku = lock_rule.get("supplier_sku")
            lock_matches = [g for g in candidates if g.get("supplier") == lock_supplier]
            if lock_sku:
                lock_matches = [g for g in lock_matches if str(g.get("supplier_sku", "")) == str(lock_sku)]
            if not lock_matches:
                add_issue(issues, "BLOCK", "SRC-LOCK-NOT-FOUND", f"LOCK supplier '{lock_supplier}' has no available offer", product_id=pid)
                continue
            chosen = best_lowest(lock_matches)
            rule_applied = "LOCK"
            override_ref = lock_rule
            policy_hits.append({"rule": "LOCK", "policy": lock_rule})
            reason_codes.append("LOCK_ENFORCED")
        else:
            if phase2_active:
                product_category = str(candidates[0].get("category", "") or "").lower()
                category_known = product_category not in {"", "unknown", "none", "null"}

                # when production overrides are enabled, rollout allowlist controls category-scoped rules
                category_in_rollout = (not production_overrides_active) or (product_category in rollout_categories)

                # BAN
                for b in bans:
                    if not selectors_match(b, args.service_tag, tier):
                        continue
                    scope = (b.get("scope") or "").lower()
                    match = str(b.get("match") or "").lower()
                    supplier = b.get("supplier") or b.get("supplier_id")
                    if production_overrides_active and scope == "category" and not category_in_rollout:
                        continue
                    before = len(candidates)
                    if scope == "category":
                        candidates = [c for c in candidates if not (c.get("supplier") == supplier and str(c.get("category", "")).lower() == match)]
                    elif scope == "product_id":
                        candidates = [c for c in candidates if not (c.get("supplier") == supplier and str(c.get("product_id")) == str(b.get("match")))]
                    elif scope == "supplier_id":
                        candidates = [c for c in candidates if str(c.get("supplier")) != str(match)]
                    if len(candidates) < before:
                        reason_codes.append("BAN_FILTERED")
                        policy_hits.append({"rule": "BAN", "policy": b})

                if not candidates:
                    add_issue(issues, "BLOCK", "SRC-ALL-BANNED", "All candidate offers filtered by BAN rules", product_id=pid)
                    continue

                # PREFER (soft)
                baseline = best_lowest(candidates)
                baseline_price = float(baseline.get("price_per_base_unit", 1e18) or 1e18)
                preferred_pick = None
                preferred_rule = None

                if not category_known:
                    reason_codes.append("CATEGORY_UNKNOWN_FALLBACK_LOWEST")
                else:
                    for pref in prefers:
                        if not selectors_match(pref, args.service_tag, tier):
                            continue
                        scope = (pref.get("scope") or "").lower()
                        match = str(pref.get("match") or "").lower()
                        supplier = pref.get("supplier") or pref.get("supplier_id")
                        max_premium_pct = float(pref.get("max_premium_pct", 0) or 0)

                        if production_overrides_active and scope == "category" and not category_in_rollout:
                            continue

                        pool = candidates
                        if scope == "category":
                            pool = [c for c in candidates if str(c.get("category", "")).lower() == match and c.get("supplier") == supplier]
                        elif scope == "product_id":
                            pool = [c for c in candidates if str(c.get("product_id")) == str(pref.get("match")) and c.get("supplier") == supplier]
                        elif scope == "supplier_id":
                            pool = [c for c in candidates if str(c.get("supplier")) == str(match)]

                        if not pool:
                            continue

                        cand = best_lowest(pool)
                        cand_price = float(cand.get("price_per_base_unit", 1e18) or 1e18)
                        if baseline_price <= 0:
                            continue
                        premium_pct = ((cand_price - baseline_price) / baseline_price) * 100
                        if premium_pct <= max_premium_pct:
                            preferred_pick = cand
                            preferred_rule = pref
                            break

                if preferred_pick is not None:
                    chosen = preferred_pick
                    rule_applied = "PREFER"
                    override_ref = preferred_rule
                    policy_hits.append({"rule": "PREFER", "policy": preferred_rule})
                    reason_codes.append("PREFER_APPLIED")
                else:
                    chosen = baseline
                    rule_applied = "LOWEST"
            else:
                chosen = best_lowest(candidates)

        cp = float(chosen.get("price_per_base_unit", 0) or 0)
        lowest = best_lowest(candidates)
        lowest_price = float(lowest.get("price_per_base_unit", 0) or 0)

        candidates_view = []
        alternatives = []
        for g in candidates:
            gp = float(g.get("price_per_base_unit", 0) or 0)
            entry = {
                "supplier": g.get("supplier"),
                "offer_id": g.get("offer_id"),
                "price_per_base_unit": gp,
                "captured_at": g.get("captured_at"),
                "price_unit": g.get("price_unit") or g.get("pack_unit"),
            }
            candidates_view.append(entry)
            if g.get("offer_id") != chosen.get("offer_id"):
                diff = None if cp == 0 else ((gp - cp) / cp) * 100
                alternatives.append({
                    **entry,
                    "diff_pct": None if diff is None else round(diff, 2),
                })

        decision_key = "supplier_sku" if str(chosen.get("supplier_sku", "")).strip() else "desc_pack_exact"
        if decision_key == "desc_pack_exact":
            reason_codes.append("NO_SKU_KEY")

        decisions.append({
            "product_id": pid,
            "chosen_offer_id": chosen.get("offer_id"),
            "selected_supplier": chosen.get("supplier"),
            "decision_key": decision_key,
            "rule_applied": rule_applied,
            "candidates": candidates_view,
            "candidates_considered": candidates_view[:5],
            "policy_hits": policy_hits,
            "alternatives": alternatives,
            "override_ref": override_ref,
            "reason_codes": reason_codes,
            "lowest_global_offer_id": lowest.get("offer_id"),
            "lowest_global_price_per_base_unit": lowest_price,
            "chosen_price_per_base_unit": cp,
            "savings_vs_lowest_global_per_base_unit": round(lowest_price - cp, 6),
            "decision_ts": datetime.now(timezone.utc).isoformat(),
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")

    issues_out = Path(args.issues_out)
    issues_out.parent.mkdir(parents=True, exist_ok=True)
    issues_out.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"decisions": len(decisions), "issues": len(issues), "phase2_active": phase2_active}, ensure_ascii=False))


if __name__ == "__main__":
    main()
