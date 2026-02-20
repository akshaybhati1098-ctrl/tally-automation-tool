from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel

# -------------------------------------------------
# APP INITIALIZATION
# -------------------------------------------------

app = FastAPI(title="Tally Automation")

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Jinja templates
templates = Jinja2Templates(directory="web/templates")

# -------------------------------------------------
# UI ROUTES
# -------------------------------------------------

@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# -------------------------------------------------
# EXCEL → XML
# -------------------------------------------------

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
                "Content-Disposition": f"attachment; filename={file.filename.rsplit('.',1)[0]}_output.xml",
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.exception("Excel to XML failed")
        raise HTTPException(500, str(e))

# -------------------------------------------------
# LEDGER MAPPING
# -------------------------------------------------

@app.get("/api/mapping")
async def get_mapping():
    try:
        return JSONResponse(content=load_mapping_json())
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/mapping")
async def update_mapping(mapping: dict):
    try:
        save_mapping_json(mapping)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

# -------------------------------------------------
# COMPANY RULES
# -------------------------------------------------

@app.get("/api/company-rules")
async def get_company_rules():
    try:
        return JSONResponse(content=load_rules())
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/company-rules/{company_key}")
async def save_company_rule(company_key: str, rule_data: dict):
    try:
        rules = load_rules()
        rules[company_key] = rule_data
        save_rules(rules)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/company-rules/{company_key}")
async def delete_company_rule(company_key: str):
    try:
        rules = load_rules()
        if company_key not in rules:
            raise HTTPException(404, "Company not found")

        del rules[company_key]
        save_rules(rules)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(500, str(e))

# -------------------------------------------------
# PDF / IMAGE → EXCEL
# -------------------------------------------------

@app.post("/api/convert-image")
async def convert_image_to_excel(
    file: UploadFile,
    company: str = Form(...)
):
    allowed = (".pdf", ".jpg", ".jpeg", ".png")

    if not file.filename.lower().endswith(allowed):
        raise HTTPException(400, "Only PDF or image files allowed")

    try:
        file_bytes = await file.read()
        excel_bytes, filename = image_to_excel(
            file_bytes,
            file.filename,
            company
        )

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logging.exception("Image to Excel failed")
        raise HTTPException(500, str(e))