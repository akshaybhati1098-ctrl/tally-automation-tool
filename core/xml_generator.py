"""
services/xml_generator.py

Core business logic: converts an Excel worksheet of Party Name / GSTIN
rows into a Tally-compatible "Ledger Master" import XML.

The XML-building logic below is carried over unchanged from the
original standalone script - only the surrounding I/O (file picking,
console input, hard-coded output name) has been removed and replaced
with plain function arguments so it can be driven by the GUI.

This module has no Qt dependency, so it can be reused from a CLI,
tests, or a different UI layer later.
"""
import io
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd

from core.convert_menu import clean_text, state_from_gstin

GST_APPLICABLE_FROM = date.today().strftime("%d-%m-%Y")


def get_state_from_gstin(gstin: str) -> str:
    return state_from_gstin(gstin)


class XMLGenerationError(Exception):
    """Raised when XML generation or validation fails."""
    pass


def read_sheet(excel_file: str, sheet_name: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        df.columns = [str(col).strip() for col in df.columns]
        return df.fillna("")
    except Exception as exc:
        raise XMLGenerationError(
            f"Failed to read Excel sheet '{sheet_name}': {exc}"
        ) from exc


def validate_columns(df: pd.DataFrame) -> None:
    required = ["Party Name", "GSTIN"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise XMLGenerationError(
            f"Missing required columns: {', '.join(missing)}"
        )


def _build_envelope(df, parent_group: str) -> ET.Element:
    """Build the <ENVELOPE> XML tree for the given rows.

    This is the same structure produced by the original script:
    ENVELOPE > BODY > IMPORTDATA > REQUESTDATA > TALLYMESSAGE > LEDGER
    """
    envelope = ET.Element("ENVELOPE")

    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import"

    body = ET.SubElement(envelope, "BODY")
    data = ET.SubElement(body, "IMPORTDATA")

    requestdesc = ET.SubElement(data, "REQUESTDESC")
    ET.SubElement(requestdesc, "REPORTNAME").text = "All Masters"

    requestdata = ET.SubElement(data, "REQUESTDATA")

    for _, row in df.iterrows():
        name = str(row["Party Name"]).strip()
        gstin = str(row["GSTIN"]).strip().upper()

        state = get_state_from_gstin(gstin)

        tallymessage = ET.SubElement(requestdata, "TALLYMESSAGE")

        ledger = ET.SubElement(
            tallymessage,
            "LEDGER",
            NAME=name,
            ACTION="Create",
        )

        ET.SubElement(ledger, "NAME").text = name
        ET.SubElement(ledger, "PARENT").text = parent_group

        # GST Details
        gst = ET.SubElement(ledger, "LEDGSTREGDETAILS.LIST")
        ET.SubElement(gst, "APPLICABLEFROM").text = GST_APPLICABLE_FROM
        ET.SubElement(gst, "GSTREGISTRATIONTYPE").text = "Regular"
        ET.SubElement(gst, "STATE").text = state
        ET.SubElement(gst, "PLACEOFSUPPLY").text = state
        ET.SubElement(gst, "GSTIN").text = gstin
        ET.SubElement(gst, "ISOTHTERRITORYASSESSEE").text = "No"
        ET.SubElement(gst, "CONSIDERPURCHASEFOREXPORT").text = "No"
        ET.SubElement(gst, "ISTRANSPORTER").text = "No"
        ET.SubElement(gst, "ISCOMMONPARTY").text = "No"

        # Mailing Details
        mail = ET.SubElement(ledger, "LEDMAILINGDETAILS.LIST")
        ET.SubElement(mail, "APPLICABLEFROM").text = GST_APPLICABLE_FROM
        ET.SubElement(mail, "MAILINGNAME").text = name
        ET.SubElement(mail, "STATE").text = state
        ET.SubElement(mail, "COUNTRY").text = "India"

    return envelope


def generate_xml(
    excel_file: str,
    sheet_name: str,
    parent_group: str,
    output_xml: str,
    progress_callback=None,
) -> dict:
    """
    Generate a Tally Ledger Master XML file from an Excel worksheet.

    Parameters
    ----------
    excel_file : str
        Path to the source .xlsx / .xls file.
    sheet_name : str
        Worksheet to read.
    parent_group : str
        "Sundry Debtors" or "Sundry Creditors".
    output_xml : str
        Path to write the resulting XML file to.
    progress_callback : callable(str), optional
        Called with short status messages ("Reading Excel...",
        "Generating XML...", etc.) so a caller (e.g. the GUI) can
        display progress.

    Returns
    -------
    dict
        {"success": True, "rows_processed": int, "output_file": str}

    Raises
    ------
    ExcelReadError
        If the file/sheet cannot be read.
    MissingColumnsError
        If "Party Name" or "GSTIN" columns are missing.
    XMLGenerationError
        If the sheet has no data rows, or the XML cannot be written
        (including permission errors).
    """

    def _notify(message: str):
        if progress_callback:
            progress_callback(message)

    _notify("Reading Excel...")
    df = read_sheet(excel_file, sheet_name)
    validate_columns(df)

    if df.empty:
        raise XMLGenerationError("The selected worksheet contains no data rows.")

    _notify("Generating XML...")
    envelope = _build_envelope(df, parent_group)

    try:
        tree = ET.ElementTree(envelope)
        tree.write(output_xml, encoding="utf-8", xml_declaration=True)
    except PermissionError as exc:
        raise XMLGenerationError(
            f"Permission denied while writing to:\n{output_xml}\n\n"
            "Close the file if it is open elsewhere (e.g. in Tally or "
            "another program) and try again."
        ) from exc
    except Exception as exc:
        raise XMLGenerationError(f"Failed to write XML file:\n{exc}") from exc

    _notify("XML Generated Successfully")

    return {
        "success": True,
        "rows_processed": int(len(df)),
        "output_file": output_xml,
    }
def generate_xml_bytes(
    df,
    parent_group: str,
    progress_callback=None,
):
    """
    Generate Tally Ledger XML directly from a DataFrame.

    Returns:
        bytes
    """

    def _notify(message):
        if progress_callback:
            progress_callback(message)

    validate_columns(df)

    if df.empty:
        raise XMLGenerationError(
            "No missing ledgers found."
        )

    _notify("Generating XML...")

    envelope = _build_envelope(
        df,
        parent_group
    )

    try:

        buffer = io.BytesIO()

        tree = ET.ElementTree(envelope)

        tree.write(
            buffer,
            encoding="utf-8",
            xml_declaration=True
        )

        _notify("Completed")

        return buffer.getvalue()

    except Exception as exc:

        raise XMLGenerationError(
            f"Failed to generate XML.\n{exc}"
        ) from exc
