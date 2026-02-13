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
    # PASS reply shortcut visible or json-only
    txt_pass = "\n".join([
        "2026-04-12 | 30 άτομα | DEL finger | 25€/άτομο | client: OpenPathPass",
        "Nigiri Salmon — 30 portions | op_pass_a 180g, op_pass_b 120g, op_pass_c 1g",
    ])
    aliases_path = ROOT / "mappings" / "catalog_aliases.json"
    aliases = {}
    if aliases_path.exists():
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
        if not isinstance(aliases, dict):
            aliases = {}
    aliases["op_pass_a"] = "PROD-POTATO-STD"
    aliases["op_pass_b"] = "PROD-POTATO-STD"
    aliases["op_pass_c"] = "PROD-POTATO-STD"
    aliases_path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")

    rp = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txt_pass,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    ttxt = (rp / "telegram_reply.txt").read_text(encoding="utf-8")
    tj = json.loads((rp / "telegram_reply.json").read_text(encoding="utf-8"))
    if ("Open: open-path --run" not in ttxt) and (not tj.get("open_shortcuts")):
        raise AssertionError("Expected open shortcut in pass reply txt or json")

    op = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "open-path",
        "--run", str(rp),
        "--target", "filed",
        "--copy-to-clipboard",
    ]))
    oj = json.loads((op / "open_path.json").read_text(encoding="utf-8"))
    if oj.get("status") != "PASS":
        raise AssertionError("open-path filed should PASS")
    if oj.get("clipboard") != "copied":
        raise AssertionError("open-path clipboard should be copied on PASS with flag")

    # BLOCKED recipe-review should include patch_csv shortcut
    txt_block = "\n".join([
        "2026-04-13 | 30 άτομα | DEL finger | 25€/άτομο | client: OpenPathBlock",
        "Nigiri Salmon — 30 portions | op_blk_x 180g, op_blk_y 120g, op_blk_z 1 pcs",
    ])
    rb = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "menu-offer",
        "--text", txt_block,
        "--raw", str(ROOT / "data" / "prices" / "sample_offers.json"),
        "--no-reply",
    ]))
    btxt = (rb / "telegram_reply.txt").read_text(encoding="utf-8")
    bj = json.loads((rb / "telegram_reply.json").read_text(encoding="utf-8"))
    if ("--target patch_csv" not in btxt) and (not any("patch_csv" in x for x in bj.get("open_shortcuts", []))):
        raise AssertionError("Expected patch_csv shortcut on blocked recipe-review")

    op2 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "open-path",
        "--run", str(rb),
        "--target", "patch_csv",
    ]))
    oj2 = json.loads((op2 / "open_path.json").read_text(encoding="utf-8"))
    if oj2.get("status") != "PASS":
        raise AssertionError("open-path patch_csv should PASS")

    # BLOCK not found target + clipboard not attempted
    op3 = Path(run([
        sys.executable, str(S / "run_pipeline.py"), "open-path",
        "--run", str(rb),
        "--target", "manifest",
        "--copy-to-clipboard",
    ]))
    oj3 = json.loads((op3 / "open_path.json").read_text(encoding="utf-8"))
    if oj3.get("code") != "OPENPATH-TARGET-NOT-FOUND":
        raise AssertionError("open-path expected OPENPATH-TARGET-NOT-FOUND")
    if oj3.get("clipboard") != "not_attempted":
        raise AssertionError("clipboard should be not_attempted on BLOCK")

    print("OPEN_PATH_DEMO_PASS")


if __name__ == "__main__":
    main()
