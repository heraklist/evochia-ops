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


def latest_dir(kind):
    runs = sorted((ROOT / "runs").glob(f"*/{kind}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise RuntimeError(f"No {kind} runs found")
    return runs[0]


def main():
    # run search demo context
    run([sys.executable, str(S / "run_pipeline.py"), "search-proposals", "--client", "policy", "--limit", "5", "--reindex"])
    search_dir = latest_dir("search")

    # n=1
    run([sys.executable, str(S / "run_pipeline.py"), "open-result", "--search-run", str(search_dir), "--n", "1"])
    o1 = latest_dir("open")
    j1 = json.loads((o1 / "open_result.json").read_text(encoding="utf-8"))
    if j1.get("status") != "PASS":
        raise AssertionError("Expected PASS for open-result n=1")

    # n=3
    run([sys.executable, str(S / "run_pipeline.py"), "open-result", "--search-run", str(search_dir), "--n", "3"])
    o3 = latest_dir("open")
    j3 = json.loads((o3 / "open_result.json").read_text(encoding="utf-8"))
    if j3.get("status") != "PASS":
        raise AssertionError("Expected PASS for open-result n=3")

    # out-of-range
    run([sys.executable, str(S / "run_pipeline.py"), "open-result", "--search-run", str(search_dir), "--n", "999"])
    oo = latest_dir("open")
    jo = json.loads((oo / "open_result.json").read_text(encoding="utf-8"))
    if jo.get("code") != "OPEN-N-OUT-OF-RANGE":
        raise AssertionError("Expected OPEN-N-OUT-OF-RANGE for out-of-range n")

    print("OPEN_RESULT_DEMO_PASS")


if __name__ == "__main__":
    main()
