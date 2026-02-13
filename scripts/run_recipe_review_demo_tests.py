import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    return r.stdout.strip()


def main():
    aliases_path = ROOT / "mappings" / "catalog_aliases.json"
    aliases = {}
    if aliases_path.exists():
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
        if not isinstance(aliases, dict):
            aliases = {}
    for k in ["rr_ing_a", "rr_ing_b", "rr_ing_c"]:
        aliases.pop(k, None)
    aliases_path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")

    txt = 'Nigiri Salmon — 30 portions | rr_ing_a 180g, rr_ing_b 120g, rr_ing_c 1g'
    recipe_dir = Path(run([sys.executable, str(S / "run_pipeline.py"), "recipe-skeleton", "--text", txt]))
    recipes = recipe_dir / "recipes_skeleton.json"

    # Demo A: export + apply mapping
    csv_path = ROOT / "data" / "imports" / "recipe_review_filled_demo.csv"
    rr1 = Path(run([sys.executable, str(S / "run_pipeline.py"), "recipe-review", "--recipes", str(recipes), "--export-csv-skeleton", str(csv_path)]))
    needs1 = json.loads((rr1 / "needs_review_ingredients.json").read_text(encoding="utf-8"))
    if len(needs1) != 3:
        raise AssertionError("Expected 3 needs_review ingredients")

    sample_decisions = json.loads((ROOT / "data" / "prices" / "sample_decisions.json").read_text(encoding="utf-8"))
    sample_offers = {x.get("offer_id"): x for x in json.loads((ROOT / "data" / "prices" / "sample_offers_mapped.json").read_text(encoding="utf-8"))}
    pid_by_family = {"weight": None, "count": None}
    for d in sample_decisions:
        pid = d.get("product_id")
        off = sample_offers.get(d.get("chosen_offer_id"))
        if not pid or not off:
            continue
        u = str(off.get("pack_unit", "")).lower()
        if u in {"kg"} and pid_by_family["weight"] is None:
            pid_by_family["weight"] = pid
        if u in {"pcs"} and pid_by_family["count"] is None:
            pid_by_family["count"] = pid

    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            unit = str(r.get("unit", "")).lower()
            if unit == "pcs":
                r["set_product_id"] = pid_by_family["count"] or pid_by_family["weight"]
            else:
                r["set_product_id"] = pid_by_family["weight"] or pid_by_family["count"]
            r["persist_mode"] = ""
            r["reason"] = "demo_apply"
            rows.append(r)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    rr2 = Path(run([sys.executable, str(S / "run_pipeline.py"), "recipe-review", "--recipes", str(recipes), "--apply-csv", str(csv_path)]))
    mapped = json.loads((rr2 / "recipes_mapped.json").read_text(encoding="utf-8"))
    if any(i.get("product_id") is None for i in mapped[0].get("ingredients", [])):
        raise AssertionError("Expected mapped recipe ingredients")

    # Demo B: recipe-cost PASS
    rc = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "recipe-cost",
        "--recipes-mapped", str(rr2 / "recipes_mapped.json"),
        "--offers", str(ROOT / "data" / "prices" / "sample_offers_mapped.json"),
        "--decisions", str(ROOT / "data" / "prices" / "sample_decisions.json"),
    ]))
    sc = json.loads((rc / "recipe_cost_summary.json").read_text(encoding="utf-8"))
    if sc.get("status") != "PASS":
        raise AssertionError("Expected recipe-cost PASS")

    # Demo C: conflict persist -> BLOCK
    conflict_csv = ROOT / "data" / "imports" / "recipe_review_conflict_demo.csv"
    first = mapped[0]["ingredients"][0]

    def write_conflict_csv(pid):
        with conflict_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["recipe_id", "line_id", "raw_ingredient", "qty", "unit", "suggestion_1", "suggestion_2", "suggestion_3", "set_product_id", "persist_mode", "reason"])
            w.writeheader()
            w.writerow({
                "recipe_id": mapped[0]["recipe_id"],
                "line_id": first["line_id"],
                "raw_ingredient": first.get("raw_ingredient", "σολομός"),
                "qty": first.get("gross_qty"),
                "unit": first.get("unit"),
                "suggestion_1": "", "suggestion_2": "", "suggestion_3": "",
                "set_product_id": pid,
                "persist_mode": "catalog_alias",
                "reason": "conflict-demo",
            })

    write_conflict_csv("PROD-CONFLICT-A")
    run([sys.executable, str(S / "run_pipeline.py"), "recipe-review", "--recipes", str(recipes), "--apply-csv", str(conflict_csv), "--persist-mode", "catalog_alias"])
    write_conflict_csv("PROD-CONFLICT-B")
    rr3 = Path(run([sys.executable, str(S / "run_pipeline.py"), "recipe-review", "--recipes", str(recipes), "--apply-csv", str(conflict_csv), "--persist-mode", "catalog_alias"]))
    issues3 = json.loads((rr3 / "issues.json").read_text(encoding="utf-8"))
    if not any(i.get("code") == "RECIPE-ALIAS-CONFLICT" for i in issues3):
        raise AssertionError("Expected RECIPE-ALIAS-CONFLICT")

    print("RECIPE_REVIEW_DEMO_PASS")


if __name__ == "__main__":
    main()
