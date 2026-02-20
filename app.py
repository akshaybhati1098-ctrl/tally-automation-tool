from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import os

# ===== Core Services =====
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel

# =========================
# App Init
# =========================
app = FastAPI(title="Akshay's Tally Automation")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================
# Static Files
# =========================
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "web/static")),
    name="static"
)

# =========================
# Templates
# =========================
templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "web/templates")
)

# =========================
# UI Route
# =========================
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# =========================
# Excel → XML
# =========================
@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    try:
        data = await file.read()
        xml_content, count = excel_to_xml(data, sheet_name, vtype)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename=output.xml",
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.exception(e)
        raise HTTPException(500, str(e))

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

@app.put("/api/company-rules/{key}")
async def save_company(key: str, rule: dict):
    rules = load_rules()
    rules[key] = rule
    save_rules(rules)
    return {"status": "saved"}

@app.delete("/api/company-rules/{key}")
async def delete_company(key: str):
    rules = load_rules()
    if key in rules:
        del rules[key]
        save_rules(rules)
        return {"status": "deleted"}
    raise HTTPException(404, "Company not found")

# =========================
# PDF / Image → Excel
# =========================
@app.post("/api/convert-image")
async def convert_image(
    file: UploadFile,
    company: str = Form(...)
):
    try:
        data = await file.read()
        excel_bytes, filename = image_to_excel(
            data, file.filename, company
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
        raise HTTPException(500, str(e))

# =========================
# Run (Local only)
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860)