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
    # named defaults mode
    out = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "daily-refresh",
        "--sources", "themart",
        "--sources", "alios",
        "--no-reply",
    ]))
    sm = json.loads((out / "daily_refresh_summary.json").read_text(encoding="utf-8"))
    if len(sm.get("suppliers", [])) < 2:
        raise AssertionError("Expected TheMart+Alios in named-default daily refresh demo")
    if not (out / "telegram_macros.txt").exists():
        raise AssertionError("Expected telegram_macros.txt")

    # unknown named source -> clean BLOCK
    out2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "daily-refresh",
        "--sources", "unknown_supplier_key",
        "--no-reply",
    ]))
    sm2 = json.loads((out2 / "daily_refresh_summary.json").read_text(encoding="utf-8"))
    if sm2.get("status") != "BLOCKED":
        raise AssertionError("Expected BLOCKED on unknown named source")
    codes = [x.get("code") for x in sm2.get("blocked_sources", [])]
    if "DAILY-UNKNOWN-SOURCE" not in codes:
        raise AssertionError("Expected DAILY-UNKNOWN-SOURCE")

    print("DAILY_REFRESH_DEMO_PASS")


if __name__ == "__main__":
    main()
