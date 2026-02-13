import argparse
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


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser(description="Supplier onboarding fixture tests")
    p.add_argument("--supplier-id", required=True)
    p.add_argument("--profile", required=False, default=None)
    p.add_argument("--fixtures-root", required=False, default=None)
    args = p.parse_args()

    sid = args.supplier_id
    profile_path = Path(args.profile) if args.profile else (ROOT / "suppliers" / f"{sid}.json")
    fx_root = Path(args.fixtures_root) if args.fixtures_root else (ROOT / "data" / "imports" / "fixtures" / sid)

    if not profile_path.exists():
        raise AssertionError(f"Profile missing: {profile_path}")
    if not fx_root.exists():
        raise AssertionError(f"Fixtures root missing: {fx_root}")

    profile = load(profile_path)
    for key in ["supplier_id", "layout_version", "unit_map", "defaults"]:
        if key not in profile:
            raise AssertionError(f"Missing profile key: {key}")

    # pdf-ocr fixture tests if present
    pdf_ok = fx_root / "pdfocr_v1_complete.json"
    pdf_bad = fx_root / "pdfocr_v1_layout_unknown.json"
    if pdf_ok.exists() and pdf_bad.exists():
        out_ok = fx_root / "_tmp_pdf_ok_raw.json"
        out_ok_batch = fx_root / "_tmp_pdf_ok_batch.json"
        out_ok_needs = fx_root / "_tmp_pdf_ok_needs.json"
        out_ok_issues = fx_root / "_tmp_pdf_ok_issues.json"
        run([
            sys.executable,
            str(S / "import_pdf_ocr.py"),
            "--input", str(pdf_ok),
            "--supplier-profile", str(profile_path),
            "--out", str(out_ok),
            "--batch-out", str(out_ok_batch),
            "--needs-review", str(out_ok_needs),
            "--issues-out", str(out_ok_issues),
        ])
        rows_ok = load(out_ok)
        if len(rows_ok) == 0:
            raise AssertionError("Expected pdfocr complete rows > 0")

        out_bad = fx_root / "_tmp_pdf_bad_raw.json"
        out_bad_batch = fx_root / "_tmp_pdf_bad_batch.json"
        out_bad_needs = fx_root / "_tmp_pdf_bad_needs.json"
        out_bad_issues = fx_root / "_tmp_pdf_bad_issues.json"
        run([
            sys.executable,
            str(S / "import_pdf_ocr.py"),
            "--input", str(pdf_bad),
            "--supplier-profile", str(profile_path),
            "--out", str(out_bad),
            "--batch-out", str(out_bad_batch),
            "--needs-review", str(out_bad_needs),
            "--issues-out", str(out_bad_issues),
        ])
        issues_bad = load(out_bad_issues)
        if not any(i.get("code") == "SUPPLIER-LAYOUT-UNKNOWN" for i in issues_bad):
            raise AssertionError("Expected SUPPLIER-LAYOUT-UNKNOWN in bad layout fixture")

        for f in [out_ok, out_ok_batch, out_ok_needs, out_ok_issues, out_bad, out_bad_batch, out_bad_needs, out_bad_issues]:
            if f.exists():
                f.unlink()

    # xlsx fixture sanity tests (structured fixture)
    xlsx_ok = fx_root / "xlsx_v1_complete.json"
    xlsx_bad = fx_root / "xlsx_v1_broken_missing_price.json"
    if xlsx_ok.exists():
        j = load(xlsx_ok)
        rows = j.get("rows", [])
        if not rows or "net" not in rows[0]:
            raise AssertionError("Invalid xlsx_v1_complete fixture")
    if xlsx_bad.exists():
        j = load(xlsx_bad)
        rows = j.get("rows", [])
        if not rows or "net" in rows[0]:
            raise AssertionError("Invalid xlsx_v1_broken_missing_price fixture")

    print("ONBOARDING_FIXTURE_TESTS_PASS")


if __name__ == "__main__":
    main()
