import argparse
import csv
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description="Normalize supplier price rows (v0 scaffold)")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    src = Path(args.input)
    out = Path(args.out)

    if src.suffix.lower() == ".json":
        rows = json.loads(src.read_text(encoding="utf-8"))
        if rows and isinstance(rows[0], dict):
            headers = list(rows[0].keys())
        else:
            headers = []
    else:
        with src.open("r", encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f)
            rows = list(r)
            headers = r.fieldnames or []

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    print(f"normalized_rows={len(rows)}")


if __name__ == "__main__":
    main()
