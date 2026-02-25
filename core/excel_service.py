import pandas as pd
import tempfile
import os
import shutil

from core import convert_menu
from core.mapping import get_company_mapping   # new import

def excel_to_xml(file_bytes: bytes, sheet_name: str, vtype: str, company: str = "Default") -> tuple[str, int]:
    """
    Convert Excel data to Tally XML using the mapping of the specified company.
    """
    # 1. Read Excel from bytes
    df = pd.read_excel(file_bytes, sheet_name=sheet_name).fillna("")

    # 2. Load mapping for the selected company
    mapping = get_company_mapping(company)

    # 3. Create temporary output directory
    out_dir = tempfile.mkdtemp()

    try:
        # 4. Call the existing conversion logic
        xml_path, record_count = convert_menu.convert_excel_to_xml(
            vtype=vtype,
            df=df,
            out_dir=out_dir,
            mapping=mapping
        )

        # 5. Read the generated XML
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        return xml_content, record_count
    finally:
        # 6. Clean up temporary files
        shutil.rmtree(out_dir, ignore_errors=True)