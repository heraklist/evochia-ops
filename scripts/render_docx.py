import argparse
import json
import re
import zipfile
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def add_issue(issues, severity, code, message, **extra):
    row = {"severity": severity, "code": code, "message": message}
    row.update(extra)
    issues.append(row)


def read_xml_parts(zf):
    names = [n for n in zf.namelist() if n.startswith("word/") and (n.endswith(".xml"))]
    return {n: zf.read(n).decode("utf-8", errors="ignore") for n in names}


def extract_placeholders(xml_text):
    return set(PLACEHOLDER_RE.findall(xml_text or ""))


def main():
    p = argparse.ArgumentParser(description="Render DOCX with strict placeholder validation (no style reflow)")
    p.add_argument("--payload", required=True)
    p.add_argument("--template", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--placeholder-map", required=False, default=None)
    p.add_argument("--validation-out", required=True)
    p.add_argument("--issues-out", required=True)
    args = p.parse_args()

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    template = Path(args.template)
    out = Path(args.out)

    issues = []

    if payload.get("compliance_status") != "PASS":
        add_issue(issues, "BLOCK", "TEMPLATE-COMPLIANCE-NOT-PASS", "DOCX render allowed only when compliance_status == PASS", compliance_status=payload.get("compliance_status"))

    if not template.exists():
        add_issue(issues, "BLOCK", "TEMPLATE-NOT-FOUND", "Template file not found", template=str(template))

    placeholders = payload.get("placeholder_values", {}) or {}
    expected_keys = list(placeholders.keys())
    if args.placeholder_map:
        pm = json.loads(Path(args.placeholder_map).read_text(encoding="utf-8"))
        expected_keys = pm.get("placeholders", [])

    expected_template = payload.get("template_type")
    if expected_template not in {"A", "B"}:
        add_issue(issues, "BLOCK", "TEMPLATE-TYPE-INVALID", "template_type must be A or B", template_type=expected_template)

    rendered = False
    unresolved = []
    template_placeholders = []

    if not any(i["severity"] == "BLOCK" for i in issues):
        with zipfile.ZipFile(template, "r") as zf:
            parts = read_xml_parts(zf)
            all_text = "\n".join(parts.values())
            found = sorted(extract_placeholders(all_text))
            template_placeholders = found

            # missing placeholders in docx template
            for key in expected_keys:
                if key not in found:
                    add_issue(
                        issues,
                        "BLOCK",
                        "TEMPLATE-PLACEHOLDER-MISSING",
                        "Placeholder key required by template map not present in DOCX template",
                        placeholder=key,
                    )

            if not any(i["severity"] == "BLOCK" for i in issues):
                replaced_parts = {}
                for name, xml in parts.items():
                    new_xml = xml
                    for k, v in placeholders.items():
                        new_xml = re.sub(r"\{\{\s*" + re.escape(k) + r"\s*\}\}", str(v), new_xml)
                    replaced_parts[name] = new_xml

                check_text = "\n".join(replaced_parts.values())
                unresolved = sorted(extract_placeholders(check_text))
                if unresolved:
                    add_issue(
                        issues,
                        "BLOCK",
                        "TEMPLATE-UNRESOLVED-PLACEHOLDERS",
                        "Template still contains unresolved placeholders after replacement",
                        unresolved=unresolved,
                    )

                if not any(i["severity"] == "BLOCK" for i in issues):
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                        for item in zf.infolist():
                            data = zf.read(item.filename)
                            if item.filename in replaced_parts:
                                data = replaced_parts[item.filename].encode("utf-8")
                            zout.writestr(item, data)
                    rendered = True

    compliance_status = "PASS"
    if any(i["severity"] == "BLOCK" for i in issues):
        compliance_status = "BLOCKED"
    elif any(i["severity"] == "WARNING" for i in issues):
        compliance_status = "WARNING"

    validation = {
        "template": str(template),
        "output": str(out),
        "rendered": rendered,
        "template_placeholders": template_placeholders,
        "unresolved_after_render": unresolved,
        "compliance_status": compliance_status,
        "checks": {
            "pass_required": payload.get("compliance_status") == "PASS",
            "template_exists": template.exists(),
            "placeholders_only": payload.get("template_refs", {}).get("placeholders_only", False),
            "no_unresolved_placeholders": len(unresolved) == 0,
        },
    }

    Path(args.validation_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.validation_out).write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.issues_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.issues_out).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    # Consistency update: when DOCX render succeeds, mark docx_rendered=true in sibling proposal_validation.json
    if rendered:
        proposal_validation_path = Path(args.validation_out).with_name("proposal_validation.json")
        if proposal_validation_path.exists():
            try:
                proposal_validation = json.loads(proposal_validation_path.read_text(encoding="utf-8"))
                checks = proposal_validation.get("checks")
                if not isinstance(checks, dict):
                    checks = {}
                    proposal_validation["checks"] = checks
                checks["docx_rendered"] = True
                proposal_validation_path.write_text(json.dumps(proposal_validation, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    print(json.dumps({"rendered": rendered, "compliance_status": compliance_status, "issues": len(issues)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
