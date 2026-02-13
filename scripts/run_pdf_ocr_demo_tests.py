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


def main():
    out = ROOT / "runs" / "phase30-demo" / "pdf_ocr_demo"
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw_offers.json"
    batch = out / "import_batch.json"
    needs = out / "needs_review.json"
    issues = out / "issues.json"

    run([
        sys.executable,
        str(S / "import_pdf_ocr.py"),
        "--input",
        str(ROOT / "data" / "imports" / "pdf_fixtures" / "alios_pdf_price_list_fixture.json"),
        "--supplier-profile",
        str(ROOT / "suppliers" / "alios.json"),
        "--out",
        str(raw),
        "--batch-out",
        str(batch),
        "--needs-review",
        str(needs),
        "--issues-out",
        str(issues),
    ])

    rows = json.loads(raw.read_text(encoding="utf-8"))
    if len(rows) < 2:
        raise AssertionError("Expected PDF/OCR import rows >= 2")
    req = ["offer_id", "supplier", "supplier_sku", "product_name", "price", "currency", "captured_at", "valid_until"]
    for k in req:
        if k not in rows[0]:
            raise AssertionError(f"Missing RawOffer key: {k}")

    print("PDF_OCR_DEMO_PASS")


if __name__ == "__main__":
    main()
