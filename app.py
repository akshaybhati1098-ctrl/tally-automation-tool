from io import BytesIO
from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.responses import Response, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import openpyxl
import pandas as pd
import sqlite3

# Existing services
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json   # these will now store the full structure

# Image → Excel service
from core.process_service import image_to_excel

# ========== NEW AUTH IMPORTS ==========
from database import get_db, init_db
from auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
)
# =======================================

app = FastAPI(title="Tally Automation Tool")

# -------------------------
# Static files & templates
# -------------------------
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# ========== NEW: DATABASE INIT ON STARTUP ==========
@app.on_event("startup")
def startup_event():
    init_db()
# ====================================================

# ========== NEW: MIDDLEWARE TO ATTACH USER TO REQUEST ==========
@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    user = await get_current_user(request)
    request.state.user = user
    response = await call_next(request)
    return response
# ================================================================

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

# ========== NEW AUTH ROUTES ==========
@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    try:
        if password != confirm_password:
            return templates.TemplateResponse(
                "pages/register.html",
                {"request": request, "error": "Passwords do not match"}
            )
        if len(password) < 6:
            return templates.TemplateResponse(
                "pages/register.html",
                {"request": request, "error": "Password must be at least 6 characters"}
            )

        hashed = get_password_hash(password)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed)
            )
            conn.commit()

        # Success – redirect to login with a success message
        response = RedirectResponse(url="/login?registered=1", status_code=302)
        return response

    except sqlite3.IntegrityError:
        # Username already exists
        return templates.TemplateResponse(
            "pages/register.html",
            {"request": request, "error": "Username already taken"}
        )
    except Exception as e:
        # Log the full error for debugging
        logging.error(f"Registration error: {str(e)}", exc_info=True)
        return templates.TemplateResponse(
            "pages/register.html",
            {"request": request, "error": "An unexpected error occurred. Please try again."}
        )
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
@app.get("/")
async def serve_ui(request: Request):
    user = request.state.user
    # Choose default page: dashboard if logged in, otherwise converter (or any other page)
    default_page = "dashboard" if user else "converter"
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "default_page": default_page}
    )