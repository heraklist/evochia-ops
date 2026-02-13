import argparse
import json
import re
import unicodedata
from pathlib import Path


def _slug(s: str) -> str:
    n = unicodedata.normalize("NFKD", str(s or "").strip().lower())
    a = "".join(ch for ch in n if not unicodedata.combining(ch))
    a = re.sub(r"[^a-z0-9]+", "-", a)
    a = re.sub(r"-+", "-", a).strip("-")
    return a or "item"


def _to_num(v: str):
    return float(str(v).replace(",", "."))


def _parse_ingredient_token(tok: str):
    t = tok.strip()
    m = re.match(r"^(?P<name>.+?)\s+(?P<qty>\d+(?:[\.,]\d+)?)\s*(?P<unit>[A-Za-zΑ-Ωα-ω]+)$", t)
    if not m:
        return None
    return {
        "line_id": f"ING-{_slug(m.group('name'))}",
        "raw_ingredient": m.group("name").strip(),
        "product_id": None,
        "gross_qty": _to_num(m.group("qty")),
        "unit": m.group("unit").lower(),
    }


def _normalize_lines(text: str):
    lines = []
    for raw in str(text or "").splitlines():
        s = raw.strip().strip('"').strip("'")
        if not s:
            continue
        if s.lower().startswith("menu:"):
            s = s.split(":", 1)[1].strip()
            if not s:
                continue
        if s.startswith("-"):
            s = s[1:].strip()
        lines.append(s)
    return lines


def build_from_text(lines, autofill_portions=None):
    recipes = []
    for idx, line in enumerate(lines, start=1):
        parts = [x.strip() for x in line.split("|", 1)]
        left = parts[0]
        ing_part = parts[1] if len(parts) > 1 else ""

        m = re.match(r"^(?P<name>.+?)\s*[—-]\s*(?P<portions>\d+(?:[\.,]\d+)?)\s*portions\s*$", left, re.IGNORECASE)
        if not m:
            if autofill_portions is None:
                return {
                    "status": "BLOCKED",
                    "code": "RECIPE-MISSING-PORTIONS",
                    "next_question": f"Για το πιάτο '{left}', πόσα portions να βάλω;",
                    "recipes": [],
                }
            name = left
            portions = float(autofill_portions)
        else:
            name = m.group("name").strip()
            portions = _to_num(m.group("portions"))

        ingredients = []
        if ing_part:
            for j, token in enumerate([x.strip() for x in ing_part.split(",") if x.strip()], start=1):
                ing = _parse_ingredient_token(token)
                if not ing:
                    return {
                        "status": "BLOCKED",
                        "code": "RECIPE-INGREDIENT-FORMAT-INVALID",
                        "next_question": f"Για το '{name}', γράψε το υλικό '{token}' ως 'όνομα ποσότητα unit' (π.χ. σολομός 180g).",
                        "recipes": [],
                    }
                ing["line_id"] = f"ING-{j:03d}-{_slug(ing.get('raw_ingredient'))[:24]}"
                ingredients.append(ing)

        recipes.append({
            "recipe_id": f"RECIPE-{idx:03d}-{_slug(name)[:40]}",
            "name": name,
            "tier": "standard",
            "portions": portions,
            "ingredients": ingredients,
        })

    return {
        "status": "PASS",
        "code": "RECIPE-SKELETON-BUILT",
        "next_question": None,
        "recipes": recipes,
    }


def main():
    p = argparse.ArgumentParser(description="Build deterministic Recipe skeletons from text or items json")
    p.add_argument("--text", default=None)
    p.add_argument("--items-json", default=None)
    p.add_argument("--autofill-portions", type=float, default=None)
    p.add_argument("--out-recipes", required=True)
    p.add_argument("--out-summary", required=True)
    p.add_argument("--out-reply", required=True)
    args = p.parse_args()

    if bool(args.text) == bool(args.items_json):
        raise RuntimeError("recipe-skeleton requires exactly one of --text or --items-json")

    if args.items_json:
        items = json.loads(Path(args.items_json).read_text(encoding="utf-8"))
        lines = []
        for x in items:
            name = str(x.get("name", "")).strip()
            portions = x.get("portions", None)
            if portions is None and args.autofill_portions is None:
                summary = {
                    "status": "BLOCKED",
                    "code": "RECIPE-MISSING-PORTIONS",
                    "next_question": f"Για το πιάτο '{name}', πόσα portions να βάλω;",
                    "input_count": len(items),
                    "recipe_count": 0,
                }
                Path(args.out_recipes).write_text("[]\n", encoding="utf-8")
                Path(args.out_summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                Path(args.out_reply).write_text((summary["code"] + "\n" + summary["next_question"] + "\n"), encoding="utf-8")
                print(json.dumps(summary, ensure_ascii=False))
                return
            pval = portions if portions is not None else args.autofill_portions
            ing = x.get("ingredients", []) or []
            ing_txt = ", ".join([f"{i.get('name','')} {i.get('gross_qty','')} {i.get('unit','')}".strip() for i in ing if i])
            line = f"{name} - {pval} portions"
            if ing_txt:
                line += f" | {ing_txt}"
            lines.append(line)
    else:
        lines = _normalize_lines(args.text)

    result = build_from_text(lines, autofill_portions=args.autofill_portions)

    recipes = result.get("recipes", [])
    summary = {
        "status": result["status"],
        "code": result["code"],
        "next_question": result.get("next_question"),
        "input_count": len(lines),
        "recipe_count": len(recipes),
        "ingredient_lines": sum(len(r.get("ingredients", [])) for r in recipes),
    }

    Path(args.out_recipes).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_recipes).write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if summary["status"] != "PASS":
        reply = [summary["code"], summary["next_question"]]
    else:
        reply = [
            f"PASS: {summary['recipe_count']} skeleton recipes",
            f"ingredients lines: {summary['ingredient_lines']}",
        ]
        for r in recipes[:6]:
            reply.append(f"- {r.get('name')} | portions={r.get('portions')} | ingredients={len(r.get('ingredients', []))}")
    Path(args.out_reply).write_text("\n".join(reply[:8]) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
