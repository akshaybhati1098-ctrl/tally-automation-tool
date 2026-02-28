import os
import io
import json
import logging
import bcrypt
from typing import Optional
from io import BytesIO

from fastapi import FastAPI, Request, UploadFile, Form, HTTPException, Depends
from fastapi.responses import Response, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font

# Existing services
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.process_service import image_to_excel

app = FastAPI(title="Tally Automation Tool")

# -------------------------
# Session Middleware (NEW)
# -------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production-please")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# -------------------------
# Static files & templates
# -------------------------
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# -------------------------
# User management (NEW)
# -------------------------
USER_DATA_FILE = 'users.json'

def load_users():
    if not os.path.exists(USER_DATA_FILE):
        return {}
    with open(USER_DATA_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# -------------------------
# Flash helpers (NEW)
# -------------------------
def set_flash(request: Request, message: str, category: str = "success"):
    if "_flashes" not in request.session:
        request.session["_flashes"] = []
    request.session["_flashes"].append({"category": category, "message": message})

def get_flashes(request: Request):
    return request.session.pop("_flashes", [])

# -------------------------
# Auth dependency (NEW)
# -------------------------
def get_current_user(request: Request) -> Optional[str]:
    return request.session.get("username")

def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# -------------------------
# Public routes (NEW) - login, signup, logout
# -------------------------
@app.get("/")
async def serve_ui(request: Request):
    """If logged in, show the main SPA; otherwise redirect to login."""
    user = get_current_user(request)
    if user:
        return templates.TemplateResponse("index.html", {"request": request, "username": user})
    return RedirectResponse(url="/login")

@app.get("/login")
async def login_page(request: Request):
    flashes = get_flashes(request)
    return templates.TemplateResponse("pages/login.html", {"request": request, "flashes": flashes})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    users = load_users()
    username = username.strip()
    if username in users and check_password(password, users[username]):
        request.session["username"] = username
        # AJAX support
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"success": True, "redirect": "/"})
        set_flash(request, "Logged in successfully.", "success")
        return RedirectResponse(url="/", status_code=302)
    else:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"success": False, "error": "Invalid username or password."})
        set_flash(request, "Invalid username or password.", "error")
        return RedirectResponse(url="/login", status_code=302)

@app.get("/signup")
async def signup_page(request: Request):
    flashes = get_flashes(request)
    return templates.TemplateResponse("pages/signup.html", {"request": request, "flashes": flashes})

@app.post("/signup")
async def signup_post(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if not username or not password:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"success": False, "error": "Username and password are required."})
        set_flash(request, "Username and password are required.", "error")
        return RedirectResponse(url="/signup", status_code=302)
    users = load_users()
    if username in users:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"success": False, "error": "Username already exists."})
        set_flash(request, "Username already exists.", "error")
        return RedirectResponse(url="/signup", status_code=302)
    users[username] = hash_password(password)
    save_users(users)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"success": True, "redirect": "/login"})
    set_flash(request, "Account created! Please log in.", "success")
    return RedirectResponse(url="/login", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("username", None)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({"success": True, "redirect": "/login"})
    set_flash(request, "You have been logged out.", "success")
    return RedirectResponse(url="/login")

# -------------------------
# API endpoint to check current user (for SPA)
# -------------------------
@app.get("/api/me")
async def get_me(request: Request):
    user = get_current_user(request)
    if user:
        return {"authenticated": True, "username": user}
    return {"authenticated": False}

# -------------------------
# Helper functions for multi‑company mapping (unchanged)
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

# =========================================================
# Protected API endpoints (all now require login)
# =========================================================

@app.post("/api/convert")
async def convert_excel_api(
    request: Request,                      # added request for dependency
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale"),
    company: str = Form("Default"),
    user: str = Depends(require_login)     # NEW
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    try:
        file_bytes = await file.read()
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

@app.post("/api/image-to-excel")
async def image_to_excel_api(
    request: Request,
    file: UploadFile,
    company_key: str = Form(...),
    user: str = Depends(require_login)     # NEW
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
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}"
            }
        )
    except Exception as e:
        logging.error(e)
        raise HTTPException(500, str(e))

@app.get("/api/companies")
async def get_companies(
    request: Request,
    user: str = Depends(require_login)     # NEW
):
    """Return list of all company names."""
    try:
        full = load_full_mapping()
        return JSONResponse(content={"companies": full.get("companies", [])})
    except Exception as e:
        raise HTTPException(500, f"Failed to load companies: {str(e)}")

@app.post("/api/companies")
async def create_company(
    request: Request,
    name: str = Form(...),
    user: str = Depends(require_login)     # NEW
):
    """Create a new company with default mapping."""
    try:
        full = load_full_mapping()
        if name in full["companies"]:
            raise HTTPException(400, f"Company '{name}' already exists")
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
async def remove_company(
    request: Request,
    company: str,
    user: str = Depends(require_login)     # NEW
):
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

@app.put("/api/companies/{old_name}")
async def rename_company(
    request: Request,
    old_name: str,
    new_name: str = Form(...),
    user: str = Depends(require_login)     # NEW
):
    """Rename an existing company. Cannot rename 'Default'."""
    if old_name == "Default":
        raise HTTPException(400, "Cannot rename the Default company")
    try:
        full = load_full_mapping()
        if old_name not in full["companies"]:
            raise HTTPException(404, f"Company '{old_name}' not found")
        if new_name in full["companies"]:
            raise HTTPException(400, f"Company '{new_name}' already exists")
        idx = full["companies"].index(old_name)
        full["companies"][idx] = new_name
        full["mappings"][new_name] = full["mappings"].pop(old_name)
        save_full_mapping(full)
        return {"status": "success", "message": f"Company renamed to '{new_name}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to rename company: {str(e)}")

@app.get("/api/mapping/{company}")
async def get_company_mapping(
    request: Request,
    company: str,
    user: str = Depends(require_login)     # NEW
):
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
async def update_company_mapping(
    request: Request,
    company: str,
    mapping: dict,
    user: str = Depends(require_login)     # NEW
):
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

@app.post("/api/sheets")
async def get_sheet_names(
    request: Request,
    file: UploadFile,
    user: str = Depends(require_login)     # NEW
):
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

@app.get("/download-template")
async def download_template(
    request: Request,
    user: str = Depends(require_login)     # NEW
):
    # Create a new Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"

    headers = [
        'Sr', 'GSTIN', 'Recipient Name', 'Invoice Number',
        'Invoice date', 'Invoice Value', 'Taxable Value',
        'IGST', 'CGST', 'SGST', 'Cess'
    ]

    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

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