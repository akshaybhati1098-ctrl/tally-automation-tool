import os
import logging
from fastapi import (
    FastAPI,
    UploadFile,
    Form,
    HTTPException,
    Request
)
from fastapi.responses import (
    Response,
    JSONResponse,
    HTMLResponse
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# -----------------------------
# CORE SERVICES
# -----------------------------
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel

# -----------------------------
# BASE DIR (HF SAFE)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------
# APP INIT
# -----------------------------
app = FastAPI(title="Tally Automation")

# -----------------------------
# STATIC FILES
# -----------------------------
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "web", "static")),
    name="static"
)

# -----------------------------
# TEMPLATES
# -----------------------------
templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "web", "templates")
)

# -----------------------------
# ROOT UI
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# -----------------------------
# SPA PAGE ROUTES
# -----------------------------
@app.get("/pages/{page}", response_class=HTMLResponse)
async def load_page(request: Request, page: str):

    pages = {
        "dashboard": "pages/dashboard.html",
        "excel_to_xml": "pages/excel_to_xml.html",
        "image_to_excel": "pages/image_to_excel.html",
        "mapping": "pages/mapping.html",
        "company": "pages/company.html",
        "settings": "pages/settings.html",
    }

    if page not in pages:
        raise HTTPException(status_code=404, detail="Page not found")

    return templates.TemplateResponse(
        pages[page],
        {"request": request}
    )

# =================================================
# =================== APIs ========================
# =================================================

# -------- Excel → XML --------
@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
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
        logging.exception("Excel conversion failed")
        raise HTTPException(500, str(e))


# -------- Mapping --------
@app.get("/api/mapping")
async def get_mapping():
    return load_mapping_json()


@app.post("/api/mapping")
async def save_mapping(mapping: dict):
    save_mapping_json(mapping)
    return {"status": "success"}


# -------- Company Rules --------
@app.get("/api/company-rules")
async def get_company_rules():
    return load_rules()


@app.put("/api/company-rules/{company_key}")
async def update_company_rule(company_key: str, rule: dict):
    rules = load_rules()
    rules[company_key] = rule
    save_rules(rules)
    return {"status": "success"}


@app.delete("/api/company-rules/{company_key}")
async def delete_company_rule(company_key: str):
    rules = load_rules()
    if company_key not in rules:
        raise HTTPException(404, "Company not found")

    del rules[company_key]
    save_rules(rules)
    return {"status": "deleted"}


# -------- PDF / Image → Excel --------
@app.post("/api/convert-image")
async def convert_image(
    file: UploadFile,
    company: str = Form(...)
):
    allowed = (".pdf", ".jpg", ".jpeg", ".png")
    if not file.filename.lower().endswith(allowed):
        raise HTTPException(400, "Invalid file type")

    data = await file.read()
    excel_bytes, filename = image_to_excel(data, file.filename, company)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}