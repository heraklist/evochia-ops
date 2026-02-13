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


def latest_search_dir():
    runs = sorted((ROOT / "runs").glob("*/search"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise RuntimeError("No search run found")
    return runs[0]


def assert_reply(path):
    lines = [x for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(lines) > 10:
        raise AssertionError("search_reply must be <=10 lines")


def main():
    # build index and search by client
    run([sys.executable, str(S / "run_pipeline.py"), "search-proposals", "--client", "policy-case", "--limit", "5", "--reindex"])
    s1 = latest_search_dir()
    assert_reply(s1 / "search_reply.txt")
    json.loads((s1 / "search_results.json").read_text(encoding="utf-8"))

    # date range
    run([sys.executable, str(S / "run_pipeline.py"), "search-proposals", "--date-from", "2026-03-01", "--date-to", "2026-03-31", "--limit", "5"])
    s2 = latest_search_dir()
    assert_reply(s2 / "search_reply.txt")

    # service + template
    run([sys.executable, str(S / "run_pipeline.py"), "search-proposals", "--service", "DEL", "--template", "B", "--limit", "5"])
    s3 = latest_search_dir()
    assert_reply(s3 / "search_reply.txt")

    print("PROPOSAL_SEARCH_DEMO_PASS")


if __name__ == "__main__":
    main()
