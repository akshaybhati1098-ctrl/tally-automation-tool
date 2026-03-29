import os
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom

MISSING_LEDGER_NAME = "__RATE_NOT_MAPPED__"
def tally_date(d):
    try:
        import pandas as pd
        dt = pd.to_datetime(d, dayfirst=True, errors="coerce")
        if pd.isna(dt):
            return ""
        return dt.strftime("%Y%m%d")
    except:
        return ""

GST_STATE = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli",
    "27": "Maharashtra",
    "28": "Goa",
    "29": "Karnataka",
    "30": "Andaman and Nicobar Islands",
    "31": "Lakshadweep",
    "32": "Delhi",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Kerala",
    "36": "Telangana",
    "37": "Andhra Pradesh"
}
def state_from_gstin(gstin):
    gstin = clean_text(gstin)
    return GST_STATE.get(gstin[:2], "")

# ---------------- HELPER ----------------
def is_interstate(gstin, company_state="Uttar Pradesh"):
    state = state_from_gstin(gstin)
    print("👉 GSTIN:", gstin, "| STATE:", state, "| COMPANY:", company_state)
    if not state:
        return False
    return state.strip().lower() != company_state.strip().lower()
def is_already_normalized(mapping):
    return (
        "SALES" in mapping or
        "PURCHASE" in mapping or
        "CGST_RATES" in mapping
    )
# ---------------- BASIC HELPERS ----------------

def num(x):
    try:
        return round(float(str(x).replace(",", "").strip()), 2)
    except:
        return 0.0


def clean_text(x):
    return "" if x is None else str(x).strip()


def normalize_rate_key(k):
    try:
        return str(int(round(float(str(k).replace("%", "").strip()))))
    except:
        return "0"


def first_non_empty(row, *keys):
    for k in keys:
        if str(row.get(k, "")).strip():
            return row.get(k)
    return ""


def add_entry(v, ledger, positive, amt):
    e = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(e, "LEDGERNAME").text = str(ledger).strip()
    ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if positive else "No"
    ET.SubElement(e, "AMOUNT").text = f"{(-amt if positive else amt):.2f}"


# ---------------- MAIN FUNCTION ----------------

def convert_excel_to_xml(vtype, df, out_dir, mapping):

    print("\n================= START CONVERSION =================")

    # ✅ SMART MAPPING
    if not is_already_normalized(mapping):
        print("⚙️ Mapping not normalized → normalizing...")
        mapping = normalize_mapping(mapping)

    print("📦 FINAL MAPPING KEYS:", list(mapping.keys()))

    SALES = mapping.get("SALES", {})
    SALES_INTER = mapping.get("SALES_INTER", {})
    PURCHASE = mapping.get("PURCHASE", {})
    PURCHASE_INTER = mapping.get("PURCHASE_INTER", {})

    CGST_SALES = mapping.get("CGST_SALES") or mapping.get("CGST_RATES", {})
    SGST_SALES = mapping.get("SGST_SALES") or mapping.get("SGST_RATES", {})
    IGST_SALES = mapping.get("IGST_SALES") or mapping.get("IGST_RATES", {})

    CGST_PURCHASE = mapping.get("CGST_PURCHASE") or mapping.get("CGST_RATES", {})
    SGST_PURCHASE = mapping.get("SGST_PURCHASE") or mapping.get("SGST_RATES", {})
    IGST_PURCHASE = mapping.get("IGST_PURCHASE") or mapping.get("IGST_RATES", {})

    COMPANY_STATE = mapping.get("COMPANY_STATE") or "Uttar Pradesh"
    print("🏢 COMPANY STATE:", COMPANY_STATE)

    ENV = ET.Element("ENVELOPE")

    HDR = ET.SubElement(ENV, "HEADER")
    ET.SubElement(HDR, "TALLYREQUEST").text = "Import Data"

    BODY = ET.SubElement(ENV, "BODY")
    IMP = ET.SubElement(BODY, "IMPORTDATA")
    REQ = ET.SubElement(IMP, "REQUESTDATA")

    record_count = 0

    for i, row in df.iterrows():

        print("\n================= ROW", i, "=================")

        record_count += 1

        taxable = num(first_non_empty(row, "Taxable Value", "Taxable"))
        cgst = num(first_non_empty(row, "CGST", "CGST Amount"))
        sgst = num(first_non_empty(row, "SGST", "SGST Amount"))
        igst = num(first_non_empty(row, "IGST", "IGST Amount"))

        print("💰 TAXABLE:", taxable)
        print("💰 CGST:", cgst, "| SGST:", sgst, "| IGST:", igst)

        invoice_no = clean_text(first_non_empty(row, "Invoice Number"))
        invoice_date = first_non_empty(row, "Invoice date", "Date")
        invoice_value = num(first_non_empty(row, "Invoice Value", "Total"))

        print("🧾 INVOICE:", invoice_no, "| DATE:", invoice_date, "| VALUE:", invoice_value)

        calc_total = taxable + cgst + sgst + igst
        voucher_total = calc_total if abs(invoice_value - calc_total) <= 10 else invoice_value

        print("📊 CALC TOTAL:", calc_total, "| FINAL:", voucher_total)

        full_rate = 0 if taxable == 0 else round((cgst + sgst + igst) / taxable * 100, 2)

        # Sales / Purchase key
        rk = str(int(round(full_rate)))

        # CGST / SGST key (HALF)
        half_rate = round(full_rate / 2, 2)

        # convert to clean string like "9", "2.5"
        rk_half = str(half_rate).rstrip("0").rstrip(".")

        print("📌 RATE:", full_rate, "| RK:", rk, "| HALF:", rk_half)

        gstin = clean_text(first_non_empty(row, "GSTIN"))
        party_state = state_from_gstin(gstin) or COMPANY_STATE
        interstate = is_interstate(gstin, COMPANY_STATE)

        print("🌍 PARTY STATE:", party_state)
        print("🚚 INTERSTATE:", interstate)

        msg = ET.SubElement(REQ, "TALLYMESSAGE")
        V = ET.SubElement(msg, "VOUCHER",
                          VCHTYPE=("Sales" if vtype == "sale" else "Purchase"),
                          ACTION="Create")
        
        if vtype == "sale":
           ET.SubElement(V, "ISINVOICE").text = "Yes"
           ET.SubElement(V, "USEFORGOODS").text = "No"
           ET.SubElement(V, "PERSISTEDVIEW").text = "Accounting Voucher View"

        date_str = tally_date(invoice_date)
        if date_str:
            ET.SubElement(V, "DATE").text = date_str

        ET.SubElement(V, "VOUCHERTYPENAME").text = "Sales" if vtype == "sale" else "Purchase"


        party = clean_text(first_non_empty(row, "Recipient Name", "Party"))

        print("👤 PARTY:", party)

        # ================= SALES =================
        if vtype == "sale":

            if interstate:
                sales_ledger = SALES_INTER.get(rk)
                igst_ledger = IGST_SALES.get(rk)
                cgst_ledger = None
                sgst_ledger = None
                print("📦 SALES TYPE: INTERSTATE")
            else:
                sales_ledger = SALES.get(rk)
                cgst_ledger = CGST_SALES.get(rk_half)
                sgst_ledger = SGST_SALES.get(rk_half)
                igst_ledger = None
                print("📦 SALES TYPE: LOCAL")

            print("📘 SALES LEDGER:", sales_ledger)
            print("📘 CGST LEDGER:", cgst_ledger)
            print("📘 SGST LEDGER:", sgst_ledger)
            print("📘 IGST LEDGER:", igst_ledger)

            ET.SubElement(V, "PARTYLEDGERNAME").text = party
            ET.SubElement(V, "VOUCHERNUMBER").text = invoice_no
            ET.SubElement(V, "STATENAME").text = party_state
            ET.SubElement(V, "COUNTRYNAME").text = "India"
            ET.SubElement(V, "PLACEOFSUPPLY").text = party_state

            if gstin:
               ET.SubElement(V, "PARTYGSTIN").text = gstin
               ET.SubElement(V, "GSTREGISTRATIONTYPE").text = "Regular"
            else:
               ET.SubElement(V, "GSTREGISTRATIONTYPE").text = "Unregistered/Consumer"

            # Consignee (same as party)
            ET.SubElement(V, "CONSIGNEENAME").text = party
            ET.SubElement(V, "CONSIGNEESTATENAME").text = party_state

            if gstin:
                ET.SubElement(V, "CONSIGNEEGSTIN").text = gstin

            add_entry(V, party, True, voucher_total)

            if sales_ledger:
                add_entry(V, sales_ledger, False, taxable)

            if cgst_ledger and cgst:
                add_entry(V, cgst_ledger, False, cgst)

            if sgst_ledger and sgst:
                add_entry(V, sgst_ledger, False, sgst)

            if igst_ledger and igst:
                add_entry(V, igst_ledger, False, igst)

        # ================= PURCHASE =================
        else:

            if interstate:
                purchase_ledger = PURCHASE_INTER.get(rk)
                igst_ledger = IGST_PURCHASE.get(rk)
                cgst_ledger = None
                sgst_ledger = None
                print("📦 PURCHASE TYPE: INTERSTATE")
            else:
                purchase_ledger = PURCHASE.get(rk)
                cgst_ledger = CGST_PURCHASE.get(rk_half)
                sgst_ledger = SGST_PURCHASE.get(rk_half)
                igst_ledger = None
                print("📦 PURCHASE TYPE: LOCAL")

            print("📘 PURCHASE LEDGER:", purchase_ledger)
            print("📘 CGST LEDGER:", cgst_ledger)
            print("📘 SGST LEDGER:", sgst_ledger)
            print("📘 IGST LEDGER:", igst_ledger)

            ET.SubElement(V, "PARTYLEDGERNAME").text = party
            ET.SubElement(V, "REFERENCE").text = invoice_no
            ET.SubElement(V, "STATENAME").text = party_state
            ET.SubElement(V, "COUNTRYNAME").text = "India"
            ET.SubElement(V, "PLACEOFSUPPLY").text = party_state

            if gstin:
                ET.SubElement(V, "PARTYGSTIN").text = gstin
                ET.SubElement(V, "GSTREGISTRATIONTYPE").text = "Regular"
            else:
               ET.SubElement(V, "GSTREGISTRATIONTYPE").text = "Unregistered/Consumer"

            # ✅ Consignee same as Buyer
            ET.SubElement(V, "CONSIGNEENAME").text = party
            ET.SubElement(V, "CONSIGNEESTATENAME").text = party_state

            if gstin:
                ET.SubElement(V, "CONSIGNEEGSTIN").text = gstin

            add_entry(V, party, False, voucher_total)

            if purchase_ledger:
                add_entry(V, purchase_ledger, True, taxable)

            if cgst_ledger and cgst:
                add_entry(V, cgst_ledger, True, cgst)

            if sgst_ledger and sgst:
                add_entry(V, sgst_ledger, True, sgst)

            if igst_ledger and igst:
                add_entry(V, igst_ledger, True, igst)

    print("\n✅ TOTAL RECORDS:", record_count)

    # SAVE
    file_name = f"{vtype}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xml"
    xml_path = os.path.join(out_dir, file_name)

    xml_str = minidom.parseString(
        ET.tostring(ENV, encoding="utf-8")
    ).toprettyxml(indent="  ")

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print("📁 FILE SAVED:", xml_path)

    return xml_path, record_count