# core/tally_service.py
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import requests

TALLY_URL = os.getenv("TALLY_URL", "https://untimid-ja-nondefinitively.ngrok-free.dev")
REQUEST_TIMEOUT = float(os.getenv("TALLY_TIMEOUT", "10"))


def _clean_xml_text(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.replace("\x00", "")
    raw = re.sub(r"&#\d+;", "", raw)
    return raw.strip()


def _post_to_tally(xml_request: str, timeout: float = REQUEST_TIMEOUT) -> requests.Response:
    headers = {"Content-Type": "text/xml"}
    response = requests.post(
        TALLY_URL,
        data=xml_request.encode("utf-8"),
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def _parse_xml(raw_text: str) -> ET.Element:
    cleaned = _clean_xml_text(raw_text)
    if not cleaned:
        raise ValueError("Empty response from Tally")
    try:
        return ET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML response from Tally: {exc}") from exc


def get_tally_status() -> dict:
    xml_request = """
    <ENVELOPE>
     <HEADER>
      <VERSION>1</VERSION>
      <TALLYREQUEST>Export</TALLYREQUEST>
      <TYPE>Collection</TYPE>
      <ID>Company Collection</ID>
     </HEADER>
     <BODY>
      <DESC>
       <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
       </STATICVARIABLES>
       <TDL>
        <TDLMESSAGE>
         <COLLECTION NAME="Company Collection">
          <TYPE>Company</TYPE>
          <FETCH>Name</FETCH>
         </COLLECTION>
        </TDLMESSAGE>
       </TDL>
      </DESC>
     </BODY>
    </ENVELOPE>
    """.strip()

    try:
        response = _post_to_tally(xml_request, timeout=5)
        root = _parse_xml(response.text)

        company_name = None
        for path in (".//COMPANYNAME", ".//LASTCOMPANYNAME", ".//NAME", ".//COMPANY"):
            node = root.find(path)
            if node is not None and node.text and node.text.strip():
                company_name = node.text.strip()
                break

        return {"status": "running", "company": company_name}
    except Exception:
        return {"status": "not_running", "company": None}


def _ledger_xml(group: Optional[str] = None) -> str:
    group_xml = f"<GROUPNAME>{group}</GROUPNAME>" if group else ""
    return f"""
    <ENVELOPE>
     <HEADER>
      <TALLYREQUEST>Export Data</TALLYREQUEST>
     </HEADER>
     <BODY>
      <EXPORTDATA>
       <REQUESTDESC>
        <REPORTNAME>List of Accounts</REPORTNAME>
        <STATICVARIABLES>
            <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
            {group_xml}
        </STATICVARIABLES>
       </REQUESTDESC>
      </EXPORTDATA>
     </BODY>
    </ENVELOPE>
    """.strip()


def fetch_tally_ledgers(group: Optional[str] = None) -> List[str]:
    response = _post_to_tally(_ledger_xml(group=group), timeout=15)
    root = _parse_xml(response.text)

    names: List[str] = []
    for ledger in root.findall(".//LEDGER"):
        name = ledger.attrib.get("NAME") or ledger.findtext("NAME") or ledger.findtext(".//NAME")
        if name:
            name = name.strip()
            if name:
                names.append(name)

    seen = set()
    deduped: List[str] = []
    for item in names:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped


def fetch_tally_ledgers_with_gstin(group: Optional[str] = None) -> Tuple[List[str], Dict[str, str]]:
    response = _post_to_tally(_ledger_xml(group=group), timeout=15)
    root = _parse_xml(response.text)

    names: List[str] = []
    gstin_map: Dict[str, str] = {}

    for ledger in root.findall(".//LEDGER"):
        name = ledger.attrib.get("NAME") or ledger.findtext("NAME") or ledger.findtext(".//NAME")
        if not name:
            continue
        name = name.strip()
        if not name:
            continue

        names.append(name)

        gstin = (
            ledger.findtext("PARTYGSTIN")
            or ledger.findtext(".//PARTYGSTIN")
            or ledger.findtext("GSTIN")
            or ledger.findtext(".//GSTIN")
        )
        if gstin:
            gstin = gstin.strip().upper()
            if gstin and gstin not in gstin_map:
                gstin_map[gstin] = name

    seen = set()
    deduped: List[str] = []
    for item in names:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped, gstin_map