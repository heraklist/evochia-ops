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
    # Demo 1: BLOCK at intake (missing date)
    txt1 = "30 άτομα | DEL finger | 25€/άτομο"
    o1 = Path(run([sys.executable, str(S / "run_pipeline.py"), "menu-offer", "--text", txt1, "--no-reply"]))
    s1 = (o1 / "run_summary.txt").read_text(encoding="utf-8")
    if "status=BLOCKED" not in s1 or "stage=intake" not in s1:
        raise AssertionError("Demo1 expected BLOCK at intake")

    # Demo 2: BLOCK at recipe-review + skeleton csv
    txt2 = "\n".join([
        "2026-03-30 | 30 άτομα | DEL finger | 25€/άτομο | client: Demo Two",
        "Nigiri Salmon — 30 portions | demo_ing_a 180g, demo_ing_b 120g, demo_ing_c 1 pcs",
    ])
    o2 = Path(run([sys.executable, str(S / "run_pipeline.py"), "menu-offer", "--text", txt2, "--no-reply"]))
    s2 = (o2 / "run_summary.txt").read_text(encoding="utf-8")
    if "status=BLOCKED" not in s2 or "stage=recipe-review" not in s2:
        raise AssertionError("Demo2 expected BLOCK at recipe-review")
    if not (o2 / "recipe_review_patch_skeleton.csv").exists():
        raise AssertionError("Demo2 expected skeleton csv")

    # Seed aliases for Demo3 pass path
    aliases_path = ROOT / "mappings" / "catalog_aliases.json"
    aliases = {}
    if aliases_path.exists():
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
        if not isinstance(aliases, dict):
            aliases = {}
    aliases["σολομός"] = "PROD-POTATO-STD"
    aliases["ρύζι sushi"] = "PROD-POTATO-STD"
    aliases["nori"] = "PROD-POTATO-STD"
    aliases_path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")

    # Demo 3: PASS end-to-end FILED + <=6 lines reply
    txt3 = "\n".join([
        "2026-04-02 | 30 άτομα | DEL finger | template:A | 25€/άτομο | client: Demo Three",
        "Nigiri Salmon — 30 portions | σολομός 180g, ρύζι sushi 120g, nori 1g",
    ])
    o3 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txt3,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    s3 = (o3 / "run_summary.txt").read_text(encoding="utf-8")
    if "status=PASS" not in s3:
        raise AssertionError("Demo3 expected PASS")
    offer_dir = None
    for ln in s3.splitlines():
        if ln.startswith("offer="):
            offer_dir = ln.split("=", 1)[1].strip()
    if not offer_dir:
        raise AssertionError("Demo3 missing offer pointer")
    offer_summary = Path(offer_dir) / "run_summary.txt"
    offer_summary_text = offer_summary.read_text(encoding="utf-8")
    if "filing_status=" not in offer_summary_text:
        raise AssertionError("Demo3 expected filing_status line in offer summary")

    reply_lines = (o3 / "telegram_reply.txt").read_text(encoding="utf-8").strip().splitlines()
    if len(reply_lines) > 6:
        raise AssertionError("Demo3 expected <=6 reply lines")

    print("MENU_OFFER_DEMO_PASS")


if __name__ == "__main__":
    main()
