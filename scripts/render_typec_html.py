import argparse
import json
from pathlib import Path


def add_issue(issues, severity, code, message, **extra):
    row = {"severity": severity, "code": code, "message": message}
    row.update(extra)
    issues.append(row)


def main():
    p = argparse.ArgumentParser(description="Render Type C HTML with placeholder injection only")
    p.add_argument("--template", required=True)
    p.add_argument("--payload", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--validation-out", required=True)
    p.add_argument("--issues-out", required=True)
    args = p.parse_args()

    template = Path(args.template)
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    html = template.read_text(encoding="utf-8", errors="ignore") if template.exists() else ""

    issues = []
    if payload.get("compliance_status") != "PASS":
        add_issue(issues, "BLOCK", "TYPEC-COMPLIANCE-NOT-PASS", "Render allowed only when compliance_status == PASS")

    placeholders = payload.get("placeholder_values", {}) or {}
    required = ["COURSE_COUNT", "PRICE_PER_PERSON", "MENU_BLOCKS"]

    for r in required:
        if f"{{{{{r}}}}}" not in html:
            add_issue(issues, "BLOCK", "TEMPLATE-PLACEHOLDER-MISSING", "Missing Type C placeholder in template", placeholder=r)
        if r not in placeholders:
            add_issue(issues, "BLOCK", "TYPEC-PAYLOAD-MISSING", "Missing Type C placeholder value in payload", placeholder=r)

    # consistency check
    cc = placeholders.get("COURSE_COUNT")
    blocks = placeholders.get("MENU_BLOCKS", "")
    if cc is not None:
        try:
            cci = int(cc)
            est = blocks.count("<section") if isinstance(blocks, str) else 0
            if est and est != cci:
                add_issue(issues, "BLOCK", "TYPEC-INCONSISTENT-COURSE-COUNT", "COURSE_COUNT inconsistent with MENU_BLOCKS")
        except Exception:
            add_issue(issues, "BLOCK", "TYPEC-COURSE-COUNT-INVALID", "COURSE_COUNT must be integer")

    rendered = False
    if not any(i["severity"] == "BLOCK" for i in issues):
        out_html = html
        for k, v in placeholders.items():
            out_html = out_html.replace(f"{{{{{k}}}}}", str(v))
        if "{{" in out_html or "}}" in out_html:
            add_issue(issues, "BLOCK", "TEMPLATE-UNRESOLVED-PLACEHOLDERS", "Unresolved placeholders remain after render")
        else:
            Path(args.out).write_text(out_html, encoding="utf-8")
            rendered = True

    status = "PASS"
    if any(i["severity"] == "BLOCK" for i in issues):
        status = "BLOCKED"
    elif any(i["severity"] == "WARNING" for i in issues):
        status = "WARNING"

    validation = {
        "rendered": rendered,
        "compliance_status": status,
        "template": str(template),
        "output": str(args.out)
    }
    Path(args.validation_out).write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.issues_out).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rendered": rendered, "compliance_status": status, "issues": len(issues)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
