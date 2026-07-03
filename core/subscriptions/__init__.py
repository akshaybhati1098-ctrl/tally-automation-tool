# core/tally_service.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape


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

def build_ledger_xml(group: str = None) -> str:
    """
    Build XML to fetch ledgers using the report 'List of Accounts'.

    This is the most reliable pattern for your Tally setup (matches your demo
    code): filter using STATICVARIABLES->GROUPNAME.
    """

    group_norm = (group or "").strip()
    group_block = (
        # Important: keep group text exactly as provided (same pattern as your demo code).
        # Tally expects the literal group name; escaping can sometimes break the lookup.
        f"<GROUPNAME>{group_norm}</GROUPNAME>"
        if group_norm and group_norm.lower() != "all"
        else ""
    )

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
     {group_block}
    </STATICVARIABLES>
   </REQUESTDESC>
  </EXPORTDATA>
 </BODY>
</ENVELOPE>
""".strip()


def parse_ledgers_with_parent(raw_xml: str) -> List[Dict[str, str]]:
    """
    Parse LEDGER elements and return name + parent group.

    Note: Tally tag names can vary by version; we try multiple common fields.
    """
    root = _parse_xml(raw_xml)

    items: List[Dict[str, str]] = []

    ledgers = root.findall(".//LEDGER")
    if ledgers:
        for ledger in ledgers:
            name = (
                ledger.attrib.get("NAME")
                or ledger.findtext("NAME")
                or ledger.findtext(".//NAME")
                or ledger.findtext("LEDGERNAME")
                or ledger.findtext(".//LEDGERNAME")
            )
            if not name:
                continue
            name = name.strip()
            if not name:
                continue

            parent = (
                ledger.findtext("PARENT")
                or ledger.findtext(".//PARENT")
                or ledger.findtext("PARENTNAME")
                or ledger.findtext(".//PARENTNAME")
                or ledger.findtext("PARENTGROUP")
                or ledger.findtext(".//PARENTGROUP")
                or ledger.findtext("GROUPNAME")
                or ledger.findtext(".//GROUPNAME")
            )
            if parent:
                parent = parent.strip()

            items.append({"name": name, "parent": parent or ""})
    else:
        # Fallback: if no <LEDGER> wrapper exists, we can at least return names.
        ledger_names = [
            (n.text or "").strip()
            for n in root.findall(".//LEDGERNAME")
            if n is not None and (n.text or "").strip()
        ]
        if not ledger_names:
            ledger_names = [
                (n.text or "").strip()
                for n in root.findall(".//NAME")
                if n is not None and (n.text or "").strip()
            ]

        parent_values = [
            (n.text or "").strip()
            for n in root.findall(".//PARENTNAME")
            if n is not None and (n.text or "").strip()
        ]
        if not parent_values:
            parent_values = [
                (n.text or "").strip()
                for n in root.findall(".//PARENT")
                if n is not None and (n.text or "").strip()
            ]
        if not parent_values:
            parent_values = [
                (n.text or "").strip()
                for n in root.findall(".//PARENTGROUP")
                if n is not None and (n.text or "").strip()
            ]
        if not parent_values:
            parent_values = [
                (n.text or "").strip()
                for n in root.findall(".//GROUPNAME")
                if n is not None and (n.text or "").strip()
            ]

        for idx, nm in enumerate(ledger_names):
            parent = parent_values[idx] if idx < len(parent_values) else ""
            items.append({"name": nm, "parent": parent})

    return items


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

    ledgers = root.findall(".//LEDGER")
    if ledgers:
        for ledger in ledgers:
            name = (
                ledger.attrib.get("NAME")
                or ledger.findtext("NAME")
                or ledger.findtext(".//NAME")
                or ledger.findtext("LEDGERNAME")
                or ledger.findtext(".//LEDGERNAME")
            )

            if name:
                name = name.strip()
                if name:
                    names.append(name)
    else:
        # Some Tally collection responses may not wrap each item inside a <LEDGER> node.
        for n in root.findall(".//LEDGERNAME"):
            if n is not None and n.text:
                t = n.text.strip()
                if t:
                    names.append(t)

        # Last-resort fallback: sometimes ledger names are returned under <NAME>
        if not names:
            for n in root.findall(".//NAME"):
                if n is not None and n.text:
                    t = n.text.strip()
                    if t:
                        names.append(t)

    # remove duplicates
    return list(dict.fromkeys(names))


def parse_ledgers_with_gstin(raw_xml: str) -> Tuple[List[str], Dict[str, str]]:
    root = _parse_xml(raw_xml)

    names: List[str] = []
    gstin_map: Dict[str, str] = {}

    ledgers = root.findall(".//LEDGER")
    if ledgers:
        for ledger in ledgers:
            name = (
                ledger.attrib.get("NAME")
                or ledger.findtext("NAME")
                or ledger.findtext(".//NAME")
                or ledger.findtext("LEDGERNAME")
                or ledger.findtext(".//LEDGERNAME")
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
    else:
        # Best-effort fallback if no <LEDGER> wrapper exists:
        ledger_names = [
            (n.text or "").strip()
            for n in root.findall(".//LEDGERNAME")
            if n is not None and (n.text or "").strip()
        ]

        # If LEDGERNAME isn't returned, try the generic <NAME> tag.
        if not ledger_names:
            ledger_names = [
                (n.text or "").strip()
                for n in root.findall(".//NAME")
                if n is not None and (n.text or "").strip()
            ]

        if not ledger_names:
            ledger_names = [
                (n.text or "").strip()
                for n in root.findall(".//NAME")
                if n is not None and (n.text or "").strip()
            ]

        party_gstins = [
            (n.text or "").strip().upper()
            for n in root.findall(".//PARTYGSTIN")
            if n is not None and (n.text or "").strip()
        ]

        # If PARTYGSTIN not available, try GSTIN
        if not party_gstins:
            party_gstins = [
                (n.text or "").strip().upper()
                for n in root.findall(".//GSTIN")
                if n is not None and (n.text or "").strip()
            ]

        for idx, nm in enumerate(ledger_names):
            names.append(nm)
            if idx < len(party_gstins):
                g = party_gstins[idx]
                if g and g not in gstin_map:
                    gstin_map[g] = nm

    return list(dict.fromkeys(names)), gstin_map