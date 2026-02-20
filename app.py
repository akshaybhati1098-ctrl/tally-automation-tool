from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel

app = FastAPI(title="Akshay's Tally Automation")

# ✅ STATIC FIRST (DO NOT MOVE)
app.mount(
    "/static",
    StaticFiles(directory="web/static"),
    name="static"
)

# ✅ TEMPLATES (DO NOT CHANGE PATH)
templates = Jinja2Templates(directory="web/templates")

# ---------------- UI ----------------
@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# ---------------- EXCEL → XML ----------------
@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    try:
        file_bytes = await file.read()
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype)
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename=output.xml",
                "X-Records-Processed": str(count),
            },
        )
    except Exception as e:
        logging.exception(e)
        raise HTTPException(500, "Conversion failed")

# ---------------- MAPPING ----------------
@app.get("/api/mapping")
async def get_mapping():
    return JSONResponse(load_mapping_json())

@app.post("/api/mapping")
async def save_mapping(mapping: dict):
    save_mapping_json(mapping)
    return {"status": "ok"}

# ---------------- COMPANY RULES ----------------
@app.get("/api/company-rules")
async def get_company_rules():
    return JSONResponse(load_rules())

@app.put("/api/company-rules/{key}")
async def save_company(key: str, rule: dict):
    rules = load_rules()
    rules[key] = rule
    save_rules(rules)
    return {"status": "ok"}

@app.delete("/api/company-rules/{key}")
async def delete_company(key: str):
    rules = load_rules()
    rules.pop(key, None)
    save_rules(rules)
    return {"status": "ok"}

# ---------------- IMAGE → EXCEL ----------------
@app.post("/api/convert-image")
async def convert_image(
    file: UploadFile,
    company: str = Form(...)
):
    file_bytes = await file.read()
    excel_bytes, filename = image_to_excel(
        file_bytes, file.filename, company
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )