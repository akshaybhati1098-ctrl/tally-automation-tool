import pytesseract
from PIL import Image
import re
import pandas as pd
from pdf2image import convert_from_bytes

# ❌ REMOVE Windows-only paths
# pytesseract.pytesseract.tesseract_cmd = ...
# POPPLER_PATH = ...

# ===== HELPERS =====
def last_number(line):
    nums = re.findall(r'\d+', line)
    return nums[-1] if nums else "0"

def find_line(lines, keyword):
    if not keyword:
        return ""
    for l in lines:
        if keyword.lower() in l.lower():
            return l
    return ""

def process_text(text, rules):
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    invoice_no = ""
    invoice_date = ""
    party_name = ""
    party_gstin = ""

    for l in lines:
        u = l.upper()

        if "INVOICE" in u and not invoice_no:
            m = re.findall(r'[A-Z0-9\/\-]{4,}', l)
            if m:
                invoice_no = m[-1]

        if "DATE" in u and not invoice_date:
            d = re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{4}', l)
            if d:
                invoice_date = d.group()

        if u.startswith("M/S") or u.startswith("IM/S"):
            clean = re.split(r'INVOICE', l, flags=re.I)[0]
            party_name = clean.replace(":-", " ").replace(":", " ").strip()

        if "GST" in u and not party_gstin:
            g = re.search(r'[0-9A-Z]{15}', l)
            if g:
                party_gstin = g.group()

    taxable_value = last_number(find_line(lines, rules["taxable"]))
    cgst = last_number(find_line(lines, rules.get("cgst", "")))
    sgst = last_number(find_line(lines, rules.get("sgst", "")))
    igst = last_number(find_line(lines, rules.get("igst", "")))
    fuel = last_number(find_line(lines, rules.get("fuel", "")))
    shipment = last_number(find_line(lines, rules.get("shipment", "")))
    invoice_value = last_number(find_line(lines, rules["invoice_total"]))

    return {
        "Invoice No": invoice_no,
        "Invoice Date": invoice_date,
        "Party Name": party_name,
        "Party GSTIN": party_gstin,
        "Taxable Value": taxable_value,
        "CGST": cgst,
        "SGST": sgst,
        "IGST": igst,
        "Fuel Charges": fuel,
        "Shipment Charges": shipment,
        "Invoice Value": invoice_value
    }

def extract_from_bytes(file_bytes: bytes, filename: str, rules):
    rows = []

    if filename.lower().endswith(".pdf"):
        pages = convert_from_bytes(file_bytes)
        for page in pages:
            text = pytesseract.image_to_string(page)
            row = process_text(text, rules)
            if row["Invoice No"] or row["Invoice Value"] != "0":
                rows.append(row)
    else:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        rows.append(process_text(text, rules))

    return rows
