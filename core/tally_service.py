# core/tally_service.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple


# ================================
# 🔧 CLEAN XML RESPONSE
# ================================
def _clean_xml_text(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.replace("\x00", "")
    raw = re.sub(r"&#\d+;", "", raw)
    return raw.strip()


# ================================
# 🔧 PARSE XML SAFELY
# ================================
def _parse_xml(raw_text: str) -> ET.Element:
    cleaned = _clean_xml_text(raw_text)

    if not cleaned:
        raise ValueError("Empty response from Tally")

    try:
        return ET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML response from Tally: {exc}") from exc


# ================================
# 📡 XML BUILDERS (SEND TO CONNECTOR)
# ================================

def build_company_status_xml() -> str:
    return """
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


def build_ledger_xml(group: Optional[str] = None) -> str:
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


# ================================
# 📊 PARSERS (FROM CONNECTOR RESULT)
# ================================

def parse_company_status(raw_xml: str) -> dict:
    try:
        root = _parse_xml(raw_xml)

        company_name = None
        for path in (".//COMPANYNAME", ".//LASTCOMPANYNAME", ".//NAME", ".//COMPANY"):
            node = root.find(path)
            if node is not None and node.text and node.text.strip():
                company_name = node.text.strip()
                break

        return {"status": "running", "company": company_name}

    except Exception:
        return {"status": "not_running", "company": None}


def parse_ledgers(raw_xml: str) -> List[str]:
    root = _parse_xml(raw_xml)

    names: List[str] = []

    for ledger in root.findall(".//LEDGER"):
        name = (
            ledger.attrib.get("NAME")
            or ledger.findtext("NAME")
            or ledger.findtext(".//NAME")
        )

        if name:
            name = name.strip()
            if name:
                names.append(name)

    # remove duplicates
    return list(dict.fromkeys(names))


def parse_ledgers_with_gstin(raw_xml: str) -> Tuple[List[str], Dict[str, str]]:
    root = _parse_xml(raw_xml)

    names: List[str] = []
    gstin_map: Dict[str, str] = {}

    for ledger in root.findall(".//LEDGER"):
        name = (
            ledger.attrib.get("NAME")
            or ledger.findtext("NAME")
            or ledger.findtext(".//NAME")
        )

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

    return list(dict.fromkeys(names)), gstin_map