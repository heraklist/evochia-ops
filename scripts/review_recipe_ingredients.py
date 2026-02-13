import argparse
import csv
import json
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


def parse_csv(path):
    rows = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def norm_alias(s):
    return " ".join(str(s or "").strip().lower().split())


def export_skeleton(needs, out_csv):
    fields = [
        "recipe_id", "line_id", "raw_ingredient", "qty", "unit",
        "suggestion_1", "suggestion_2", "suggestion_3",
        "set_product_id", "persist_mode", "reason",
    ]
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_csv).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for n in needs:
            w.writerow({
                "recipe_id": n.get("recipe_id"),
                "line_id": n.get("line_id"),
                "raw_ingredient": n.get("raw_ingredient", ""),
                "qty": n.get("gross_qty"),
                "unit": n.get("unit"),
                "suggestion_1": "",
                "suggestion_2": "",
                "suggestion_3": "",
                "set_product_id": "",
                "persist_mode": "",
                "reason": "",
            })


def main():
    p = argparse.ArgumentParser(description="Review recipe ingredient mappings deterministically")
    p.add_argument("--recipes", required=True)
    p.add_argument("--export-csv-skeleton", default=None)
    p.add_argument("--apply-csv", default=None)
    p.add_argument("--persist-mode", default="off", choices=["off", "catalog_alias"])
    p.add_argument("--catalog-aliases", default=str(ROOT / "mappings" / "catalog_aliases.json"))
    p.add_argument("--out-mapped", required=True)
    p.add_argument("--out-needs", required=True)
    p.add_argument("--out-issues", required=True)
    p.add_argument("--out-summary", required=True)
    args = p.parse_args()

    recipes = load_json(args.recipes, [])
    issues = []
    needs = []

    aliases = load_json(args.catalog_aliases, {})
    if not isinstance(aliases, dict):
        aliases = {}

    for r in recipes:
        rid = r.get("recipe_id")
        for ing in r.get("ingredients", []) or []:
            if ing.get("product_id") is None:
                akey = norm_alias(ing.get("raw_ingredient", ""))
                auto_pid = aliases.get(akey)
                if auto_pid:
                    ing["product_id"] = auto_pid
                    continue
                needs.append({
                    "recipe_id": rid,
                    "line_id": ing.get("line_id"),
                    "raw_ingredient": ing.get("raw_ingredient", ""),
                    "gross_qty": ing.get("gross_qty"),
                    "unit": ing.get("unit"),
                    "code": "RECIPE-INGREDIENT-UNMAPPED",
                    "action": "BLOCK_UNTIL_MAPPED",
                })

    export_path = args.export_csv_skeleton
    if export_path:
        export_skeleton(needs, export_path)

    if not isinstance(aliases, dict):
        aliases = {}

    if args.apply_csv:
        patch_rows = parse_csv(args.apply_csv)
        patch = {(x.get("recipe_id"), x.get("line_id")): x for x in patch_rows}

        for r in recipes:
            for ing in r.get("ingredients", []) or []:
                key = (r.get("recipe_id"), ing.get("line_id"))
                pr = patch.get(key)
                if not pr:
                    continue
                set_pid = (pr.get("set_product_id") or "").strip() or None
                if set_pid:
                    ing["product_id"] = set_pid

                pmode = (pr.get("persist_mode") or "").strip()
                if pmode == "catalog_alias":
                    if args.persist_mode != "catalog_alias":
                        continue
                    raw_ing = norm_alias(pr.get("raw_ingredient") or ing.get("raw_ingredient"))
                    if not raw_ing or not set_pid:
                        continue
                    existing = aliases.get(raw_ing)
                    if existing and existing != set_pid:
                        issues.append({
                            "severity": "BLOCK",
                            "code": "RECIPE-ALIAS-CONFLICT",
                            "message": "Alias already mapped to different product_id",
                            "raw_ingredient": raw_ing,
                            "existing_product_id": existing,
                            "new_product_id": set_pid,
                        })
                    else:
                        aliases[raw_ing] = set_pid

    # recompute needs after apply
    mapped_needs = []
    for r in recipes:
        for ing in r.get("ingredients", []) or []:
            if ing.get("product_id") is None:
                mapped_needs.append({
                    "recipe_id": r.get("recipe_id"),
                    "line_id": ing.get("line_id"),
                    "raw_ingredient": ing.get("raw_ingredient", ""),
                    "gross_qty": ing.get("gross_qty"),
                    "unit": ing.get("unit"),
                    "code": "RECIPE-INGREDIENT-UNMAPPED",
                    "action": "BLOCK_UNTIL_MAPPED",
                })

    status = "BLOCKED" if any(i.get("severity") == "BLOCK" for i in issues) or mapped_needs else "PASS"
    summary = {
        "status": status,
        "recipes": len(recipes),
        "needs_review_ingredients": len(mapped_needs),
        "issues": len(issues),
    }

    save_json(args.out_mapped, recipes)
    save_json(args.out_needs, mapped_needs)
    save_json(args.out_issues, issues)
    save_json(args.out_summary, summary)

    if args.persist_mode == "catalog_alias" and not any(i.get("severity") == "BLOCK" for i in issues):
        save_json(args.catalog_aliases, aliases)

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
