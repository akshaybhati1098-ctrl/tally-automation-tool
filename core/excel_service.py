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
from core.tally_service import fetch_tally_ledgers_with_gstin

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
    df = load_excel_dataframe(file_bytes, sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")

    party_col = detect_party_column(df)
    if not party_col:
        raise ValueError(f"Party column not detected. Available columns: {list(df.columns)}")

    gstin_col = detect_gstin_column(df)

    if ledger_group and ledger_group.lower() not in {"all", "both", "any"}:
        ledgers, gstin_map = fetch_tally_ledgers_with_gstin(group=ledger_group)
    else:
        led1, gst1 = fetch_tally_ledgers_with_gstin("Sundry Debtors")
        led2, gst2 = fetch_tally_ledgers_with_gstin("Sundry Creditors")
        ledgers = list(dict.fromkeys(led1 + led2))
        gstin_map = {**gst1, **gst2}

    match_results = match_party_names(
        df=df,
        tally_ledgers=ledgers,
        tally_gstin_map=gstin_map,
        party_col=party_col,
        gstin_col=gstin_col,
    )

    reviewed_df = apply_match_results_to_dataframe(
        df=df,
        match_results=match_results,
        party_col=party_col,
    )

    unmatched_rows = get_unmatched_rows(match_results)

    return {
        "dataframe": reviewed_df,
        "match_results": match_results,
        "party_col": party_col,
        "gstin_col": gstin_col,
        "ledger_list": ledgers,
        "gstin_map": gstin_map,
        "unmatched_rows": unmatched_rows,
    }


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
        gstin_col = detect_gstin_column(df)

        if party_col:
            led1, gst1 = fetch_tally_ledgers_with_gstin("Sundry Debtors")
            led2, gst2 = fetch_tally_ledgers_with_gstin("Sundry Creditors")

            all_ledgers = list(dict.fromkeys(led1 + led2))
            gst_map = {**gst1, **gst2}

            match_results = match_party_names(
                df=df,
                tally_ledgers=all_ledgers,
                tally_gstin_map=gst_map,
                party_col=party_col,
                gstin_col=gstin_col,
            )

            # ✅ APPLY CORRECTIONS (FINAL FIX)
            corrected = {
                int(k): v
                for k, v in (tally_corrections or {}).items()
                if str(v).strip()
            }

            # ================================
            # ✅ STEP 1: APPLY AUTO MATCH FIRST
            # ================================
            for m in match_results:
                row_index = m["row_index"]

                if row_index not in df.index:
                    continue

                if m.get("status") == "matched":
                    matched_value = (
                        m.get("matched")
                        or m.get("suggested")
                        or m.get("final")
                    )

                    if matched_value:
                        df.at[row_index, party_col] = matched_value

            # ================================
            # ✅ STEP 2: APPLY MANUAL OVERRIDE
            # ================================
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