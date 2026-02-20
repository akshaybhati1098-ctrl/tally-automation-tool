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
# BASE DIR
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
# PAGE FRAGMENTS (SPA)
# -----------------------------
@app.get("/pages/{page}", response_class=HTMLResponse)
async def pages(request: Request, page: str):

    pages_map = {
        "dashboard": "pages/dashboard.html",
        "excel_to_xml": "pages/excel_to_xml.html",
        "image_to_excel": "pages/image_to_excel.html",
        "mapping": "pages/mapping.html",
        "company": "pages/company.html",
        "settings": "pages/settings.html",
    }

    if page not in pages_map:
        raise HTTPException(status_code=404, detail="Page not found")

    return templates.TemplateResponse(
        pages_map[page],
        {"request": request}
    )

# -----------------------------
# HEALTH CHECK (DEBUG)
# -----------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}