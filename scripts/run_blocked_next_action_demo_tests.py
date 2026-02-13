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
    # Case 1: intake BLOCK -> next action missing field
    o1 = Path(run([sys.executable, str(S / "run_pipeline.py"), "menu-offer", "--text", "30 άτομα | DEL finger", "--no-reply"]))
    t1 = (o1 / "telegram_reply.txt").read_text(encoding="utf-8")
    if "Next action:" not in t1 or "Reply with" not in t1:
        raise AssertionError("Case1 missing Next action line")

    # Case 2: recipe-review unresolved -> next action with csv + resume
    txt2 = "\n".join([
        "2026-04-08 | 30 άτομα | DEL finger | 25€/άτομο | client: NextAction2",
        "Nigiri Salmon — 30 portions | nx2_a 180g, nx2_b 120g, nx2_c 1 pcs",
    ])
    o2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txt2,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    t2 = (o2 / "telegram_reply.txt").read_text(encoding="utf-8")
    if "Next action:" not in t2 or "--menu-offer-run" not in t2 or "--apply-recipe-review-csv" not in t2:
        raise AssertionError("Case2 missing resume next action")

    # Case 3: recipe-cost BLOCK -> next action prices/decisions rerun
    aliases_path = ROOT / "mappings" / "catalog_aliases.json"
    aliases = {}
    if aliases_path.exists():
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
        if not isinstance(aliases, dict):
            aliases = {}
    aliases["nx3_a"] = "PROD-POTATO-STD"
    aliases["nx3_b"] = "PROD-POTATO-STD"
    aliases["nx3_c"] = "PROD-POTATO-STD"
    aliases_path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")

    txt3 = "\n".join([
        "2026-04-09 | 30 άτομα | DEL finger | 25€/άτομο | client: NextAction3",
        "Nigiri Salmon — 30 portions | nx3_a 180g, nx3_b 120g, nx3_c 1 pcs",
    ])
    o3 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txt3,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    t3 = (o3 / "telegram_reply.txt").read_text(encoding="utf-8")
    if "Next action:" not in t3 or "prices import/offer decisions" not in t3:
        raise AssertionError("Case3 missing prices/decisions next action")

    # PASS reply unchanged (no Next action line)
    aliases["nx_pass_a"] = "PROD-POTATO-STD"
    aliases["nx_pass_b"] = "PROD-POTATO-STD"
    aliases["nx_pass_c"] = "PROD-POTATO-STD"
    aliases_path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")

    txtp = "\n".join([
        "2026-04-10 | 30 άτομα | DEL finger | 25€/άτομο | client: NextActionPass",
        "Nigiri Salmon — 30 portions | nx_pass_a 180g, nx_pass_b 120g, nx_pass_c 1g",
    ])
    op = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txtp,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    tp = (op / "telegram_reply.txt").read_text(encoding="utf-8")
    if "Next action:" in tp:
        raise AssertionError("PASS reply should not include Next action")

    print("BLOCKED_NEXT_ACTION_DEMO_PASS")


if __name__ == "__main__":
    main()
