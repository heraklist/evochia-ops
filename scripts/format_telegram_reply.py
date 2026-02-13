import argparse
import json
from pathlib import Path


def load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def first_missing_code(summary):
    miss = summary.get("missing_required", []) or []
    if not miss:
        return "INTAKE-BLOCKED"
    return f"INTAKE-MISSING-{str(miss[0]).replace('.', '-').upper()}"


def policy_preset_label(req):
    p = ((req or {}).get("policy", {}) or {}).get("policies_path", "")
    s = str(p).lower()
    if "conservative" in s:
        return "conservative"
    if "balanced" in s:
        return "balanced"
    if s.endswith("sourcing_policies.json"):
        return "balanced(default)"
    return "custom"


def to_rel(abs_path: str):
    try:
        cwd = Path.cwd().resolve()
        p = Path(abs_path).resolve()
        return str(p.relative_to(cwd))
    except Exception:
        return None


def parse_filed_path(offer_run_summary_path: str):
    p = Path(offer_run_summary_path)
    if not p.exists():
        return None, None
    lines = p.read_text(encoding="utf-8").splitlines()
    note = None
    for ln in lines:
        if ln.startswith("filing_note="):
            note = ln.split("=", 1)[1].strip()
            break
    if not note:
        return None, None
    note_path = Path(note)
    if not note_path.exists():
        return None, None
    filing = json.loads(note_path.read_text(encoding="utf-8"))
    abs_final = (filing.get("copied") or {}).get("final_output")
    if not abs_final:
        return None, None
    return abs_final, to_rel(abs_final)


def fmt_money(v):
    if v is None:
        return "n/a"
    try:
        return f"€{float(v):.2f}"
    except Exception:
        return "n/a"


def main():
    p = argparse.ArgumentParser(description="Compact Telegram reply formatter")
    p.add_argument("--intake-summary", required=True)
    p.add_argument("--template-selection", required=False, default=None)
    p.add_argument("--proposal-request", required=False, default=None)
    p.add_argument("--proposal-payload", required=False, default=None)
    p.add_argument("--offer-run-summary", required=False, default=None)
    p.add_argument("--out-txt", required=True)
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    summary = load_json(args.intake_summary) or {}
    template_sel = load_json(args.template_selection) or {}
    req = load_json(args.proposal_request) or {}
    payload = load_json(args.proposal_payload) if args.proposal_payload else None

    status = summary.get("status", "BLOCKED")
    lines = []
    out = {
        "status": status,
        "mode": None,
        "lines": [],
        "paths": {
            "intake_summary": str(Path(args.intake_summary).resolve()),
            "proposal_payload": str(Path(args.proposal_payload).resolve()) if args.proposal_payload else None,
            "offer_run_summary": str(Path(args.offer_run_summary).resolve()) if args.offer_run_summary else None,
        },
    }

    if status == "BLOCKED":
        code = first_missing_code(summary)
        q = summary.get("next_question") or "Χρειάζομαι τα required στοιχεία για να συνεχίσω."
        lines = [f"BLOCKED: {code}", q]
        out["mode"] = "blocked"
        out["reason_code"] = code
        out["next_question"] = q
    elif status == "PASS" and not payload:
        r = summary.get("resolved", {})
        budget = None
        if req:
            c = req.get("commercials", {})
            budget = c.get("budget_per_person") if c.get("budget_per_person") is not None else c.get("budget_total")
        constraints = (((req.get("menu", {}) if req else {}).get("excludes_list")) or [])
        line1 = f"PASS: {r.get('event_date')} | guests={r.get('guest_count')} | {r.get('service_type')}/{r.get('event_style')}"
        line2 = f"template={r.get('template_type')} | budget={budget if budget is not None else 'n/a'}"
        line3 = f"constraints={','.join(constraints) if constraints else 'none'}"
        lines = [line1, line2, line3]
        out["mode"] = "pass_intake_only"
    else:
        pricing = (payload or {}).get("pricing", {})
        ppp = pricing.get("price_per_person")
        total = pricing.get("gross_total")
        dep_pct = ((req.get("commercials", {}) if req else {}).get("deposit_pct", 50))
        dep_amt = None
        try:
            dep_amt = float(total) * float(dep_pct) / 100.0 if total is not None else None
        except Exception:
            dep_amt = None

        rule_fired = template_sel.get("rule_fired") or "RULE_UNKNOWN"
        ttype = template_sel.get("template_type") or (req.get("template_type") if req else "A")
        policy_lbl = policy_preset_label(req)
        abs_path, rel_path = parse_filed_path(args.offer_run_summary) if args.offer_run_summary else (None, None)
        excludes = (((req.get("menu", {}) if req else {}).get("excludes_list")) or [])

        lines = [
            f"PASS+FILED: €/person={fmt_money(ppp)} | total={fmt_money(total)}",
            f"deposit: {dep_pct}% ({fmt_money(dep_amt)})",
            f"template={ttype} | rule={rule_fired}",
            f"policy={policy_lbl}",
            f"filed_abs={abs_path or 'n/a'}",
            f"filed_rel={rel_path or 'n/a'} | excludes={','.join(excludes) if excludes else 'none'}",
        ]
        out["mode"] = "pass_offer_filed"
        out["filed_abs"] = abs_path
        out["filed_rel"] = rel_path

    lines = lines[:6]
    out["lines"] = lines

    Path(args.out_txt).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_txt).write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(Path(args.out_txt).resolve()))


if __name__ == "__main__":
    main()
