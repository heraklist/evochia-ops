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


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def latest_intake_run():
    runs = sorted((ROOT / "runs").glob("*/intake"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise RuntimeError("No intake run found")
    return runs[0]


def main():
    # 1) missing date -> BLOCK
    run([
        sys.executable, str(S / "run_pipeline.py"), "intake",
        "--text", "guests 60 delivery finger budget 80 per person location: Glyfada",
    ])
    r1 = latest_intake_run()
    s1 = load(r1 / "intake_summary.json")
    if s1.get("status") != "BLOCKED" or "event.event_date" not in s1.get("missing_required", []):
        raise AssertionError("Expected BLOCKED intake with missing event.event_date")

    # 2) fully specified A
    run([
        sys.executable, str(S / "run_pipeline.py"), "intake",
        "--text", "2026-04-10 guests 70 CAT buffet budget 120 per person location: Marousi theme: mediterranean",
    ])
    r2 = latest_intake_run()
    s2 = load(r2 / "intake_summary.json")
    if s2.get("status") != "PASS":
        raise AssertionError("Expected PASS intake for fully specified input")

    # 3) end-to-end A/B/C with run-offer+file-proposal
    raw = str(ROOT / "runs" / "20260212-0733" / "prices" / "raw_merged.json")
    recipe = str(ROOT / "data" / "recipes" / "policy_cases_recipe.json")
    texts = [
        "2026-04-11 guests 50 CAT buffet budget 100 per person location: Athens theme: greek",
        "2026-04-12 guests 40 DEL finger budget 95 per person location: Piraeus theme: finger-food",
        "2026-04-13 guests 35 CAT ombre budget 140 per person location: Vouliagmeni theme: ombre",
    ]
    for t in texts:
        run([
            sys.executable, str(S / "run_pipeline.py"), "intake",
            "--text", t,
            "--run-offer",
            "--file-proposal",
            "--raw", raw,
            "--recipe", recipe,
            "--policies", str(ROOT / "policies" / "sourcing_policies.json"),
        ])

    print("INTAKE_DEMO_PASS")


if __name__ == "__main__":
    main()
