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
    sample_csv = "C:/Users/herax/Desktop/oporopoleio_unified.csv"

    # add-source PASS
    a1 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "add-source",
        "--key", "demo-src-52",
        "--type", "csv",
        "--path", sample_csv,
        "--display-name", "Demo Src 52",
        "--replace",
    ]))
    j1 = json.loads((a1 / "add_source_summary.json").read_text(encoding="utf-8"))
    if j1.get("status") != "PASS":
        raise AssertionError("add-source PASS expected")

    # add-source invalid key BLOCK
    a2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "add-source",
        "--key", "BAD KEY",
        "--type", "csv",
        "--path", sample_csv,
    ]))
    j2 = json.loads((a2 / "add_source_summary.json").read_text(encoding="utf-8"))
    if j2.get("code") != "ADD-SOURCE-INVALID-KEY":
        raise AssertionError("ADD-SOURCE-INVALID-KEY expected")

    # path-only without auto-register -> BLOCK not registered
    d1 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "daily-refresh",
        "--sources", "C:/Users/herax/Desktop/demo_autoreg_52.csv",
        "--no-reply",
    ]))
    s1 = json.loads((d1 / "daily_refresh_summary.json").read_text(encoding="utf-8"))
    codes1 = [x.get("code") for x in s1.get("blocked_sources", [])]
    if "DAILY-SOURCE-NOT-REGISTERED" not in codes1 and "DAILY-SOURCE-NOT-FOUND" not in codes1:
        raise AssertionError("Expected not registered or not found block")

    # auto-register path-only using existing path
    d2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "daily-refresh",
        "--sources", sample_csv,
        "--auto-register",
        "--no-reply",
    ]))
    s2 = json.loads((d2 / "daily_refresh_summary.json").read_text(encoding="utf-8"))
    if s2.get("status") not in {"PASS", "BLOCKED"}:
        raise AssertionError("Unexpected status in auto-register demo")

    # list-sources includes key
    ls = Path(run([sys.executable, str(S / "run_pipeline.py"), "list-sources"]))
    arr = json.loads((ls / "list_sources.json").read_text(encoding="utf-8"))
    if not any(x.get("key") == "demo-src-52" for x in arr):
        raise AssertionError("list-sources should include demo-src-52")

    # edit-source validations
    e1 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "edit-source",
        "--key", "demo-src-52",
        "--add-path", sample_csv,
    ]))
    je1 = json.loads((e1 / "edit_source_summary.json").read_text(encoding="utf-8"))
    if je1.get("status") != "PASS":
        raise AssertionError("edit-source add-path pass expected")

    e2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "edit-source",
        "--key", "demo-src-52",
        "--remove-path", "C:/missing/not-in-entry.csv",
    ]))
    je2 = json.loads((e2 / "edit_source_summary.json").read_text(encoding="utf-8"))
    if je2.get("code") != "EDIT-SOURCE-PATH-NOT-IN-ENTRY":
        raise AssertionError("EDIT-SOURCE-PATH-NOT-IN-ENTRY expected")

    # remove-source PASS + not-found BLOCK
    r1 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "remove-source",
        "--key", "demo-src-52",
    ]))
    jr1 = json.loads((r1 / "remove_source_summary.json").read_text(encoding="utf-8"))
    if jr1.get("status") != "PASS":
        raise AssertionError("remove-source pass expected")

    r2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "remove-source",
        "--key", "demo-src-52",
    ]))
    jr2 = json.loads((r2 / "remove_source_summary.json").read_text(encoding="utf-8"))
    if jr2.get("code") != "REMOVE-SOURCE-NOT-FOUND":
        raise AssertionError("REMOVE-SOURCE-NOT-FOUND expected")

    # web source PASS + invalid-url BLOCK
    w1 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "add-web-source",
        "--key", "web-demo-52",
        "--url", "https://example.com",
        "--replace",
    ]))
    jw1 = json.loads((w1 / "add_web_source_summary.json").read_text(encoding="utf-8"))
    if jw1.get("status") != "PASS":
        raise AssertionError("add-web-source pass expected")

    w2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "add-web-source",
        "--key", "web-demo-bad-52",
        "--url", "notaurl",
    ]))
    jw2 = json.loads((w2 / "add_web_source_summary.json").read_text(encoding="utf-8"))
    if jw2.get("code") != "WEB-SOURCE-INVALID-URL":
        raise AssertionError("WEB-SOURCE-INVALID-URL expected")

    print("SOURCE_REGISTRY_DEMO_PASS")


if __name__ == "__main__":
    main()
