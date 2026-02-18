from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel
import logging
import os

app = FastAPI(title="Tally Excel to XML Converter")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_ui():
    return FileResponse("static/index.html")

# ---------- XML CONVERSION (existing) ----------
@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Only Excel files (.xlsx, .xls) are allowed")
    try:
        file_bytes = await file.read()
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype)
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={file.filename.replace('.xlsx', '').replace('.xls', '')}_output.xml",
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.error(f"Conversion failed: {e}")
        raise HTTPException(500, f"Conversion failed: {str(e)}")

# ---------- MAPPING ENDPOINTS (existing) ----------
@app.get("/api/mapping")
async def get_mapping():
    try:
        mapping = load_mapping_json()
        return JSONResponse(content=mapping)
    except Exception as e:
        raise HTTPException(500, f"Failed to load mapping: {str(e)}")

@app.post("/api/mapping")
async def update_mapping(mapping: dict):
    try:
        save_mapping_json(mapping)
        return {"status": "success", "message": "Mapping saved"}
    except Exception as e:
        raise HTTPException(500, f"Failed to save mapping: {str(e)}")

# ---------- COMPANY RULES (for PDF/Image to Excel) ----------
@app.get("/api/company-rules")
async def get_company_rules():
    """Return all company rules."""
    try:
        rules = load_rules()
        return JSONResponse(content=rules)
    except Exception as e:
        raise HTTPException(500, f"Failed to load company rules: {str(e)}")

@app.put("/api/company-rules/{company_key}")
async def add_or_update_company(company_key: str, rule_data: dict):
    """Add or update a single company rule."""
    try:
        rules = load_rules()
        rules[company_key] = rule_data
        save_rules(rules)
        return {"status": "success", "message": f"Company {company_key} saved"}
    except Exception as e:
        raise HTTPException(500, f"Failed to save company rule: {str(e)}")

@app.delete("/api/company-rules/{company_key}")
async def delete_company(company_key: str):
    """Delete a company rule."""
    try:
        rules = load_rules()
        if company_key in rules:
            del rules[company_key]
            save_rules(rules)
            return {"status": "success", "message": f"Company {company_key} deleted"}
        else:
            raise HTTPException(404, "Company not found")
    except Exception as e:
        raise HTTPException(500, f"Failed to delete company rule: {str(e)}")

# ---------- PDF/IMAGE TO EXCEL CONVERSION ----------
@app.post("/api/convert-image")
async def convert_image_to_excel(
    file: UploadFile,
    company: str = Form(...)   # company key from dropdown
):
    allowed = ('.pdf', '.jpg', '.jpeg', '.png')
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(400, f"Only PDF/Image files {allowed} are allowed")

    try:
        file_bytes = await file.read()
        excel_bytes, filename = image_to_excel(file_bytes, file.filename, company)
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logging.error(f"Image to Excel conversion failed: {e}")
        raise HTTPException(500, f"Conversion failed: {str(e)}")