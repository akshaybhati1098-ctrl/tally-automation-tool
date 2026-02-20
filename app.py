from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

# ===== Core imports =====
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel

# =========================
# App Init
# =========================
app = FastAPI(title="Akshay's Tally Automation")

# =========================
# Static Files (VERY IMPORTANT: DO NOT MOVE)
# =========================
app.mount(
    "/static",
    StaticFiles(directory="web/static"),
    name="static"
)

# =========================
# Templates
# =========================
templates = Jinja2Templates(directory="web/templates")

# =========================
# UI Route
# =========================
@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# =========================
# Excel → XML API
# =========================
@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files are allowed")

    try:
        file_bytes = await file.read()
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": "attachment; filename=output.xml",
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.exception(e)
        raise HTTPException(500, "Excel to XML conversion failed")

# =========================
# Mapping APIs
# =========================
@app.get("/api/mapping")
async def get_mapping():
    return JSONResponse(load_mapping_json())

@app.post("/api/mapping")
async def save_mapping(mapping: dict):
    save_mapping_json(mapping)
    return {"status": "success"}

# =========================
# Company Rules APIs
# =========================
@app.get("/api/company-rules")
async def get_company_rules():
    return JSONResponse(load_rules())

@app.put("/api/company-rules/{company_key}")
async def save_company_rule(company_key: str, rule: dict):
    rules = load_rules()
    rules[company_key] = rule
    save_rules(rules)
    return {"status": "saved"}

@app.delete("/api/company-rules/{company_key}")
async def delete_company_rule(company_key: str):
    rules = load_rules()
    if company_key in rules:
        del rules[company_key]
        save_rules(rules)
        return {"status": "deleted"}
    raise HTTPException(404, "Company not found")

# =========================
# PDF / Image → Excel API
# =========================
@app.post("/api/convert-image")
async def convert_image(
    file: UploadFile,
    company: str = Form(...)
):
    try:
        file_bytes = await file.read()
        excel_bytes, filename = image_to_excel(
            file_bytes, file.filename, company
        )

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logging.exception(e)
        raise HTTPException(500, "Image to Excel conversion failed")