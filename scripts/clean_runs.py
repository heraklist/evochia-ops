from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete local run artifacts under skills/evochia-ops/runs")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted")
    args = parser.parse_args()

    if not RUNS_DIR.exists():
        print("RUNS_CLEAN_OK runs_missing")
        return

    removed = 0
    for child in sorted(RUNS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if args.dry_run:
            print(f"DRYRUN_DELETE {child}")
            removed += 1
            continue
        shutil.rmtree(child)
        print(f"DELETED {child}")
        removed += 1

    print(f"RUNS_CLEAN_OK removed_dirs={removed}")


if __name__ == "__main__":
    main()
