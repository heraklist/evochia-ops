import argparse
import json
import re
import shutil
import unicodedata
from pathlib import Path


_GREEK_TO_LATIN = str.maketrans({
    "α": "a", "ά": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "έ": "e", "ζ": "z", "η": "i", "ή": "i",
    "θ": "th", "ι": "i", "ί": "i", "ϊ": "i", "ΐ": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "ό": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y", "ύ": "y", "ϋ": "y",
    "ΰ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o", "ώ": "o",
    "Α": "A", "Ά": "A", "Β": "V", "Γ": "G", "Δ": "D", "Ε": "E", "Έ": "E", "Ζ": "Z", "Η": "I", "Ή": "I",
    "Θ": "TH", "Ι": "I", "Ί": "I", "Ϊ": "I", "Κ": "K", "Λ": "L", "Μ": "M", "Ν": "N", "Ξ": "X", "Ο": "O",
    "Ό": "O", "Π": "P", "Ρ": "R", "Σ": "S", "Τ": "T", "Υ": "Y", "Ύ": "Y", "Ϋ": "Y", "Φ": "F", "Χ": "CH",
    "Ψ": "PS", "Ω": "O", "Ώ": "O",
})


def slugify(text: str) -> str:
    s0 = str(text or "").translate(_GREEK_TO_LATIN)
    s = unicodedata.normalize("NFKD", s0).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown-client"


def service_tag(v: str) -> str:
    x = str(v or "").strip().lower()
    if x == "delivery":
        return "DEL"
    if x == "private_chef":
        return "PC"
    if x == "catering":
        return "CAT"
    return "CAT"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suf = path.stem, path.suffix
    n = 2
    while True:
        p = path.with_name(f"{stem}_v{n}{suf}")
        if not p.exists():
            return p
        n += 1


def copy_if_exists(src: Path, dst_dir: Path):
    if not src.exists():
        return None
    dst = unique_path(dst_dir / src.name)
    shutil.copy2(src, dst)
    return str(dst)


def _extract_version(name: str):
    m = re.search(r"_v(\d+)(\.[^.]+)$", name)
    if m:
        return f"v{int(m.group(1))}"
    return "v1"


def main():
    p = argparse.ArgumentParser(description="Deterministic proposal filing")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--template-type", required=True)
    p.add_argument("--proposal-request", required=True)
    p.add_argument("--proposals-root", required=True)
    p.add_argument("--client", required=False, default=None)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    req = json.loads(Path(args.proposal_request).read_text(encoding="utf-8"))
    payload = {}
    payload_path = run_dir / "proposal_payload.json"
    if payload_path.exists():
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    # deterministic fallback chain (as requested)
    client_name = (
        req.get("client", {}).get("name")
        or payload.get("client", {}).get("name")
        or args.client
        or "unknown-client"
    )
    client_slug = slugify(client_name)
    event_date = str(req.get("event", {}).get("date") or "unknown-date")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", event_date):
        event_date = "unknown-date"

    service_type = req.get("service_type") or req.get("event", {}).get("service_type")
    s_tag = service_tag(service_type)
    t_tag = str(args.template_type).upper()
    run_id = run_dir.parent.name

    ext = ".html" if t_tag == "C" else ".docx"
    base_filename = f"{event_date}_{client_slug}_{s_tag}_{t_tag}_{run_id}{ext}"

    year = event_date[:4] if event_date != "unknown-date" else "unknown"
    month = event_date[5:7] if event_date != "unknown-date" else "unknown"

    target_dir = Path(args.proposals_root) / year / month / client_slug / event_date
    target_dir.mkdir(parents=True, exist_ok=True)

    final_src = run_dir / ("final_output.html" if t_tag == "C" else "final_output.docx")
    final_dst = unique_path(target_dir / base_filename)
    copied = {}
    if final_src.exists():
        shutil.copy2(final_src, final_dst)
        copied["final_output"] = str(final_dst)

    for name in [
        "proposal_payload.json",
        "proposal_validation.json",
        "proposal_issues.json",
        "render_validation.json",
        "render_issues.json",
        "run_summary.txt",
        "decisions.json",
        "template_selection.json",
    ]:
        got = copy_if_exists(run_dir / name, target_dir)
        if got:
            copied[name] = got

    rv = {}
    if (run_dir / "render_validation.json").exists():
        rv = json.loads((run_dir / "render_validation.json").read_text(encoding="utf-8"))
    sel = {}
    if (run_dir / "template_selection.json").exists():
        sel = json.loads((run_dir / "template_selection.json").read_text(encoding="utf-8"))

    file_ver = _extract_version(final_dst.name) if final_src.exists() else "v1"

    manifest_path = target_dir / "manifest.json"
    manifest = {"entries": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {"entries": []}
    manifest.setdefault("entries", []).append({
        "filename": final_dst.name if final_src.exists() else None,
        "filed_artifacts": list(copied.values()),
        "source_run_path": str(run_dir),
        "compliance_status": rv.get("compliance_status"),
        "template_selection": {"rule_fired": sel.get("rule_fired")},
        "filing_version": file_ver,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    out = {
        "filed": True,
        "target_dir": str(target_dir),
        "filename": final_dst.name if final_src.exists() else None,
        "filing_version": file_ver,
        "copied": copied,
        "manifest": str(manifest_path),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
