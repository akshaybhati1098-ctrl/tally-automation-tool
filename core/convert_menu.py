#!/usr/bin/env python3
"""
STRICT XML GENERATOR (GUI VERSION)
----------------------------------
✔ Works with GUI (NO input, NO menus)
✔ Accepts: (vtype, df, out_dir, mapping)
✔ Strict GST ledger mapping
✔ Auto-adjust invoice ±10
✔ SALE vouchers → Accounting Invoice Mode
✔ PURCHASE vouchers unchanged
✔ Returns: xml_path, record_count
"""

import os, json
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom

MISSING_LEDGER_NAME = "__RATE_NOT_MAPPED__"

GST_STATE = {
 "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
 "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
 "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
 "10": "Bihar", "19": "West Bengal", "24": "Gujarat",
 "27": "Maharashtra", "29": "Karnataka", "33": "Tamil Nadu",
 "36": "Telangana"
}

# ---------------------------- HELPERS ----------------------------

def num(x):
    try:
        return round(float(str(x).replace(",", "").strip()), 2)
    except:
        return 0.0

def tally_date(d):
    try:
        return pd.to_datetime(d, dayfirst=True).strftime("%Y%m%d")
    except:
        return ""

def state_from_gstin(gstin):
    gstin = str(gstin).strip()
    return GST_STATE.get(gstin[:2], "")

def normalize_rate_key(k):
    try:
        return str(int(round(float(str(k).replace("%", "").strip()))))
    except:
        return "0"

def add_entry(v, ledger, positive, amt):
    e = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(e, "LEDGERNAME").text = ledger
    ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if positive else "No"
    ET.SubElement(e, "AMOUNT").text = f"{(-amt if positive else amt):.2f}"

# ---------------------------- MAIN GUI FUNCTION ----------------------------

def convert_excel_to_xml(vtype, df, out_dir, mapping):
    """
    vtype   : 'sale' or 'purchase'
    df      : Pandas DataFrame from GUI
    out_dir : XML output directory
    mapping : Full mapping JSON from GUI
    """

    SALES       = { normalize_rate_key(k):v for k,v in mapping["SALES"].items() }
    SALES_IGST  = { normalize_rate_key(k):v for k,v in mapping["SALES_IGST"].items() }
    PURCHASE    = { normalize_rate_key(k):v for k,v in mapping["PURCHASE"].items() }

    CGST_MAP = { normalize_rate_key(k):v for k,v in mapping["CGST_RATES"].items() }
    SGST_MAP = { normalize_rate_key(k):v for k,v in mapping["SGST_RATES"].items() }
    IGST_MAP = { normalize_rate_key(k):v for k,v in mapping["IGST_RATES"].items() }

    COMPANY_STATE = mapping["COMPANY_STATE"]

    ENV = ET.Element("ENVELOPE")
    HDR = ET.SubElement(ENV, "HEADER")
    ET.SubElement(HDR, "TALLYREQUEST").text = "Import Data"
    BODY = ET.SubElement(ENV, "BODY")
    IMP = ET.SubElement(BODY, "IMPORTDATA")
    REQ = ET.SubElement(IMP, "REQUESTDATA")

    record_count = 0
    exceptions = []

    # ------------------------------------------------------------------
    # PROCESS EVERY ROW
    # ------------------------------------------------------------------
    for _, row in df.iterrows():
        record_count += 1

        taxable = num(row.get("Taxable Value", 0))
        cgst = num(row.get("CGST", 0))
        sgst = num(row.get("SGST", 0))
        igst = num(row.get("IGST", 0))

        invoice_no = str(row.get("Invoice Number", row.get("Invoice No", "")))
        invoice_date = row.get("Invoice Date", "")

        invoice_value = num(row.get("Invoice Value", row.get("Invoice Amount", 0)))
        calc_total = round(taxable + cgst + sgst + igst, 2)
        diff = abs(invoice_value - calc_total)

        # ±10 Adjustment
        voucher_total = calc_total if diff <= 10 else invoice_value

        if diff > 10:
            r = row.copy()
            r["__EXCEPTION__"] = f"Diff {diff}"
            exceptions.append(r)

        # GST RATE
        rate = 0 if taxable == 0 else int(round((cgst + sgst + igst) / taxable * 100))
        rk = normalize_rate_key(rate)

        party_state = state_from_gstin(row.get("GSTIN", "")) or ""
        is_intra = (party_state != "" and party_state == COMPANY_STATE)

        # TAXABLE LEDGER
        if vtype == "sale":
            if igst > 0:
                taxable_ledger = SALES_IGST.get(rk, MISSING_LEDGER_NAME)
                mapped = rk in SALES_IGST
            else:
                taxable_ledger = SALES.get(rk, MISSING_LEDGER_NAME)
                mapped = rk in SALES
        else:
            taxable_ledger = PURCHASE.get(rk, MISSING_LEDGER_NAME)
            mapped = rk in PURCHASE

        if not mapped:
            r = row.copy()
            r["__EXCEPTION__"] = f"Rate {rk}% not mapped"
            exceptions.append(r)

        cgst_led = CGST_MAP.get(rk, MISSING_LEDGER_NAME)
        sgst_led = SGST_MAP.get(rk, MISSING_LEDGER_NAME)
        igst_led = IGST_MAP.get(rk, MISSING_LEDGER_NAME)

        # ------------------------------------------------------------------
        # BUILD VOUCHER
        # ------------------------------------------------------------------
        msg = ET.SubElement(REQ, "TALLYMESSAGE")
        V = ET.SubElement(msg, "VOUCHER",
                          VCHTYPE=("Sales" if vtype=="sale" else "Purchase"),
                          ACTION="Create")

        ET.SubElement(V, "DATE").text = tally_date(invoice_date)
        ET.SubElement(V, "VOUCHERTYPENAME").text = "Sales" if vtype=="sale" else "Purchase"

        # 🔵 ONLY SALE — ACCOUNTING INVOICE MODE
        if vtype == "sale":
            ET.SubElement(V, "USEFORGOODS").text = "No"
            ET.SubElement(V, "ISINVOICE").text = "Yes"

        # PARTY
        if vtype == "purchase":
            party = row.get("Supplier Name", "")
        else:
            party = row.get("Recipient Name", row.get("Party", ""))

        ET.SubElement(V, "PARTYLEDGERNAME").text = party

        # VOUCHER NUMBER / REFERENCE
        if vtype == "purchase":
            ET.SubElement(V, "REFERENCE").text = invoice_no
            ET.SubElement(V, "VOUCHERNUMBER").text = ""
        else:
            ET.SubElement(V, "VOUCHERNUMBER").text = invoice_no

        ET.SubElement(V, "STATENAME").text = party_state
        ET.SubElement(V, "PLACEOFSUPPLY").text = party_state or COMPANY_STATE

        if row.get("GSTIN"):
            ET.SubElement(V, "PARTYGSTIN").text = row["GSTIN"]

        ET.SubElement(V, "CONSIGNEENAME").text = party
        if row.get("GSTIN"):
            ET.SubElement(V, "CONSIGNEEGSTIN").text = row["GSTIN"]
        ET.SubElement(V, "CONSIGNEESTATENAME").text = party_state

        if row.get("Address"):
            ET.SubElement(V, "CONSIGNEEADDRESS").text = row["Address"]

        # ------------------- LEDGER ENTRIES -------------------
        if vtype == "sale":
            add_entry(V, party, True, voucher_total)
            add_entry(V, taxable_ledger, False, taxable)

            if is_intra:
                if cgst: add_entry(V, cgst_led, False, cgst)
                if sgst: add_entry(V, sgst_led, False, sgst)
            else:
                if igst: add_entry(V, igst_led, False, igst)

        else:
            add_entry(V, party, False, voucher_total)
            add_entry(V, taxable_ledger, True, taxable)

            if is_intra:
                if cgst: add_entry(V, cgst_led, True, cgst)
                if sgst: add_entry(V, sgst_led, True, sgst)
            else:
                if igst: add_entry(V, igst_led, True, igst)

    # ------------------- SAVE XML FILE -------------------

    name = f"{vtype}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xml"
    xml_out = os.path.join(out_dir, name)

    xml = minidom.parseString(ET.tostring(ENV)).toprettyxml(indent="  ")
    with open(xml_out, "w", encoding="utf-8") as f:
        f.write(xml)

    return xml_out, record_count