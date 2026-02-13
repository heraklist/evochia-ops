import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
RUNS = ROOT / "runs"


def latest(path_glob):
    c = list(RUNS.glob(path_glob))
    if not c:
        return None
    return str(sorted(c, key=lambda p: p.stat().st_mtime, reverse=True)[0])


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    return r.stdout.strip()


def main():
    p = argparse.ArgumentParser(description="Cost mapped recipe list using latest or provided prices decisions")
    p.add_argument("--recipes-mapped", required=True)
    p.add_argument("--offers", default=None)
    p.add_argument("--decisions", default=None)
    p.add_argument("--defaults", default=str(ROOT / "config" / "defaults.json"))
    p.add_argument("--out-costs", required=True)
    p.add_argument("--out-issues", required=True)
    p.add_argument("--out-summary", required=True)
    p.add_argument("--confirm-stale", action="store_true")
    args = p.parse_args()

    offers = args.offers or latest("*/prices/offers_mapped.json")
    decisions = args.decisions or latest("*/prices/decisions.json")

    issues = []
    if not offers:
        issues.append({"severity": "BLOCK", "code": "COST-CHOSEN-OFFER-NOT-FOUND", "message": "offers_mapped.json not found"})
    if not decisions:
        issues.append({"severity": "BLOCK", "code": "COST-NO-SOURCING-DECISION", "message": "decisions.json not found"})

    recipes = load_json(args.recipes_mapped, [])
    if issues:
        save_json(args.out_costs, [])
        save_json(args.out_issues, issues)
        save_json(args.out_summary, {"status": "BLOCKED", "recipes": len(recipes), "costed": 0, "issues": len(issues)})
        print(json.dumps({"status": "BLOCKED", "issues": len(issues)}, ensure_ascii=False))
        return

    all_costs = []
    all_issues = []
    tmp = Path(args.out_costs).parent
    tmp.mkdir(parents=True, exist_ok=True)

    for i, recipe in enumerate(recipes, start=1):
        rp = tmp / f"_recipe_{i}.json"
        ro = tmp / f"_recipe_{i}_cost.json"
        ri = tmp / f"_recipe_{i}_issues.json"
        rp.write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
        run([
            sys.executable,
            str(SCRIPTS / "cost_recipe.py"),
            "--recipe", str(rp),
            "--offers", str(offers),
            "--decisions", str(decisions),
            "--defaults", str(args.defaults),
            "--out", str(ro),
            "--issues-out", str(ri),
        ] + (["--confirm-stale"] if args.confirm_stale else []))
        all_costs.append(load_json(ro, {}))
        all_issues.extend(load_json(ri, []))

    save_json(args.out_costs, all_costs)
    save_json(args.out_issues, all_issues)
    status = "BLOCKED" if any(i.get("severity") == "BLOCK" for i in all_issues) else "PASS"
    summary = {
        "status": status,
        "recipes": len(recipes),
        "costed": len(all_costs),
        "issues": len(all_issues),
        "offers": offers,
        "decisions": decisions,
    }
    save_json(args.out_summary, summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
