import csv
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
    # create blocked-at-recipe-review run
    txt = "\n".join([
        "2026-04-05 | 30 άτομα | DEL finger | 25€/άτομο | client: Resume Demo",
        "Nigiri Salmon — 30 portions | resume_ing_a 180g, resume_ing_b 120g, resume_ing_c 1g",
    ])
    mo = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txt,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    rs = (mo / "run_summary.txt").read_text(encoding="utf-8")
    if "status=BLOCKED" not in rs or "stage=recipe-review" not in rs:
        raise AssertionError("Expected blocked menu-offer at recipe-review")

    skel = mo / "recipe_review_patch_skeleton.csv"
    rows = []
    with skel.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["set_product_id"] = "PROD-POTATO-STD"
            r["persist_mode"] = ""
            r["reason"] = "resume_demo"
            rows.append(r)
    patch = ROOT / "data" / "imports" / "resume_recipe_review_apply_demo.csv"
    with patch.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # resume success
    r_ok = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "resume",
        "--menu-offer-run", str(mo),
        "--apply-recipe-review-csv", str(patch),
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
    ]))
    s_ok = (r_ok / "run_summary.txt").read_text(encoding="utf-8")
    if "status=PASS" not in s_ok:
        raise AssertionError("Expected resume PASS")
    offer_dir = None
    for ln in s_ok.splitlines():
        if ln.startswith("offer="):
            offer_dir = ln.split("=", 1)[1].strip()
    if not offer_dir:
        raise AssertionError("Missing offer pointer in resume")
    if "filing_status=FILED" not in (Path(offer_dir) / "run_summary.txt").read_text(encoding="utf-8"):
        raise AssertionError("Expected FILED after resume")

    # wrong stopped_at -> BLOCK
    mo2 = Path(run([sys.executable, str(S / "run_pipeline.py"), "menu-offer", "--text", "30 άτομα | DEL finger", "--no-reply"]))
    r_bad = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "resume",
        "--menu-offer-run", str(mo2),
        "--apply-recipe-review-csv", str(patch),
    ]))
    s_bad = (r_bad / "run_summary.txt").read_text(encoding="utf-8")
    if "status=BLOCKED" not in s_bad or "stage=intake" not in s_bad:
        raise AssertionError("Expected clean BLOCK for wrong stopped_at")

    print("RESUME_DEMO_PASS")


if __name__ == "__main__":
    main()
