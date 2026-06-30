# core/excel_service.py
from __future__ import annotations

import io
import json
import shutil
import tempfile
from io import BytesIO
from typing import Dict, Optional

import pandas as pd

from core import convert_menu
from core.mapping import get_company_mapping
from core.match_service import (
    apply_manual_corrections,
    apply_match_results_to_dataframe,
    detect_gstin_column,
    detect_party_column,
    get_unmatched_rows,
    match_party_names,
)
from core.tally_service import parse_ledgers_with_gstin

CANONICAL_COLUMNS = {
    "invoice_number": "Invoice Number",
    "invoice_date": "Invoice date",
    "party_name": "Recipient Name",
    "taxable_value": "Taxable Value",
    "cgst": "CGST",
    "sgst": "SGST",
    "igst": "IGST",
    "invoice_value": "Invoice Value",
    "gstin": "GSTIN",
}


def load_excel_dataframe(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    excel_buffer = io.BytesIO(file_bytes)
    return pd.read_excel(excel_buffer, sheet_name=sheet_name)


def export_dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reviewed Match")
    output.seek(0)
    return output.read()


def prepare_excel_party_matching(
    file_bytes: bytes,
    sheet_name: str,
    ledger_group: Optional[str] = None,
) -> dict:
    """
    NOTE: Legacy helper.

    Party matching is now performed via the `/api/match-party` endpoint using the
    connector → Tally flow. This helper previously relied on direct Tally fetch
    helpers that no longer exist in this codebase.
    """
    df = load_excel_dataframe(file_bytes, sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")

    party_col = detect_party_column(df)
    if not party_col:
        raise ValueError(f"Party column not detected. Available columns: {list(df.columns)}")

    gstin_col = detect_gstin_column(df)

    raise NotImplementedError(
        "prepare_excel_party_matching() is deprecated. Use /api/match-party instead."
    )


def apply_corrections_and_build_final_df(
    reviewed_df: pd.DataFrame,
    corrections: Dict[int, str],
    party_col: Optional[str] = None,
) -> pd.DataFrame:
    return apply_manual_corrections(
        df=reviewed_df,
        corrections=corrections,
        party_col=party_col,
    )


def dataframe_to_xml(
    df: pd.DataFrame,
    voucher_type: str,
    company: str,
    user_id: int,
    column_mapping: dict = None,
    tally_corrections: dict = None,
):
    """
    Converts an already matching-reviewed pandas DataFrame directly into Tally XML format.
    This bypasses raw file reading to preserve corrections applied during matching screen operations.
    """
    print("🔥 INSIDE DATAFRAME XML FUNCTION. Corrections received:", tally_corrections)

    # Ensure clean columns and drop empty string null records 
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")

    # Identify active party column target
    party_col = detect_party_column(df) or "Recipient Name"

    # Apply any extra late-stage manual corrections passed directly via form parameters
    if tally_corrections:
        for k, v in tally_corrections.items():
            if str(v).strip():
                try:
                    idx_int = int(k)
                    if idx_int in df.index:
                        df.at[idx_int, party_col] = str(v).strip()
                    elif idx_int >= 0 and idx_int < len(df):
                        df.iloc[idx_int, df.columns.get_loc(party_col)] = str(v).strip()
                except (ValueError, IndexError):
                    continue

    # ════════════════════════════════════════════════════════════
    # CRITICAL FIX: Prevent uncorrected original columns from clobbering reviewed data
    # ════════════════════════════════════════════════════════════
    if column_mapping and "party_name" in column_mapping:
        orig_party_col = str(column_mapping["party_name"]).strip()
        # If the matched data lives in "Recipient Name", synchronize it back to the original mapped column
        if "Recipient Name" in df.columns and orig_party_col in df.columns and orig_party_col != "Recipient Name":
            df[orig_party_col] = df["Recipient Name"]

    # ✅ APPLY COLUMN MAPPING FOR THE TEMPLATE ENGINE
    if column_mapping:
        rename_map = {}
        for field_key, source_col in column_mapping.items():
            canonical = CANONICAL_COLUMNS.get(field_key)
            if canonical and source_col and source_col in df.columns:
                rename_map[source_col] = canonical
        if rename_map:
            df = df.rename(columns=rename_map)

    # Re-verify post-rename to ensure template matches target variables
    final_party_col = CANONICAL_COLUMNS.get("party_name", "Recipient Name")
    print("✅ FINAL RUNTIME CHECK FOR XML PARTY COLUMN:")
    if final_party_col in df.columns:
        print(df[[final_party_col]].head(10))

    mapping = get_company_mapping(company, user_id)
    out_dir = tempfile.mkdtemp()

    try:
        xml_path, record_count = convert_menu.convert_excel_to_xml(
            vtype=voucher_type,
            df=df,
            out_dir=out_dir,
            mapping=mapping,
        )
        with open(xml_path, "r", encoding="utf-8") as f:
            xml_content = f.read()
        return xml_content, record_count
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def excel_to_xml(
    file_bytes: bytes,
    sheet_name: str,
    vtype: str,
    company: str,
    user_id: int,
    column_mapping: dict = None,
    tally_corrections: dict = None,
):
    excel_buffer = io.BytesIO(file_bytes)
    df = pd.read_excel(excel_buffer, sheet_name=sheet_name)
    print("🔥 INSIDE XML FUNCTION:", tally_corrections)

    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")

    # ✅ APPLY COLUMN MAPPING
    if column_mapping:
        rename_map = {}
        for field_key, source_col in column_mapping.items():
            canonical = CANONICAL_COLUMNS.get(field_key)
            if canonical and source_col and source_col in df.columns:
                rename_map[source_col] = canonical
        if rename_map:
            df = df.rename(columns=rename_map)

    try:
        party_col = detect_party_column(df)

        if party_col:
            # ✅ APPLY CORRECTIONS (FINAL FIX)
            corrected = {
                int(k): v
                for k, v in (tally_corrections or {}).items()
                if str(v).strip()
            }

            # Apply manual overrides from UI (match-party step).
            for idx, value in corrected.items():
                if idx in df.index:
                    df.at[idx, party_col] = value

            # 🔍 DEBUG
            print("✅ FINAL CORRECTED DF:")
            print(df[[party_col]].head(10))

    except Exception as e:
        print(f"⚠️ Tally Matching Skipped: {e}")

    mapping = get_company_mapping(company, user_id)
    out_dir = tempfile.mkdtemp()

    try:
        xml_path, record_count = convert_menu.convert_excel_to_xml(
            vtype=vtype,
            df=df,
            out_dir=out_dir,
            mapping=mapping,
        )
        with open(xml_path, "r", encoding="utf-8") as f:
            xml_content = f.read()
        return xml_content, record_count
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)