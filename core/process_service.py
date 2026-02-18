import pandas as pd
from typing import Tuple
from core.company_rules import load_rules
from core.process import extract_from_bytes
import io

def image_to_excel(file_bytes: bytes, original_filename: str, company_key: str) -> Tuple[bytes, str]:
    rules = load_rules().get(company_key)
    if not rules:
        raise ValueError("Invalid company selected")

    rows = extract_from_bytes(file_bytes, original_filename, rules)

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    output_filename = original_filename.replace(".pdf", "").replace(".jpg", "") + ".xlsx"
    return output.read(), output_filename
