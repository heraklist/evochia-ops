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
    # source-health detects missing path -> BROKEN
    sh = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "source-health",
        "--sources", "missingx:csv:C:/missing/file.csv",
        "--no-reply",
    ]))
    broken = json.loads((sh / "broken_sources.json").read_text(encoding="utf-8"))
    if not broken or broken[0].get("code") not in {"HEALTH-PATH-NOT-FOUND", "DAILY-SOURCE-NOT-FOUND"}:
        raise AssertionError("Expected BROKEN missing path in source-health")

    # daily-refresh blocks on preflight broken
    drb = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "daily-refresh",
        "--sources", "missingx:csv:C:/missing/file.csv",
        "--no-reply",
    ]))
    dsum = json.loads((drb / "daily_refresh_summary.json").read_text(encoding="utf-8"))
    if dsum.get("status") != "BLOCKED":
        raise AssertionError("daily-refresh should BLOCK on preflight broken")

    # successful daily-refresh updates source_status
    dr_ok = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "daily-refresh",
        "--sources", "themart",
        "--no-reply",
    ]))
    ss = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "source-status",
        "--no-reply",
    ]))
    rows = json.loads((ss / "source_status.json").read_text(encoding="utf-8"))
    themart = [r for r in rows if r.get("key") == "themart"]
    if not themart:
        raise AssertionError("source-status should include themart")
    if not themart[0].get("last_seen_ts"):
        raise AssertionError("source-status should have last_seen_ts")

    # alias outputs exact one-liners
    a_daily = run([sys.executable, str(S / "run_pipeline.py"), "alias", "--name", "daily"]).strip()
    a_health = run([sys.executable, str(S / "run_pipeline.py"), "alias", "--name", "health"]).strip()
    a_status = run([sys.executable, str(S / "run_pipeline.py"), "alias", "--name", "status"]).strip()
    if a_daily != "python skills/evochia-ops/scripts/run_pipeline.py daily-refresh --sources themart --sources alios --reply":
        raise AssertionError("alias daily mismatch")
    if a_health != "python skills/evochia-ops/scripts/run_pipeline.py source-health --reply":
        raise AssertionError("alias health mismatch")
    if a_status != "python skills/evochia-ops/scripts/run_pipeline.py source-status --only-broken --reply":
        raise AssertionError("alias status mismatch")

    print("SOURCE_HEALTH_STATUS_ALIAS_DEMO_PASS")


if __name__ == "__main__":
    main()
