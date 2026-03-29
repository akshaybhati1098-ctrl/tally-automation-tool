# core/match_service.py
from __future__ import annotations

import re
from typing import Dict, List, Optional

import pandas as pd
from rapidfuzz import fuzz, process

MATCHED_THRESHOLD = 80
REVIEW_THRESHOLD = 50

REMOVE_WORDS = [
    "pvt ltd",
    "private limited",
    "private ltd",
    "ltd",
    "limited",
    "traders",
    "trading",
    "enterprise",
    "enterprises",
    "company",
    "co",
    "india",
    "llp",
    "inc",
]


def normalize_text(value) -> str:
    text = "" if value is None else str(value)
    text = text.lower().strip()
    for word in REMOVE_WORDS:
        text = text.replace(word, " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_gstin(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).strip().upper())


def detect_party_column(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return None

    keywords = [
        "party",
        "party name",
        "name",
        "recipient name",
        "customer",
        "vendor",
        "ledger",
        "account",
        "supplier",
        "buyer",
    ]

    columns = list(df.columns)
    for col in columns:
        low = str(col).lower().strip()
        for kw in keywords:
            if kw == low or kw in low:
                return col
    return None


def detect_gstin_column(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return None

    keywords = ["gstin", "gst no", "gst number", "gstin no", "gst"]
    columns = list(df.columns)
    for col in columns:
        low = str(col).lower().strip()
        for kw in keywords:
            if kw == low or kw in low:
                return col
    return None


def _build_ledger_lookup(ledger_names: List[str]):
    cleaned_to_original: Dict[str, str] = {}
    cleaned_names: List[str] = []

    for ledger in ledger_names:
        cleaned = normalize_text(ledger)
        if cleaned and cleaned not in cleaned_to_original:
            cleaned_to_original[cleaned] = ledger
            cleaned_names.append(cleaned)

    return cleaned_names, cleaned_to_original


def match_party_names(
    df: pd.DataFrame,
    tally_ledgers: List[str],
    tally_gstin_map: Optional[Dict[str, str]] = None,
    party_col: Optional[str] = None,
    gstin_col: Optional[str] = None,
) -> List[dict]:
    if df is None:
        raise ValueError("DataFrame is required")

    if party_col is None:
        party_col = detect_party_column(df)
    if not party_col:
        raise ValueError("Could not detect party column")

    tally_gstin_map = tally_gstin_map or {}
    cleaned_ledger_names, cleaned_lookup = _build_ledger_lookup(tally_ledgers)

    results: List[dict] = []

    for idx, row in df.iterrows():
        original_party = row.get(party_col, "")
        original_party_text = "" if pd.isna(original_party) else str(original_party).strip()

        original_gstin = ""
        if gstin_col and gstin_col in df.columns:
            gstin_value = row.get(gstin_col, "")
            original_gstin = normalize_gstin("" if pd.isna(gstin_value) else gstin_value)

        best_match = ""
        best_score = 0
        match_by = "None"

        if original_gstin and original_gstin in tally_gstin_map:
            best_match = tally_gstin_map[original_gstin]
            best_score = 100
            match_by = "GSTIN"
        else:
            cleaned_party = normalize_text(original_party_text)
            if cleaned_party and cleaned_ledger_names:
                extracted = process.extractOne(
                    cleaned_party,
                    cleaned_ledger_names,
                    scorer=fuzz.token_sort_ratio,
                )
                if extracted:
                    matched_cleaned, score, _ = extracted
                    best_match = cleaned_lookup.get(matched_cleaned, "")
                    best_score = int(score)
                    match_by = "Name"

        if best_score > MATCHED_THRESHOLD:
            status = "matched"
        elif REVIEW_THRESHOLD <= best_score <= MATCHED_THRESHOLD:
            status = "review"
        else:
            status = "not_matched"

        results.append(
            {
                "row_index": int(idx),
                "original": original_party_text,
                "matched": best_match,
                "score": best_score,
                "status": status,
                "match_by": match_by,
                "gstin": original_gstin,
            }
        )

    return results


def apply_match_results_to_dataframe(
    df: pd.DataFrame,
    match_results: List[dict],
    party_col: Optional[str] = None,
) -> pd.DataFrame:
    if df is None:
        raise ValueError("DataFrame is required")

    output = df.copy()

    if party_col is None:
        party_col = detect_party_column(output)
    if not party_col:
        raise ValueError("Could not detect party column")

    if "Original Party Name" not in output.columns:
        output["Original Party Name"] = output[party_col].astype(str)
    if "Suggested Match" not in output.columns:
        output["Suggested Match"] = ""
    if "Match Score" not in output.columns:
        output["Match Score"] = 0
    if "Match Status" not in output.columns:
        output["Match Status"] = ""
    if "Match By" not in output.columns:
        output["Match By"] = ""
    if "Final Party Name" not in output.columns:
        output["Final Party Name"] = output[party_col].astype(str)

    for item in match_results:
        idx = item["row_index"]
        if idx not in output.index:
            continue

        output.at[idx, "Suggested Match"] = item.get("matched", "")
        output.at[idx, "Match Score"] = item.get("score", 0)
        output.at[idx, "Match Status"] = item.get("status", "")
        output.at[idx, "Match By"] = item.get("match_by", "")

        if item.get("status") == "matched" and item.get("matched"):
            output.at[idx, "Final Party Name"] = item["matched"]
        else:
            output.at[idx, "Final Party Name"] = output.at[idx, party_col]

    return output


def apply_manual_corrections(
    df: pd.DataFrame,
    corrections: Dict[int, str],
    party_col: Optional[str] = None,
) -> pd.DataFrame:
    if df is None:
        raise ValueError("DataFrame is required")

    output = df.copy()

    if party_col is None:
        party_col = detect_party_column(output)
    if not party_col:
        raise ValueError("Could not detect party column")

    if "Final Party Name" not in output.columns:
        output["Final Party Name"] = output[party_col].astype(str)

    for row_index, selected_ledger in corrections.items():
        if row_index in output.index and selected_ledger:
            output.at[row_index, "Final Party Name"] = str(selected_ledger).strip()

    return output


def get_unmatched_rows(match_results: List[dict]) -> List[dict]:
    return [item for item in match_results if item.get("status") != "matched"]