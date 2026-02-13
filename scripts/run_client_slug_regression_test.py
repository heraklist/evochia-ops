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
    run_dir = ROOT / "runs" / "phase30-demo" / "client-slug-test" / "b"
    run_dir.mkdir(parents=True, exist_ok=True)

    proposal_request = run_dir / "proposal_request.json"
    proposal_request.write_text(json.dumps({
        "proposal_id": "PROP-SLUG-001",
        "client": {"name": "Νίκος"},
        "event": {"date": "2026-03-18", "service_type": "delivery"}
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # files expected by file_proposal copy logic
    (run_dir / "final_output.docx").write_bytes(b"demo")
    (run_dir / "proposal_payload.json").write_text(json.dumps({"client": {"name": "Νίκος"}}, ensure_ascii=False), encoding="utf-8")
    (run_dir / "proposal_validation.json").write_text("{}", encoding="utf-8")
    (run_dir / "proposal_issues.json").write_text("[]", encoding="utf-8")
    (run_dir / "render_validation.json").write_text(json.dumps({"compliance_status": "PASS"}), encoding="utf-8")
    (run_dir / "render_issues.json").write_text("[]", encoding="utf-8")
    (run_dir / "run_summary.txt").write_text("demo\n", encoding="utf-8")
    (run_dir / "decisions.json").write_text("[]", encoding="utf-8")
    (run_dir / "template_selection.json").write_text(json.dumps({"rule_fired": "RULE_B_DELIVERY_FINGER"}), encoding="utf-8")

    out = run_dir / "proposal_filing.json"
    run([
        sys.executable,
        str(S / "file_proposal.py"),
        "--run-dir", str(run_dir),
        "--template-type", "B",
        "--proposal-request", str(proposal_request),
        "--proposals-root", str(ROOT / "proposals"),
        "--out", str(out),
    ])

    filing = json.loads(out.read_text(encoding="utf-8"))
    target = str(filing.get("target_dir", "")).lower()
    if "\\nikos\\" not in target and "/nikos/" not in target:
        raise AssertionError(f"Expected filed target_dir to include nikos, got: {target}")

    print("CLIENT_SLUG_REGRESSION_PASS")


if __name__ == "__main__":
    main()
