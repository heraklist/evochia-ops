import json, zipfile
from pathlib import Path

base = Path('skills/evochia-ops/templates/ref_typeB_ervin_tehla_14.02.26.docx.docx')
out = Path('skills/evochia-ops/templates/Template_TypeB.docx')
ph = json.loads(Path('skills/evochia-ops/templates/placeholder_map_type_b.json').read_text(encoding='utf-8'))['placeholders']

with zipfile.ZipFile(base, 'r') as zin:
    xml = zin.read('word/document.xml').decode('utf-8', 'ignore')
    inject = ' '.join([f'{{{{{p}}}}}' for p in ph])
    if inject not in xml:
        xml = xml.replace('</w:body>', f'<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t xml:space="preserve">{inject}</w:t></w:r></w:p></w:body>')

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = xml.encode('utf-8')
            zout.writestr(item, data)

print('ok')
