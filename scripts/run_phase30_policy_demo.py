import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
OUT = ROOT / "runs" / "phase30-demo"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_decisions(rows, expect_lowest=False):
    required = ["policy_hits", "rule_applied", "reason_codes", "candidates_considered"]
    for row in rows:
        for k in required:
            if k not in row:
                raise AssertionError(f"missing {k} in decision {row.get('product_id')}")
        if expect_lowest and row.get("rule_applied") not in {"LOWEST", "LOCK"}:
            raise AssertionError(
                f"policies OFF expected LOWEST/LOCK, got {row.get('rule_applied')} for {row.get('product_id')}"
            )


def build_diff(dec_on, dec_off, category_by_pid):
    off_by_pid = {d["product_id"]: d for d in dec_off}
    rows = []
    changed = 0
    for on in dec_on:
        pid = on["product_id"]
        off = off_by_pid.get(pid)
        if not off:
            continue
        changed_supplier = on.get("selected_supplier") != off.get("selected_supplier")
        changed_rule = on.get("rule_applied") != off.get("rule_applied")
        if changed_supplier or changed_rule:
            changed += 1
        rows.append({
            "product_id": pid,
            "category": category_by_pid.get(pid),
            "on_supplier": on.get("selected_supplier"),
            "off_supplier": off.get("selected_supplier"),
            "on_rule": on.get("rule_applied"),
            "off_rule": off.get("rule_applied"),
            "changed": bool(changed_supplier or changed_rule),
        })
    return {"total": len(rows), "changed": changed, "rows": rows}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    offers = ROOT / "data" / "prices" / "phase30_policy_demo_basket.json"
    overrides = ROOT / "config" / "overrides.json"
    defaults = ROOT / "config" / "defaults.json"
    policies = ROOT / "policies" / "sourcing_policies.json"

    on_decisions = OUT / "decisions_policy_on.json"
    on_issues = OUT / "issues_policy_on.json"
    off_decisions = OUT / "decisions_policy_off.json"
    off_issues = OUT / "issues_policy_off.json"
    diff_out = OUT / "diff_report.json"

    run([
        sys.executable,
        str(S / "optimize_sourcing.py"),
        "--offers", str(offers),
        "--overrides", str(overrides),
        "--defaults", str(defaults),
        "--out", str(on_decisions),
        "--issues-out", str(on_issues),
        "--phase", "2",
        "--enable-phase2-rules",
        "--policies", str(policies),
        "--service-tag", "CAT",
    ])

    run([
        sys.executable,
        str(S / "optimize_sourcing.py"),
        "--offers", str(offers),
        "--overrides", str(overrides),
        "--defaults", str(defaults),
        "--out", str(off_decisions),
        "--issues-out", str(off_issues),
        "--phase", "1",
        "--service-tag", "CAT",
    ])

    d_on = load(on_decisions)
    d_off = load(off_decisions)
    offers_rows = load(offers)
    category_by_pid = {}
    for r in offers_rows:
        category_by_pid.setdefault(r.get("product_id"), r.get("category"))

    validate_decisions(d_on, expect_lowest=False)
    validate_decisions(d_off, expect_lowest=True)

    diff = build_diff(d_on, d_off, category_by_pid)
    diff_out.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "run_type=phase30_policy_demo",
        f"offers_input={offers}",
        f"decisions_on={len(d_on)}",
        f"decisions_off={len(d_off)}",
        f"changed_vs_baseline={diff.get('changed', 0)}",
        f"diff_report={diff_out}",
    ]
    (OUT / "run_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("PHASE30_DEMO_PASS")


if __name__ == "__main__":
    main()
