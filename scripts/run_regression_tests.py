import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
D = ROOT / "data"
T = ROOT / "templates"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")


def assert_pass(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("compliance_status") != "PASS":
        raise AssertionError(f"Expected PASS in {path}, got {obj.get('compliance_status')}")


def assert_rendered(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("rendered") is not True:
        raise AssertionError(f"Expected rendered=true in {path}")


def main():
    run([sys.executable, str(S / "run_supplier_fixture_tests.py")])
    run([sys.executable, str(S / "run_phase30_policy_demo.py")])
    run([sys.executable, str(S / "run_intake_demo_tests.py")])
    run([sys.executable, str(S / "run_telegram_reply_demo_tests.py")])
    run([sys.executable, str(S / "run_client_slug_regression_test.py")])
    run([sys.executable, str(S / "run_xlsx_demo_tests.py")])
    run([sys.executable, str(S / "run_pdf_ocr_demo_tests.py")])
    run([sys.executable, str(S / "run_onboarding_fixture_tests.py"), "--supplier-id", "demo_supplier_kappa"])
    run([sys.executable, str(S / "run_proposal_search_demo_tests.py")])
    run([sys.executable, str(S / "run_open_result_demo_tests.py")])
    run([sys.executable, str(S / "run_recipe_skeleton_demo_tests.py")])
    run([sys.executable, str(S / "run_recipe_review_demo_tests.py")])
    run([sys.executable, str(S / "run_menu_offer_demo_tests.py")])
    run([sys.executable, str(S / "run_resume_demo_tests.py")])
    run([sys.executable, str(S / "run_ops_help_demo_tests.py")])
    run([sys.executable, str(S / "run_blocked_next_action_demo_tests.py")])
    run([sys.executable, str(S / "run_open_path_demo_tests.py")])
    run([sys.executable, str(S / "run_daily_refresh_demo_tests.py")])
    run([sys.executable, str(S / "run_source_registry_demo_tests.py")])
    run([sys.executable, str(S / "run_source_health_status_alias_demo_tests.py")])
    # Type B
    run([
        sys.executable, str(S / "generate_proposal_payload.py"),
        "--request", str(D / "sample_proposal_request.json"),
        "--cost", str(D / "recipes" / "sample_recipe_cost.json"),
        "--out", str(D / "demo_typeb_proposal_payload.json"),
        "--validation-out", str(D / "demo_typeb_proposal_validation.json"),
        "--issues-out", str(D / "demo_typeb_proposal_issues.json"),
    ])
    run([
        sys.executable, str(S / "render_docx.py"),
        "--payload", str(D / "demo_typeb_proposal_payload.json"),
        "--template", str(T / "Template_TypeB.docx"),
        "--placeholder-map", str(T / "placeholder_map_type_b.json"),
        "--out", str(D / "demo_typeb_output.docx"),
        "--validation-out", str(D / "demo_typeb_render_validation.json"),
        "--issues-out", str(D / "demo_typeb_render_issues.json"),
    ])

    # Type A
    run([
        sys.executable, str(S / "generate_proposal_payload.py"),
        "--request", str(D / "sample_proposal_request.json"),
        "--cost", str(D / "recipes" / "sample_recipe_cost.json"),
        "--out", str(D / "demo_typea_proposal_payload.json"),
        "--validation-out", str(D / "demo_typea_proposal_validation.json"),
        "--issues-out", str(D / "demo_typea_proposal_issues.json"),
    ])
    run([
        sys.executable, str(S / "render_docx.py"),
        "--payload", str(D / "demo_typea_proposal_payload.json"),
        "--template", str(T / "Template_TypeA.docx"),
        "--placeholder-map", str(T / "placeholder_map_type_a.json"),
        "--out", str(D / "demo_typea_output.docx"),
        "--validation-out", str(D / "demo_typea_render_validation.json"),
        "--issues-out", str(D / "demo_typea_render_issues.json"),
    ])

    # Type C
    run([
        sys.executable, str(S / "render_typec_html.py"),
        "--template", str(T / "Template_TypeC_OmbreEtDesir.html"),
        "--payload", str(D / "demo_typec_payload.json"),
        "--out", str(D / "demo_typec_output.html"),
        "--validation-out", str(D / "demo_typec_validation.json"),
        "--issues-out", str(D / "demo_typec_issues.json"),
    ])

    assert_pass(D / "demo_typea_proposal_validation.json")
    assert_pass(D / "demo_typeb_proposal_validation.json")
    assert_rendered(D / "demo_typea_render_validation.json")
    assert_rendered(D / "demo_typeb_render_validation.json")
    assert_rendered(D / "demo_typec_validation.json")
    print("REGRESSION_PASS")


if __name__ == "__main__":
    main()
