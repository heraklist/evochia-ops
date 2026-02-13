import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
F = ROOT / "data" / "imports" / "ocr_fixtures"
SUP = ROOT / "suppliers"
OUT = ROOT / "runs" / "supplier-fixture-tests"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def one_case(supplier, fixture, expect_rows_gt0, expect_needs_review_gt0, expect_code=None):
    out_dir = OUT / supplier / fixture.replace(".json", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "raw_offers.json"
    batch_json = out_dir / "batch.json"
    needs_json = out_dir / "needs_review.json"
    issues_json = out_dir / "issues.json"

    run([
        sys.executable,
        str(S / "import_ocr.py"),
        "--input",
        str(F / fixture),
        "--supplier-profile",
        str(SUP / f"{supplier}.json"),
        "--out",
        str(out_json),
        "--batch-out",
        str(batch_json),
        "--needs-review",
        str(needs_json),
        "--issues-out",
        str(issues_json),
    ])

    rows = load(out_json)
    needs = load(needs_json)
    issues = load(issues_json)

    assert_true((len(rows) > 0) == expect_rows_gt0, f"Unexpected rows count for {supplier}/{fixture}")
    assert_true((len(needs) > 0) == expect_needs_review_gt0, f"Unexpected needs_review for {supplier}/{fixture}")

    if expect_code:
        assert_true(any(i.get("code") == expect_code for i in issues), f"Expected issue code {expect_code} not found for {supplier}/{fixture}")

    # no silent conversions check
    if expect_needs_review_gt0:
        for n in needs:
            assert_true(n.get("action") == "BLOCK_UNTIL_REVIEWED", "needs_review action must be BLOCK_UNTIL_REVIEWED")


def main():
    # complete fixtures should parse with zero needs_review
    one_case("4fsa", "4fsa_v1_complete.json", True, False)
    one_case("pelagus", "pelagus_v1_complete.json", True, False)
    one_case("alios", "alios_v1_complete.json", True, False)

    # broken fixtures should be blocked to needs_review
    one_case("4fsa", "4fsa_v1_bad_unit.json", False, True, "IMPORT-UNSUPPORTED-UNIT")
    one_case("pelagus", "pelagus_v1_missing_field.json", False, True, "IMPORT-MISSING-CRITICAL-FIELD")
    one_case("alios", "alios_v1_layout_unknown.json", False, True, "SUPPLIER-LAYOUT-UNKNOWN")

    print("SUPPLIER_FIXTURE_TESTS_PASS")


if __name__ == "__main__":
    main()
