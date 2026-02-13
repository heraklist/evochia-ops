import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe_load_json(path: Path):
    try:
        return load_json(path)
    except Exception:
        return None


def parse_filename(meta_name: str):
    # YYYY-MM-DD_client_service_template_runid.ext
    base = Path(meta_name).name
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_(.+)_(DEL|CAT|PC)_([ABC])_(\d{8}-\d{4})(?:_v\d+)?\.[^.]+$", base)
    if not m:
        return None
    return {
        "event_date": m.group(1),
        "client_slug": m.group(2),
        "service_tag": m.group(3),
        "template_tag": m.group(4),
        "run_id": m.group(5),
    }


def choose_payload(folder: Path):
    cands = sorted(folder.glob("proposal_payload*.json"))
    if not cands:
        return None
    if (folder / "proposal_payload.json").exists():
        return folder / "proposal_payload.json"
    return cands[0]


def extract_notes(payload: dict):
    notes = []
    menu = payload.get("menu", {}) if isinstance(payload, dict) else {}
    terms = payload.get("terms", {}) if isinstance(payload, dict) else {}
    theme = menu.get("theme")
    if theme:
        notes.append(f"theme:{theme}")
    excludes = menu.get("excludes_list") or terms.get("excludes_list") or []
    if isinstance(excludes, list) and excludes:
        notes.append("excludes:" + ",".join([str(x) for x in excludes]))
    elif isinstance(excludes, str) and excludes.strip():
        notes.append("excludes:" + excludes.strip())
    return " | ".join(notes)


def load_existing_jsonl(path: Path):
    out = {}
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
            out[row.get("entry_id")] = row
        except Exception:
            continue
    return out


def main():
    p = argparse.ArgumentParser(description="Build/update proposal library index from manifests")
    p.add_argument("--proposals-root", default="skills/evochia-ops/proposals")
    p.add_argument("--index-dir", default="skills/evochia-ops/proposals/index")
    p.add_argument("--out-jsonl", default=None)
    p.add_argument("--out-json", default=None)
    args = p.parse_args()

    proposals_root = Path(args.proposals_root)
    index_dir = Path(args.index_dir)
    out_jsonl = Path(args.out_jsonl) if args.out_jsonl else (index_dir / "proposals_index.jsonl")
    out_json = Path(args.out_json) if args.out_json else (index_dir / "proposals_index.json")

    manifests = sorted(proposals_root.glob("**/manifest.json"))
    existing = load_existing_jsonl(out_jsonl)
    issues = []
    now = datetime.now(timezone.utc).isoformat()

    discovered = {}

    for mp in manifests:
        mobj = safe_load_json(mp)
        if not isinstance(mobj, dict) or not isinstance(mobj.get("entries"), list):
            issues.append({
                "code": "INDEX-MANIFEST-INVALID",
                "message": "Manifest invalid or unreadable; skipped",
                "manifest_path": str(mp),
            })
            continue

        folder = mp.parent
        payload = safe_load_json(choose_payload(folder)) if choose_payload(folder) else {}
        client_display = (payload or {}).get("client", {}).get("name")
        pricing = (payload or {}).get("pricing", {})
        price_per_person = pricing.get("price_per_person")
        gross_total = pricing.get("gross_total")
        key_notes = extract_notes(payload or {})

        for i, e in enumerate(mobj.get("entries", []), start=1):
            fname = e.get("filename")
            parsed = parse_filename(fname or "") if fname else None
            filed_abs = None
            filed_rel = None

            fa = e.get("filed_artifacts") or []
            if isinstance(fa, list) and len(fa) > 0:
                # prefer final output artifact
                candidates = [x for x in fa if isinstance(x, str) and (x.endswith(".docx") or x.endswith(".html"))]
                if candidates:
                    filed_abs = candidates[0]
                elif isinstance(fa[0], str):
                    filed_abs = fa[0]
            if filed_abs:
                try:
                    filed_rel = str(Path(filed_abs).resolve().relative_to(Path.cwd().resolve()))
                except Exception:
                    filed_rel = None

            if parsed is None:
                # fallback from path pieces: /YYYY/MM/client_slug/event_date/
                parts = folder.parts
                parsed = {
                    "event_date": folder.name,
                    "client_slug": parts[-2] if len(parts) >= 2 else "unknown-client",
                    "service_tag": None,
                    "template_tag": None,
                    "run_id": None,
                }

            entry_id = f"{mp}:{i}:{fname}"
            row = {
                "entry_id": entry_id,
                "client_slug": parsed.get("client_slug"),
                "client_display": client_display,
                "event_date": parsed.get("event_date"),
                "service_tag": parsed.get("service_tag"),
                "template_tag": parsed.get("template_tag"),
                "run_id": parsed.get("run_id"),
                "compliance_status": e.get("compliance_status"),
                "filed_path_abs": filed_abs,
                "filed_path_rel": filed_rel,
                "manifest_path": str(mp),
                "created_at": now,
                "policy_preset": None,
                "key_notes": key_notes,
                "price_per_person_gross": price_per_person,
                "gross_total": gross_total,
            }
            discovered[entry_id] = row

    merged = dict(existing)
    merged.update(discovered)

    rows = sorted(merged.values(), key=lambda x: (str(x.get("event_date") or ""), str(x.get("client_slug") or ""), str(x.get("run_id") or "")), reverse=True)

    index_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl.write_text("\n".join([json.dumps(r, ensure_ascii=False) for r in rows]) + ("\n" if rows else ""), encoding="utf-8")
    out_json.write_text(json.dumps({"rows": rows, "issues": issues}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"entries": len(rows), "issues": len(issues), "jsonl": str(out_jsonl), "json": str(out_json)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
