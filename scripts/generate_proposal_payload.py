import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


TYPE_A_REQUIRED = [
    "client_title",
    "client_name",
    "event_date",
    "guest_count",
    "menu_items",
    "item_quantities",
    "vat_rate",
    "includes_list",
    "payment_method",
]

TYPE_B_REQUIRED = [
    "client_title",
    "client_name",
    "guest_count",
    "venue_name",
    "event_description",
    "service_style",
    "menu_items",
    "course_categories",
    "vat_rate",
    "includes_list",
    "excludes_list",
    "payment_method",
]


def q(v):
    return Decimal(str(v))


def round_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    units = (value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return units * step


def add_issue(issues, severity, code, message, **extra):
    row = {"severity": severity, "code": code, "message": message}
    row.update(extra)
    issues.append(row)


def get_required(template_type: str):
    if template_type == "A":
        return TYPE_A_REQUIRED
    if template_type == "B":
        return TYPE_B_REQUIRED
    return []


ALLOW_EMPTY_LIST_FIELDS = {"course_categories", "excludes_list"}


def is_empty(v):
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


def main():
    p = argparse.ArgumentParser(description="Phase-1 proposal payload pre-flight validation (no DOCX render)")
    p.add_argument("--request", required=True, help="proposal_request.json")
    p.add_argument("--cost", required=True, help="cost_breakdown.json")
    p.add_argument("--menu-summary", required=False, default=None)
    p.add_argument("--out", required=True, help="proposal_payload.json")
    p.add_argument("--validation-out", required=True, help="proposal_validation.json")
    p.add_argument("--issues-out", required=True, help="proposal_issues.json")
    args = p.parse_args()

    req = json.loads(Path(args.request).read_text(encoding="utf-8"))
    cost = json.loads(Path(args.cost).read_text(encoding="utf-8"))
    menu_summary = None
    if args.menu_summary:
        menu_summary = json.loads(Path(args.menu_summary).read_text(encoding="utf-8"))

    issues = []

    template_type = str(req.get("template_type") or req.get("proposal_type") or "").upper()
    if template_type not in {"A", "B"}:
        add_issue(issues, "BLOCK", "PROP-TEMPLATE-TYPE", "template_type must be A or B", value=template_type)

    required_fields = get_required(template_type)

    menu_obj = req.get("menu", {}) if req.get("menu") is not None else {}
    ms_obj = menu_summary or {}

    flat = {
        "client_title": req.get("client", {}).get("title"),
        "client_name": req.get("client", {}).get("name"),
        "event_date": req.get("event", {}).get("date"),
        "guest_count": req.get("event", {}).get("guest_count"),
        "venue_name": req.get("event", {}).get("venue_name"),
        "event_description": req.get("event", {}).get("description"),
        "service_style": req.get("event", {}).get("service_style"),
        "menu_items": menu_obj.get("items") if menu_obj.get("items") is not None else ms_obj.get("items"),
        "item_quantities": menu_obj.get("item_quantities") if menu_obj.get("item_quantities") is not None else ms_obj.get("item_quantities"),
        "course_categories": menu_obj.get("course_categories") if menu_obj.get("course_categories") is not None else ms_obj.get("course_categories"),
        "vat_rate": req.get("pricing", {}).get("vat_rate"),
        "includes_list": req.get("terms", {}).get("includes_list"),
        "excludes_list": req.get("terms", {}).get("excludes_list"),
        "payment_method": req.get("terms", {}).get("payment_method"),
    }

    for f in required_fields:
        v = flat.get(f)
        if f in ALLOW_EMPTY_LIST_FIELDS and isinstance(v, list):
            continue
        if is_empty(v):
            add_issue(issues, "BLOCK", "PROP-MISSING-REQUIRED", "Missing required template field", field=f, template_type=template_type)

    total_cost = q(cost.get("total_cost", 0))
    markup_pct = q(req.get("pricing", {}).get("markup_pct", 0))
    discount_pct = q(req.get("pricing", {}).get("discount_pct", 0))
    vat_rate = q(req.get("pricing", {}).get("vat_rate", 0))
    round_step = q(req.get("pricing", {}).get("round_to", 0.5))

    net_selling = total_cost * (Decimal("1") + (markup_pct / Decimal("100")))
    discount_value = net_selling * (discount_pct / Decimal("100"))
    net_after_discount = net_selling - discount_value
    vat_value = net_after_discount * vat_rate
    gross_total = net_after_discount + vat_value

    net_selling_r = round_to_step(net_after_discount, round_step)
    vat_r = round_to_step(vat_value, round_step)
    gross_r = round_to_step(gross_total, round_step)

    guests = req.get("event", {}).get("guest_count")
    if not guests:
        add_issue(issues, "BLOCK", "PROP-MISSING-GUESTS", "guest_count is required for per-person pricing")
        per_person = Decimal("0")
    else:
        per_person = gross_r / q(guests)

    compliance_status = "PASS"
    if any(i["severity"] == "BLOCK" for i in issues):
        compliance_status = "BLOCKED"
    elif any(i["severity"] == "WARNING" for i in issues):
        compliance_status = "WARNING"

    placeholders = {
        "client_title": req.get("client", {}).get("title", ""),
        "client_name": req.get("client", {}).get("name", ""),
        "client_phone": req.get("client", {}).get("phone", ""),
        "client_email": req.get("client", {}).get("email", ""),
        "event_date": req.get("event", {}).get("date", ""),
        "guest_count": req.get("event", {}).get("guest_count", ""),
        "venue_name": req.get("event", {}).get("venue_name", ""),
        "event_description": req.get("event", {}).get("description", ""),
        "service_style": req.get("event", {}).get("service_style", ""),
        "menu_items": "\n".join((req.get("menu", {}) if req.get("menu") else (menu_summary or {})).get("items", []) or []),
        "item_quantities": ", ".join([str(x) for x in ((req.get("menu", {}) if req.get("menu") else (menu_summary or {})).get("item_quantities", []) or [])]),
        "course_categories": ", ".join((req.get("menu", {}) if req.get("menu") else (menu_summary or {})).get("course_categories", []) or []),
        "price_per_person": float(round_to_step(per_person, q("0.01"))),
        "net_selling": float(net_selling_r),
        "vat_value": float(vat_r),
        "gross_total": float(gross_r),
        "vat_rate": float(vat_rate),
        "includes_list": "\n".join(req.get("terms", {}).get("includes_list", []) or []),
        "excludes_list": "\n".join(req.get("terms", {}).get("excludes_list", []) or []),
        "payment_method": req.get("terms", {}).get("payment_method", ""),
    }

    payload = {
        "proposal_id": req.get("proposal_id"),
        "proposal_type": template_type,
        "template_type": template_type,
        "compliance_status": compliance_status,
        "client": req.get("client", {}),
        "event": req.get("event", {}),
        "menu": req.get("menu", {}) if req.get("menu") else (menu_summary or {}),
        "pricing": {
            "cost_total": float(total_cost),
            "markup_pct": float(markup_pct),
            "discount_pct": float(discount_pct),
            "vat_rate": float(vat_rate),
            "round_to": float(round_step),
            "net_selling": float(net_selling_r),
            "vat_value": float(vat_r),
            "gross_total": float(gross_r),
            "price_per_person": float(round_to_step(per_person, q("0.01"))),
            "formula": "net_selling = total_cost * (1 + markup_pct/100); discount on net before VAT; gross = net + VAT",
        },
        "terms": req.get("terms", {}),
        "template_refs": {
            "verbatim_blocks": {
                "intro_block_ref": "TEMPLATE_FIXED_INTRO",
                "closing_block_ref": "TEMPLATE_FIXED_CLOSING",
                "sender_block_ref": "TEMPLATE_FIXED_SENDER"
            },
            "placeholders_only": True
        },
        "placeholder_values": placeholders
    }

    validation = {
        "proposal_id": req.get("proposal_id"),
        "template_type": template_type,
        "required_fields": required_fields,
        "missing_fields": [i.get("field") for i in issues if i.get("code") == "PROP-MISSING-REQUIRED"],
        "checks": {
            "template_type_valid": template_type in {"A", "B"},
            "required_fields_complete": not any(i.get("code") == "PROP-MISSING-REQUIRED" for i in issues),
            "pricing_formula_applied": True,
            "placeholders_only": True,
            "docx_rendered": False
        },
        "compliance_status": compliance_status
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    vout = Path(args.validation_out)
    vout.parent.mkdir(parents=True, exist_ok=True)
    vout.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")

    iout = Path(args.issues_out)
    iout.parent.mkdir(parents=True, exist_ok=True)
    iout.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"compliance_status": compliance_status, "issues": len(issues)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
