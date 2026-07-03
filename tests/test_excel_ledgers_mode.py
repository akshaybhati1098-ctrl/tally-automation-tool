import os
import tempfile

import pandas as pd

from core.convert_menu import convert_excel_to_xml


def test_excel_ledgers_mode_uses_excel_columns_for_ledger_names():
    df = pd.DataFrame([
        {
            "Recipient Name": "Test Party",
            "Invoice Number": "INV-1",
            "Invoice date": "01-04-2024",
            "Invoice Value": 118000,
            "Taxable Value": 100000,
            "CGST": 9000,
            "SGST": 9000,
            "IGST": 18000,
            "Sales Ledger": "Excel Sales Ledger",
            "Purchase Ledger": "Excel Purchase Ledger",
            "CGST Ledger": "Excel CGST Ledger",
            "SGST Ledger": "Excel SGST Ledger",
            "IGST Ledger": "Excel IGST Ledger",
        }
    ])

    with tempfile.TemporaryDirectory() as out_dir:
        xml_path, record_count = convert_excel_to_xml(
            vtype="sale",
            df=df,
            out_dir=out_dir,
            mapping={},
            use_excel_ledgers=True,
        )

        assert record_count == 1
        assert os.path.exists(xml_path)

        with open(xml_path, "r", encoding="utf-8") as fh:
            xml_content = fh.read()

        assert "Excel Sales Ledger" in xml_content
        assert "Excel CGST Ledger" in xml_content
        assert "Excel SGST Ledger" in xml_content
        assert "Excel IGST Ledger" in xml_content
        assert "__RATE_NOT_MAPPED__" not in xml_content
