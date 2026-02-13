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


def latest_recipe_dir():
    runs = sorted((ROOT / "runs").glob("*/recipe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise RuntimeError("No recipe runs")
    return runs[0]


def main():
    # Demo 1: BLOCK missing portions
    txt1 = "\n".join([
        'Menu:',
        '"Sushi Platter A"',
        '"Nigiri Salmon"',
    ])
    run([sys.executable, str(S / "run_pipeline.py"), "recipe-skeleton", "--text", txt1])
    d1 = latest_recipe_dir()
    s1 = json.loads((d1 / "recipe_summary.json").read_text(encoding="utf-8"))
    if s1.get("status") != "BLOCKED" or s1.get("code") != "RECIPE-MISSING-PORTIONS":
        raise AssertionError("Demo1 expected BLOCKED RECIPE-MISSING-PORTIONS")

    # Demo 2: PASS text no ingredients
    txt2 = "\n".join([
        'Menu:',
        '"Sushi Platter A — 30 portions"',
        '"Nigiri Salmon — 30 portions"',
        '"Edamame — 30 portions"',
    ])
    run([sys.executable, str(S / "run_pipeline.py"), "recipe-skeleton", "--text", txt2])
    d2 = latest_recipe_dir()
    s2 = json.loads((d2 / "recipe_summary.json").read_text(encoding="utf-8"))
    r2 = json.loads((d2 / "recipes_skeleton.json").read_text(encoding="utf-8"))
    if s2.get("status") != "PASS" or len(r2) != 3:
        raise AssertionError("Demo2 expected PASS with 3 recipes")
    if any(len(x.get("ingredients", [])) != 0 for x in r2):
        raise AssertionError("Demo2 expected empty ingredients arrays")

    # Demo 3: PASS explicit ingredients with product_id null
    txt3 = 'Nigiri Salmon — 30 portions | σολομός 180g, ρύζι sushi 120g, nori 1 pcs'
    run([sys.executable, str(S / "run_pipeline.py"), "recipe-skeleton", "--text", txt3])
    d3 = latest_recipe_dir()
    s3 = json.loads((d3 / "recipe_summary.json").read_text(encoding="utf-8"))
    r3 = json.loads((d3 / "recipes_skeleton.json").read_text(encoding="utf-8"))
    if s3.get("status") != "PASS" or len(r3) != 1:
        raise AssertionError("Demo3 expected PASS with 1 recipe")
    ings = r3[0].get("ingredients", [])
    if len(ings) != 3:
        raise AssertionError("Demo3 expected 3 ingredients")
    if any(i.get("product_id", "__MISSING__") is not None for i in ings):
        raise AssertionError("Demo3 expected product_id=null in ingredients")

    print("RECIPE_SKELETON_DEMO_PASS")


if __name__ == "__main__":
    main()
