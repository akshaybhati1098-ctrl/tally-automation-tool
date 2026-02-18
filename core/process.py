import pytesseract
from PIL import Image
import re
import pandas as pd
import os
from pdf2image import convert_from_path

# ===== CONFIGURE PATHS (can be set via environment variables) =====
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
POPPLER_PATH = os.environ.get("POPPLER_PATH", r"C:\poppler\poppler-25.12.0\Library\bin")

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
    """
    Extract data from OCR text using company-specific rules.
    rules: dict with keys taxable, cgst, sgst, igst, fuel, shipment, invoice_total
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    invoice_no = ""
    invoice_date = ""
    party_name = ""
    party_gstin = ""

    for l in lines:
        u = l.upper()

        # Invoice No
        if "INVOICE" in u and not invoice_no:
            m = re.findall(r'[A-Z0-9\/\-]{4,}', l)
            if m:
                invoice_no = m[-1]

        # Date
        if "DATE" in u and not invoice_date:
            d = re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{4}', l)
            if d:
                invoice_date = d.group()

        # Party Name (keep M/S)
        if u.startswith("M/S") or u.startswith("IM/S"):
            clean = re.split(r'INVOICE', l, flags=re.I)[0]
            clean = clean.replace(":-", " ").replace(":", " ")
            party_name = clean.strip()

        # Party GSTIN
        if "GST NO" in u and not party_gstin:
            g = re.search(r'[0-9A-Z]{15}', l)
            if g:
                party_gstin = g.group()

    # ===== COMPANY-WISE AMOUNTS =====
    taxable_value = last_number(find_line(lines, rules["taxable"]))
    cgst = last_number(find_line(lines, rules["cgst"])) if rules.get("cgst") else "0"
    sgst = last_number(find_line(lines, rules["sgst"])) if rules.get("sgst") else "0"
    igst = last_number(find_line(lines, rules["igst"])) if rules.get("igst") else "0"
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

def extract_from_file(file_path, rules):
    """
    Extract data from image/PDF file using given company rules.
    Returns list of dicts (one per page for PDF, one for image).
    """
    rows = []
    if file_path.lower().endswith(".pdf"):
        pages = convert_from_path(file_path, poppler_path=POPPLER_PATH)
        for page in pages:
            text = pytesseract.image_to_string(page)
            row = process_text(text, rules)
            if row["Invoice No"] or row["Invoice Value"] != "0":
                rows.append(row)
    else:
        text = pytesseract.image_to_string(Image.open(file_path))
        rows.append(process_text(text, rules))
    return rows