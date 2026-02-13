import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

CRITICAL_FIELDS = ["supplier_sku", "product_name", "pack_size", "pack_unit", "price"]


def to_bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def to_float(v, default=None):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def add_issue(issues, severity, code, message, **extra):
    row = {"severity": severity, "code": code, "message": message}
    row.update(extra)
    issues.append(row)


def parse_packaging(packaging: str):
    s = str(packaging or "").strip().lower()
    if not s:
        return None, None
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(kg|g|l|lt|ml|pcs|pc|τεμ|κιβ|συσκ)", s)
    if not m:
        return None, None
    qty = to_float(m.group(1), None)
    unit_raw = m.group(2).upper()
    return qty, unit_raw


def col_to_idx(cell_ref: str):
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def parse_shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    out = []
    for si in root.findall("x:si", ns):
        parts = [t.text or "" for t in si.findall(".//x:t", ns)]
        out.append("".join(parts))
    return out


def get_sheet_path(z, sheet_name=None):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    ns = {
        "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    sheets = wb.findall("x:sheets/x:sheet", ns)
    target_rid = None
    for s in sheets:
        if sheet_name is None or s.get("name") == sheet_name:
            target_rid = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            break
    if not target_rid:
        raise RuntimeError("XLSX sheet not found")
    for rel in rels.findall("pr:Relationship", ns):
        if rel.get("Id") == target_rid:
            tgt = rel.get("Target").lstrip("/")
            return tgt if tgt.startswith("xl/") else ("xl/" + tgt)
    raise RuntimeError("XLSX relationship for sheet not found")


def parse_sheet_rows(z, sheet_path, shared_strings):
    root = ET.fromstring(z.read(sheet_path))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = []
    for r in root.findall(".//x:sheetData/x:row", ns):
        vals = {}
        for c in r.findall("x:c", ns):
            ref = c.get("r")
            idx = col_to_idx(ref)
            t = c.get("t")
            v = c.find("x:v", ns)
            if t == "inlineStr":
                it = c.find("x:is/x:t", ns)
                val = (it.text if it is not None else "") or ""
            elif v is None:
                val = ""
            else:
                raw = v.text or ""
                if t == "s":
                    val = shared_strings[int(raw)] if raw.isdigit() and int(raw) < len(shared_strings) else ""
                else:
                    val = raw
            vals[idx] = val
        if vals:
            max_idx = max(vals.keys())
            row_vals = [vals.get(i, "") for i in range(max_idx + 1)]
            rows.append(row_vals)
    return rows


def main():
    p = argparse.ArgumentParser(description="Import supplier XLSX -> RawOffer[]")
    p.add_argument("--input", required=True)
    p.add_argument("--supplier-profile", required=True)
    p.add_argument("--captured-at", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--batch-out", required=True)
    p.add_argument("--needs-review", required=False, default=None)
    p.add_argument("--issues-out", required=False, default=None)
    args = p.parse_args()

    profile = json.loads(Path(args.supplier_profile).read_text(encoding="utf-8"))
    xcfg = profile.get("xlsx", {})
    cmap = xcfg.get("column_map", profile.get("column_map", {}))
    defaults = profile.get("defaults", {})
    unit_map = {str(k).upper(): v for k, v in (profile.get("unit_map", {}) or {}).items()}

    captured = datetime.now(timezone.utc) if not args.captured_at else datetime.fromisoformat(args.captured_at.replace("Z", "+00:00"))
    catalog_valid_days = int(profile.get("catalog_valid_days", defaults.get("max_age_days", 14)))
    valid_until = captured + timedelta(days=catalog_valid_days)

    inp = Path(args.input)
    source_hash = hashlib.sha1(inp.read_bytes()).hexdigest()[:10]

    with zipfile.ZipFile(inp, "r") as z:
        shared = parse_shared_strings(z)
        sheet_path = get_sheet_path(z, xcfg.get("sheet"))
        rows_all = parse_sheet_rows(z, sheet_path, shared)

    header_row = int(xcfg.get("header_row", 1))
    if len(rows_all) < header_row:
        raise RuntimeError("XLSX header_row out of range")

    headers = [str(x).strip() if x is not None else "" for x in rows_all[header_row - 1]]
    data_rows = rows_all[header_row:]

    stop_rules = xcfg.get("stop_rules", {})
    stop_on_blank_name = bool(stop_rules.get("blank_product_name", False))

    required_columns = xcfg.get("required_columns", [])
    missing_cols = [c for c in required_columns if c not in headers]

    issues = []
    needs_review = []
    out_rows = []

    if missing_cols:
        add_issue(issues, "BLOCK", "XLSX-MISSING-COLUMNS", "Required XLSX columns missing", missing_columns=missing_cols)

    for i, row in enumerate(data_rows, start=1):
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        r = {headers[j]: row[j] for j in range(min(len(headers), len(row)))}

        sku = r.get(cmap.get("supplier_sku", "supplier_sku"), "")
        name = r.get(cmap.get("product_name", "product_name"), "")
        category = r.get(cmap.get("category", "category"), "")
        pack_size = r.get(cmap.get("pack_size", "pack_size"), None)
        pack_unit_raw = r.get(cmap.get("pack_unit", "pack_unit"), "")
        packaging = r.get(cmap.get("packaging", "packaging"), "")
        price = r.get(cmap.get("price", "price"), None)

        if stop_on_blank_name and (name is None or str(name).strip() == ""):
            break

        offer_id = f"OFF-{profile.get('supplier_code','SUP')}-{captured.strftime('%Y%m%d')}-{i:04d}"

        if to_float(pack_size, None) is None or str(pack_unit_raw).strip() == "":
            pkg_qty, pkg_unit = parse_packaging(packaging)
            if to_float(pack_size, None) is None:
                pack_size = pkg_qty
            if str(pack_unit_raw).strip() == "":
                pack_unit_raw = pkg_unit or ""

        missing_crit = []
        if str(sku).strip() == "":
            missing_crit.append("supplier_sku")
        if str(name).strip() == "":
            missing_crit.append("product_name")
        if to_float(pack_size, None) is None:
            missing_crit.append("pack_size")
        if str(pack_unit_raw).strip() == "":
            missing_crit.append("pack_unit")
        if to_float(price, None) is None:
            missing_crit.append("price")

        if missing_crit or missing_cols:
            add_issue(issues, "WARNING", "IMPORT-MISSING-CRITICAL-FIELD", "Critical field missing; row sent to needs_review", offer_id=offer_id, missing_fields=missing_crit)
            needs_review.append({
                "offer_id": offer_id,
                "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                "supplier_sku": str(sku or ""),
                "product_name": str(name or ""),
                "reason": "IMPORT-MISSING-CRITICAL-FIELD",
                "missing_fields": missing_crit,
                "action": "BLOCK_UNTIL_REVIEWED",
            })
            continue

        unit_src = str(pack_unit_raw).upper().strip()
        unit_norm = unit_map.get(unit_src)
        if unit_norm is None:
            add_issue(issues, "WARNING", "IMPORT-UNSUPPORTED-UNIT", "Unsupported XLSX unit; row sent to needs_review", offer_id=offer_id, raw_unit=unit_src)
            needs_review.append({
                "offer_id": offer_id,
                "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
                "supplier_sku": str(sku or ""),
                "product_name": str(name or ""),
                "reason": "IMPORT-UNSUPPORTED-UNIT",
                "raw_unit": unit_src,
                "action": "BLOCK_UNTIL_REVIEWED",
            })
            continue

        out_rows.append({
            "offer_id": offer_id,
            "supplier": profile.get("supplier_name", profile.get("supplier_id", "SUPPLIER")),
            "supplier_sku": str(sku),
            "product_name": str(name),
            "category": str(category or ""),
            "tier": defaults.get("tier", "standard"),
            "pack_size": to_float(pack_size, 1),
            "pack_unit": unit_norm,
            "price": to_float(price, 0),
            "price_per_base_unit": None,
            "currency": r.get(cmap.get("currency", "currency"), defaults.get("currency", "EUR")),
            "vat_rate": to_float(r.get(cmap.get("vat_rate", "vat_rate"), defaults.get("vat_rate", 0.13)), defaults.get("vat_rate", 0.13)),
            "captured_at": captured.isoformat(),
            "valid_until": valid_until.isoformat(),
            "source": f"import_xlsx:{inp.name}",
            "in_stock": to_bool(r.get(cmap.get("in_stock", "in_stock"), True)),
            "notes": "",
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    batch = {
        "batch_id": f"BATCH-{profile.get('supplier_id','unknown')}-{captured.strftime('%Y%m%d-%H%M%S')}-{source_hash}",
        "source": "xlsx",
        "source_hash": source_hash,
        "supplier_id": profile.get("supplier_id", "unknown"),
        "layout_version": profile.get("layout_version", "v1"),
        "captured_at": captured.isoformat(),
        "catalog_valid_days": catalog_valid_days,
        "files": [{"path": str(args.input), "kind": "xlsx"}],
        "stats": {
            "rows_in": len(data_rows),
            "rows_out": len(out_rows),
            "rows_needs_review": len(needs_review),
        },
    }
    Path(args.batch_out).write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.needs_review:
        Path(args.needs_review).parent.mkdir(parents=True, exist_ok=True)
        Path(args.needs_review).write_text(json.dumps(needs_review, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.issues_out:
        Path(args.issues_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.issues_out).write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"rows": len(out_rows), "needs_review": len(needs_review), "issues": len(issues), "batch": batch["batch_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
