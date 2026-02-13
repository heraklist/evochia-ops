import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def _extract_date(text):
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return m.group(1) if m else None


def _extract_guest_count(text):
    m = re.search(r"\b(\d{1,4})\s*(?:guests|guest|άτομα|ατομα|pax)\b", text, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _extract_service_type(text):
    t = text.lower()
    if "delivery" in t or "del" in t:
        return "DEL"
    if "private chef" in t or re.search(r"\bpc\b", t):
        return "PC"
    if "catering" in t or re.search(r"\bcat\b", t):
        return "CAT"
    return None


def _extract_event_style(text):
    t = text.lower()
    if "finger" in t:
        return "finger"
    if "plated" in t:
        return "plated"
    if "buffet" in t:
        return "buffet"
    if "ombre" in t:
        return "ombre_et_desir"
    return None


def _extract_template_hint(text):
    m = re.search(r"\btemplate\s*[:=]?\s*([ABC])\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m2 = re.search(r"\btype\s*([ABC])\b", text, flags=re.IGNORECASE)
    return m2.group(1).upper() if m2 else None


def _extract_budget(text):
    t = text.lower()
    pp = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:€|eur)?\s*(?:/|per|ανά)?\s*(?:person|άτομο|ατομο|pp)", t)
    total = re.search(r"(?:total|συνολ(?:ικό|ικο)|budget)\s*[:=]?\s*(\d+(?:[\.,]\d+)?)", t)
    bpp = float(pp.group(1).replace(",", ".")) if pp else None
    btot = float(total.group(1).replace(",", ".")) if total else None
    return bpp, btot


def _extract_email(text):
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None


def _extract_phone(text):
    m = re.search(r"\b(?:\+30)?\d{10}\b", text)
    return m.group(0) if m else None


def _extract_client_name(text):
    m = re.search(r"(?:client|πελάτης|ονομα|name)\s*[:=]\s*([^,\n]+)", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_location(text):
    m = re.search(r"(?:location|address|διευθυνση|περιοχη)\s*[:=]\s*([^\n]+)", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_theme(text):
    m = re.search(r"(?:theme|κουζινα|cuisine)\s*[:=]\s*([^\n]+)", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_tier(text):
    t = text.lower()
    if "premium" in t:
        return "premium"
    if "standard" in t:
        return "standard"
    return None


def _extract_excludes(text):
    m = re.search(r"(?:exclude|excludes|χωρις|χωρίς)\s*[:=]\s*([^\n]+)", text, flags=re.IGNORECASE)
    if not m:
        return []
    return [x.strip() for x in re.split(r",|;", m.group(1)) if x.strip()]


def service_word(code):
    return {"DEL": "delivery", "CAT": "catering", "PC": "private_chef"}.get(code, "")


def select_template(service_word_val, event_style, hint):
    if hint in {"A", "B", "C"}:
        return hint, "RULE_HINT_OVERRIDE"
    if event_style == "ombre_et_desir":
        return "C", "RULE_C_OMBRE"
    if service_word_val == "delivery" and event_style == "finger":
        return "B", "RULE_B_DELIVERY_FINGER"
    return "A", "RULE_A_DEFAULT"


def main():
    p = argparse.ArgumentParser(description="Offer intake wizard (deterministic, Telegram-first)")
    p.add_argument("--text", required=True)
    p.add_argument("--defaults", required=True)
    p.add_argument("--out-request", required=True)
    p.add_argument("--summary-out", required=True)
    p.add_argument("--transcript-out", required=True)
    p.add_argument("--template-selection-out", required=True)
    p.add_argument("--channel", default="telegram")
    args = p.parse_args()

    text = str(args.text)
    defaults = json.loads(Path(args.defaults).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()

    event_date = _extract_date(text)
    guest_count = _extract_guest_count(text)
    service_code = _extract_service_type(text)
    event_style = _extract_event_style(text)
    hint = _extract_template_hint(text)
    budget_pp, budget_total = _extract_budget(text)
    location_text = _extract_location(text)
    client_name = _extract_client_name(text)
    email = _extract_email(text)
    phone = _extract_phone(text)
    theme = _extract_theme(text)
    tier = _extract_tier(text) or "standard"
    excludes = _extract_excludes(text)

    missing = []
    if not event_date:
        missing.append("event.event_date")
    if not guest_count:
        missing.append("event.guest_count")
    if not budget_pp and not budget_total:
        missing.append("commercials.budget")
    if not service_code:
        missing.append("event.service_type")
    if not event_style:
        missing.append("event.event_style")

    standard_questions = [
        "Για να το κλειδώσω: ημερομηνία (YYYY-MM-DD), πόσα άτομα και περιοχή/διεύθυνση;",
        "Τι υπηρεσία θέλεις; (DEL=Delivery / CAT=Catering / PC=Private Chef) και τι στυλ; (finger / plated / buffet)",
        "Κουζίνα/θεματική και περιορισμοί; (π.χ. sushi, vegan επιλογές, αλλεργίες, excludes)",
        "Budget ανά άτομο ή συνολικό; Και προτιμάς standard ή premium πρώτες ύλες;",
        "Στοιχεία πελάτη για την προσφορά: όνομα/εταιρεία + τηλέφωνο/email. Προκαταβολή (default 50%) ΟΚ;",
    ]

    next_question = None
    if "event.event_date" in missing or "event.guest_count" in missing:
        next_question = standard_questions[0]
    elif "event.service_type" in missing or "event.event_style" in missing:
        next_question = standard_questions[1]
    elif "commercials.budget" in missing:
        next_question = standard_questions[3]

    svc_word = service_word(service_code)
    ttype, rule_fired = select_template(svc_word, event_style, hint)

    request_id = "INTAKE-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    proposal_request = {
        "request_id": request_id,
        "proposal_id": request_id,
        "template_type": ttype,
        "client": {
            "title": "κ.",
            "name": client_name,
            "email": email,
            "phone": phone,
        },
        "event": {
            "event_date": event_date,
            "date": event_date,
            "guest_count": guest_count,
            "location_text": location_text,
            "venue_name": location_text or "TBD Venue",
            "service_type": svc_word,
            "service_type_code": service_code,
            "event_style": event_style,
            "template_hint": hint,
            "description": theme or "Offer intake",
        },
        "menu": {
            "theme": theme,
            "items": [theme] if theme else ["TBD menu"],
            "item_quantities": [guest_count] if guest_count else [],
            "tier": tier,
            "course_categories": [],
            "excludes_list": excludes,
            "notes": "",
        },
        "pricing": {
            "markup_pct": defaults.get("pricing", {}).get("markup_pct", 300),
            "discount_pct": defaults.get("pricing", {}).get("discount_pct", 0),
            "vat_rate": defaults.get("vat", {}).get("delivery_default", 0.13),
            "round_to": defaults.get("pricing", {}).get("round_to", 0.5),
        },
        "terms": {
            "includes_list": ["as agreed"],
            "excludes_list": excludes,
            "payment_method": "bank transfer",
        },
        "commercials": {
            "budget_per_person": budget_pp,
            "budget_total": budget_total,
            "deposit_pct": defaults.get("pricing", {}).get("deposit_pct", 50),
            "discount_pct": defaults.get("pricing", {}).get("discount_pct", 0),
        },
        "policy": {
            "phase": 3,
            "policies_path": "skills/evochia-ops/policies/sourcing_policies.json",
        },
        "meta": {
            "channel": args.channel,
            "source_text": text,
            "created_at": now,
            "intake_transcript_ref": str(args.transcript_out),
        },
    }

    status = "PASS" if len(missing) == 0 else "BLOCKED"
    summary = {
        "status": status,
        "missing_required": missing,
        "resolved": {
            "event_date": event_date,
            "guest_count": guest_count,
            "service_type": service_code,
            "event_style": event_style,
            "template_type": ttype,
        },
        "defaults_applied": {
            "tier": tier,
            "course_categories": [],
            "excludes_list": excludes,
            "deposit_pct": defaults.get("pricing", {}).get("deposit_pct", 50),
            "discount_pct": defaults.get("pricing", {}).get("discount_pct", 0),
        },
        "next_question": next_question,
    }

    transcript_path = Path(args.transcript_out)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    if transcript_path.exists():
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    else:
        transcript = {"turns": []}
    transcript.setdefault("turns", []).append({
        "timestamp": now,
        "input_text": text,
        "parsed": summary.get("resolved", {}),
        "status": status,
        "missing_required": missing,
        "next_question": next_question,
    })

    template_selection = {
        "template_type": ttype,
        "service_type": svc_word,
        "event_style": event_style,
        "template_hint": hint,
        "rule_fired": rule_fired,
        "timestamp": now,
    }

    for pth, obj in [
        (args.out_request, proposal_request),
        (args.summary_out, summary),
        (args.transcript_out, transcript),
        (args.template_selection_out, template_selection),
    ]:
        outp = Path(pth)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"status": status, "missing": len(missing)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
