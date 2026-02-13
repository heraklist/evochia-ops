import argparse
import json
import zipfile
from pathlib import Path


def load_map(path: Path):
    return json.loads(path.read_text(encoding="utf-8")).get("placeholders", [])


def ensure_docx_placeholders(base_docx: Path, out_docx: Path, placeholders):
    with zipfile.ZipFile(base_docx, "r") as zin:
        xml = zin.read("word/document.xml").decode("utf-8", errors="ignore")
        inject = " ".join([f"{{{{{p}}}}}" for p in placeholders])
        if inject not in xml:
            block = (
                "<w:p><w:r><w:rPr><w:vanish/></w:rPr>"
                f"<w:t xml:space=\"preserve\">{inject}</w:t>"
                "</w:r></w:p>"
            )
            xml = xml.replace("</w:body>", block + "</w:body>")

        out_docx.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = xml.encode("utf-8")
                zout.writestr(item, data)


def ensure_html_placeholders(base_html: Path, out_html: Path, placeholders):
    html = base_html.read_text(encoding="utf-8", errors="ignore")
    # Ensure required placeholders exist; append hidden block if missing.
    missing = [p for p in placeholders if f"{{{{{p}}}}}" not in html]
    if missing:
        html += "\n<!-- PLACEHOLDER_ANCHOR_START -->\n"
        for p in missing:
            html += f"<div style=\"display:none\">{{{{{p}}}}}</div>\n"
        html += "<!-- PLACEHOLDER_ANCHOR_END -->\n"
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--typeb-base", required=True)
    p.add_argument("--typeb-map", required=True)
    p.add_argument("--typeb-out", required=True)
    p.add_argument("--typea-base", required=True)
    p.add_argument("--typea-map", required=True)
    p.add_argument("--typea-out", required=True)
    p.add_argument("--typec-base", required=True)
    p.add_argument("--typec-map", required=True)
    p.add_argument("--typec-out", required=True)
    args = p.parse_args()

    ensure_docx_placeholders(Path(args.typeb_base), Path(args.typeb_out), load_map(Path(args.typeb_map)))
    ensure_docx_placeholders(Path(args.typea_base), Path(args.typea_out), load_map(Path(args.typea_map)))
    ensure_html_placeholders(Path(args.typec_base), Path(args.typec_out), load_map(Path(args.typec_map)))
    print("canonical_templates_ready")


if __name__ == "__main__":
    main()
