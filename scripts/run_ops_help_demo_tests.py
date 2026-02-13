import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    return r.stdout.strip()


def main():
    out = Path(run([sys.executable, str(S / "run_pipeline.py"), "ops-help"]))
    txt = out / "telegram_ops_help.txt"
    if not txt.exists():
        raise AssertionError("ops-help output missing")
    lines = txt.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) > 20:
        raise AssertionError("ops-help exceeded 20 lines")
    must = ["NEW OFFER:", "PATCH & RESUME:", "SEARCH & OPEN:"]
    body = "\n".join(lines)
    for m in must:
        if m not in body:
            raise AssertionError(f"Missing section {m}")
    print("OPS_HELP_DEMO_PASS")


if __name__ == "__main__":
    main()
