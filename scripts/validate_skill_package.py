from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_MD = ROOT / "SKILL.md"


def fail(msg: str) -> None:
    print(f"FAIL {msg}")
    raise SystemExit(1)


def validate_frontmatter() -> dict[str, str]:
    if not SKILL_MD.exists():
        fail("SKILL.md missing")

    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        fail("SKILL.md frontmatter must start with '---' on line 1")

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        fail("SKILL.md frontmatter closing '---' not found")

    kv: dict[str, str] = {}
    for raw in lines[1:end_idx]:
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            fail(f"Invalid frontmatter line: {raw}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            fail(f"Empty frontmatter key in line: {raw}")
        kv[key] = value

    required = {"name", "description"}
    present = set(kv.keys())
    if present != required:
        fail(f"Frontmatter keys must be exactly {sorted(required)}; got {sorted(present)}")
    if not kv["name"] or not kv["description"]:
        fail("Frontmatter 'name' and 'description' must be non-empty")

    print(f"PASS frontmatter name={kv['name']}")
    return kv


def validate_json_files() -> tuple[int, int]:
    checked = 0
    errors = 0
    for path in sorted(ROOT.rglob("*.json")):
        # deterministic parser check equivalent to json.tool validation
        checked += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"FAIL json {path.relative_to(ROOT)} :: {exc}")

    if errors:
        fail(f"json validation failed files={errors}")

    print(f"PASS json files={checked}")
    return checked, errors


def main() -> None:
    fm = validate_frontmatter()
    checked, _ = validate_json_files()
    print(
        f"VALIDATOR_PASS skill={fm['name']} frontmatter_keys=2 json_files={checked}"
    )


if __name__ == "__main__":
    main()
