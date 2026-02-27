from flask import send_file  # might not be needed but left as is
import io
import csv
from io import BytesIO
from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font

# Existing services
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json   # these will now store the full structure

# Image → Excel service
from core.process_service import image_to_excel

app = FastAPI(title="Tally Automation Tool")

# -------------------------
# Static files & templates
# -------------------------
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# -------------------------
# Helper functions for multi‑company mapping
# -------------------------
def load_full_mapping():
    """Load the full mapping structure (companies + per‑company mappings)."""
    data = load_mapping_json()
    # Migrate old single‑company format
    if "companies" not in data:
        data = {
            "companies": ["Default"],
            "mappings": {"Default": data}
        }
        save_full_mapping(data)
    return data

def save_full_mapping(data):
    """Save the full mapping structure."""
    save_mapping_json(data)

# -------------------------
# UI (single entry point)
# -------------------------
@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# =========================================================
# Excel → XML API (with company selection)
# =========================================================
@app.post("/api/convert")
async def convert_excel_api(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale"),
    company: str = Form("Default")          # new company parameter
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    try:
        file_bytes = await file.read()
        # Pass company to the service so it uses the correct mapping
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype, company)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": (
                    f"attachment; filename="
                    f"{file.filename.rsplit('.', 1)[0]}_output.xml"
                ),
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.error(e)
        raise HTTPException(500, str(e))

# =========================================================
# Image / PDF → Excel API
# =========================================================
@app.post("/api/image-to-excel")
async def image_to_excel_api(
    file: UploadFile,
    company_key: str = Form(...)
):
    if not file.filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
        raise HTTPException(400, "Only PDF or image files allowed")

    try:
        file_bytes = await file.read()

        excel_bytes, output_filename = image_to_excel(
            file_bytes=file_bytes,
            original_filename=file.filename,
            company_key=company_key
        )

        return Response(
            content=excel_bytes,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}"
            }
        )

    except Exception as e:
        logging.error(e)
        raise HTTPException(500, str(e))

# =========================================================
# Company management endpoints
# =========================================================
@app.get("/api/companies")
async def get_companies():
    """Return list of all company names."""
    try:
        full = load_full_mapping()
        return JSONResponse(content={"companies": full.get("companies", [])})
    except Exception as e:
        raise HTTPException(500, f"Failed to load companies: {str(e)}")

@app.post("/api/companies")
async def create_company(name: str = Form(...)):
    """Create a new company with default mapping."""
    try:
        full = load_full_mapping()
        if name in full["companies"]:
            raise HTTPException(400, f"Company '{name}' already exists")
        # Add company with a fresh default mapping
        full["companies"].append(name)
        full["mappings"][name] = {
            "COMPANY_STATE": "Not set",
            "SALES": {},
            "SALES_IGST": {},
            "PURCHASE": {},
            "CGST_RATES": {},
            "SGST_RATES": {},
            "IGST_RATES": {},
            "DEBUG": False
        }
        save_full_mapping(full)
        return {"status": "success", "message": f"Company '{name}' created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create company: {str(e)}")

@app.delete("/api/companies/{company}")
async def remove_company(company: str):
    """Delete a company and its mapping. Cannot delete 'Default'."""
    if company == "Default":
        raise HTTPException(400, "Cannot delete the Default company")
    try:
        full = load_full_mapping()
        if company not in full["companies"]:
            raise HTTPException(404, f"Company '{company}' not found")
        full["companies"].remove(company)
        del full["mappings"][company]
        save_full_mapping(full)
        return {"status": "success", "message": f"Company '{company}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete company: {str(e)}")

# =========================================================
# Rename company
# =========================================================
@app.put("/api/companies/{old_name}")
async def rename_company(old_name: str, new_name: str = Form(...)):
    """Rename an existing company. Cannot rename 'Default'."""
    if old_name == "Default":
        raise HTTPException(400, "Cannot rename the Default company")
    try:
        full = load_full_mapping()
        if old_name not in full["companies"]:
            raise HTTPException(404, f"Company '{old_name}' not found")
        if new_name in full["companies"]:
            raise HTTPException(400, f"Company '{new_name}' already exists")

        # Update the companies list
        idx = full["companies"].index(old_name)
        full["companies"][idx] = new_name

        # Rename the key in the mappings dictionary
        full["mappings"][new_name] = full["mappings"].pop(old_name)

        save_full_mapping(full)
        return {"status": "success", "message": f"Company renamed to '{new_name}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to rename company: {str(e)}")

# =========================================================
# Per‑company mapping endpoints
# =========================================================
@app.get("/api/mapping/{company}")
async def get_company_mapping(company: str):
    """Return mapping for a specific company."""
    try:
        full = load_full_mapping()
        if company not in full["mappings"]:
            raise HTTPException(404, f"Company '{company}' not found")
        return JSONResponse(content=full["mappings"][company])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to load mapping: {str(e)}")

@app.post("/api/mapping/{company}")
async def update_company_mapping(company: str, mapping: dict):
    """Save mapping for a specific company."""
    try:
        full = load_full_mapping()
        if company not in full["mappings"]:
            raise HTTPException(404, f"Company '{company}' not found")
        full["mappings"][company] = mapping
        save_full_mapping(full)
        return {"status": "success", "message": "Mapping saved"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to save mapping: {str(e)}")

# =========================================================
# Sheet names detection (unchanged)
# =========================================================
@app.post("/api/sheets")
async def get_sheet_names(file: UploadFile):
    """Return list of sheet names from uploaded Excel file."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Only Excel files (.xlsx, .xls) are allowed")

    try:
        contents = await file.read()
        if file.filename.endswith('.xlsx'):
            wb = openpyxl.load_workbook(filename=BytesIO(contents), read_only=True)
            sheets = wb.sheetnames
        else:  # .xls
            df_dict = pd.read_excel(BytesIO(contents), sheet_name=None)
            sheets = list(df_dict.keys())

        return {"sheets": sheets}
    except Exception as e:
        logging.error(f"Failed to read sheets: {e}")
        raise HTTPException(500, f"Could not read sheet names: {str(e)}")

# =========================================================
# Download Excel Template (UPDATED: uses openpyxl for real .xlsx)
# =========================================================
@app.get("/download-template")
async def download_template():
    # Create a new Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"

    # Define headers
    headers = [
        'Sr', 'GSTIN', 'Recipient Name', 'Invoice Number',
        'Invoice date', 'Invoice Value', 'Taxable Value',
        'IGST', 'CGST', 'SGST', 'Cess'
    ]

    # Add headers (bold)
    ws.append(headers)
    for cell in ws[1]:  # first row
        cell.font = Font(bold=True)

    # Add example rows
    data = [
        [1, '27AABCT1234E1Z5', 'ABC Enterprises', 'INV-001', '2025-02-20',
         11800.00, 10000.00, 0, 900.00, 900.00, 0],
        [2, '27BBBTX5678F2Y6', 'XYZ Traders', 'INV-002', '2025-02-21',
         23600.00, 20000.00, 3600.00, 0, 0, 0],
        [3, '27CCCP9012G3H7', 'LMN Pvt Ltd', 'INV-003', '2025-02-22',
         5900.00, 5000.00, 0, 450.00, 450.00, 0]
    ]

    for row in data:
        ws.append(row)

    # Auto-adjust column widths (optional but nice)
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Save to BytesIO
    excel_bytes = io.BytesIO()
    wb.save(excel_bytes)
    excel_bytes.seek(0)

    return Response(
        content=excel_bytes.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="invoice_template.xlsx"'
        }
    )