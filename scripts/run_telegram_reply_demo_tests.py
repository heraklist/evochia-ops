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


def latest_intake():
    runs = sorted((ROOT / "runs").glob("*/intake"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise RuntimeError("No intake runs found")
    return runs[0]


def assert_lines(path):
    lines = [x for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    if not (1 <= len(lines) <= 6):
        raise AssertionError(f"Expected 1-6 lines in {path}, got {len(lines)}")


def main():
    raw = str(ROOT / "runs" / "20260212-0733" / "prices" / "raw_merged.json")
    recipe = str(ROOT / "data" / "recipes" / "policy_cases_recipe.json")

    # BLOCKED
    run([sys.executable, str(S / "run_pipeline.py"), "intake", "--text", "guests 55 DEL finger budget 90 per person", "--reply"])
    b = latest_intake()
    s = load(b / "intake_summary.json")
    if s.get("status") != "BLOCKED":
        raise AssertionError("Expected BLOCKED intake")
    assert_lines(b / "telegram_reply.txt")

    # PASS intake only
    run([sys.executable, str(S / "run_pipeline.py"), "intake", "--text", "2026-04-20 guests 45 CAT buffet budget 110 per person location: Kifisia", "--reply"])
    p = latest_intake()
    s2 = load(p / "intake_summary.json")
    if s2.get("status") != "PASS":
        raise AssertionError("Expected PASS intake")
    assert_lines(p / "telegram_reply.txt")

    # PASS offer+file
    run([
        sys.executable, str(S / "run_pipeline.py"), "intake",
        "--text", "2026-04-22 guests 50 DEL finger budget 95 per person location: Piraeus",
        "--run-offer", "--file-proposal", "--raw", raw, "--recipe", recipe, "--reply",
    ])
    f = latest_intake()
    assert_lines(f / "telegram_reply.txt")
    rj = load(f / "telegram_reply.json")
    if rj.get("mode") not in {"pass_offer_filed", "pass_intake_only", "blocked"}:
        raise AssertionError("Invalid telegram reply mode")

    print("TELEGRAM_REPLY_DEMO_PASS")


if __name__ == "__main__":
    main()
