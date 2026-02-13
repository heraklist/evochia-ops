import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _norm_hint(v: str):
    s = str(v or "").strip().upper().replace("TYPE", "").replace("_", "").replace("-", "").replace(" ", "")
    if s in {"A", "B", "C"}:
        return s
    return None


def _pick(req: dict):
    hint = _norm_hint(req.get("template_hint"))
    event_style = str(req.get("event_style") or req.get("event", {}).get("event_style") or "").strip().lower()
    service_type = str(req.get("service_type") or req.get("event", {}).get("service_type") or "").strip().lower()

    if hint:
        return hint, "RULE_HINT_OVERRIDE", service_type, event_style, req.get("template_hint")
    if event_style == "ombre_et_desir":
        return "C", "RULE_C_OMBRE", service_type, event_style, req.get("template_hint")
    if service_type == "delivery" and event_style == "finger":
        return "B", "RULE_B_DELIVERY_FINGER", service_type, event_style, req.get("template_hint")
    return "A", "RULE_A_DEFAULT", service_type, event_style, req.get("template_hint")


def main():
    p = argparse.ArgumentParser(description="Deterministic template selector")
    p.add_argument("--request", required=True, help="proposal_request.json")
    p.add_argument("--out", required=True, help="selection output json")
    args = p.parse_args()

    req_path = Path(args.request)
    req = json.loads(req_path.read_text(encoding="utf-8"))

    template_type, rule, service_type, event_style, template_hint = _pick(req)
    out = {
        "template_type": template_type,
        "service_type": service_type,
        "event_style": event_style,
        "template_hint": template_hint,
        "rule_fired": rule,
        "request": str(req_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
