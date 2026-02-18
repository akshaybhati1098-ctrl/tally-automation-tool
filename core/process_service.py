import os
import tempfile
import shutil
import pandas as pd
from typing import Tuple
from core import process
from core.company_rules import load_rules

def image_to_excel(file_bytes: bytes, original_filename: str, company_key: str) -> Tuple[bytes, str]:
    """
    Convert uploaded file (PDF/Image) to Excel using process.py with company-specific rules.
    Returns (excel_bytes, output_filename).
    """
    # Load company rules
    all_rules = load_rules()
    if company_key not in all_rules:
        raise ValueError(f"Unknown company key: {company_key}")
    rules = all_rules[company_key]

    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, original_filename)
    output_filename = os.path.splitext(original_filename)[0] + f"_{company_key}.xlsx"
    output_path = os.path.join(temp_dir, output_filename)

    try:
        # Save uploaded file
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        # Extract data using process.py
        rows = process.extract_from_file(input_path, rules)

        # Create DataFrame and save to Excel
        df = pd.DataFrame(rows)
        df.to_excel(output_path, index=False)

        # Read the generated Excel
        with open(output_path, "rb") as f:
            excel_bytes = f.read()

        return excel_bytes, output_filename

    finally:
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)