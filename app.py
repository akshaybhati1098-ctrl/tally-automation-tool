
import os
import io
import logging
import sqlite3
import bcrypt
os.makedirs("/data", exist_ok=True)
from io import BytesIO
from typing import Optional

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
from core.mapping import (
    load_companies,
    add_company,
    delete_company,
    get_company_mapping as get_company_mapping_data,
    save_company_mapping
)
from core.process_service import image_to_excel

# =========================================================
# APP
# =========================================================
app = FastAPI(title="Tally Automation Tool")

# =========================================================
# SESSION (HF SAFE)
# =========================================================
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="none",
    https_only=True
)

# =========================================================
# STATIC & TEMPLATES
# =========================================================
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# =========================================================
# USER DB (SQLite)
# =========================================================
DB_PATH = "/data/users.db"

def init_user_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_user_db()

def get_user(username: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()
    return user

def create_user(username: str, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, hashed)
    )
    conn.commit()
    conn.close()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# =========================================================
# AUTH HELPERS
# =========================================================
def get_current_user(request: Request) -> Optional[str]:
    return request.session.get("username")

def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return user

# =========================================================
# UI ROUTES (IMPORTANT FIX)
# =========================================================
@app.get("/")
async def serve_ui(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "username": user}
    )

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("pages/login.html", {"request": request})

@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    username = username.strip()
    user = get_user(username)
    if user and verify_password(password, user["password_hash"]):
        request.session["username"] = username
        return RedirectResponse("/", status_code=302)
    return RedirectResponse("/login?error=1", status_code=302)

@app.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("pages/signup.html", {"request": request})

@app.post("/signup")
async def signup_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    username = username.strip()
    if not username or not password:
        return RedirectResponse("/signup?error=1", status_code=302)
    if get_user(username):
        return RedirectResponse("/signup?exists=1", status_code=302)
    create_user(username, password)
    return RedirectResponse("/login?created=1", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/api/me")
async def api_me(request: Request):
    user = get_current_user(request)
    return {"authenticated": bool(user), "username": user}

# =========================================================
# MAPPING APIs (PERSISTENT)
# =========================================================

@app.get("/api/companies")
async def get_companies(
    request: Request,
    user: str = Depends(require_login)
):
    return {"companies": load_companies()}


@app.post("/api/companies")
async def create_company(
    request: Request,
    name: str = Form(...),
    user: str = Depends(require_login)
):
    try:
        add_company(name)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "success"}


@app.delete("/api/companies/{name}")
async def remove_company(
    request: Request,
    name: str,
    user: str = Depends(require_login)
):
    try:
        delete_company(name)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "deleted"}


@app.get("/api/mapping/{company}")
async def get_company_mapping_api(
    request: Request,
    company: str,
    user: str = Depends(require_login)
):
    try:
        return get_company_mapping_data(company)
    except ValueError:
        raise HTTPException(404)


@app.post("/api/mapping/{company}")
async def update_company_mapping(
    request: Request,
    company: str,
    mapping: dict,
    user: str = Depends(require_login)
):
    try:
        save_company_mapping(company, mapping)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "saved"}
# =========================================================
# PROTECTED APIs (ORDER PRESERVED)
# =========================================================
@app.post("/api/convert")
async def convert_excel_api(
    request: Request,
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale"),
    company: str = Form("Default"),
    user: str = Depends(require_login)
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    xml_content, count = excel_to_xml(
        await file.read(),
        sheet_name,
        vtype,
        company
    )

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={file.filename}_output.xml",
            "X-Records-Processed": str(count)
        }
    )

@app.post("/api/image-to-excel")
async def image_to_excel_api(
    request: Request,
    file: UploadFile,
    company_key: str = Form(...),
    user: str = Depends(require_login)
):
    excel_bytes, output_filename = image_to_excel(
        await file.read(),
        file.filename,
        company_key
    )
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={output_filename}"}
    )

@app.get("/api/companies")
async def get_companies(
    request: Request,
    user: str = Depends(require_login)
):
    return {"companies": load_full_mapping().get("companies", [])}

@app.post("/api/companies")
async def create_company(
    request: Request,
    name: str = Form(...),
    user: str = Depends(require_login)
):
    full = load_full_mapping()
    if name in full["companies"]:
        raise HTTPException(400, "Company already exists")
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
    return {"status": "success"}

@app.get("/api/mapping/{company}")
async def get_company_mapping(
    request: Request,
    company: str,
    user: str = Depends(require_login)
):
    full = load_full_mapping()
    if company not in full["mappings"]:
        raise HTTPException(404)
    return full["mappings"][company]

@app.post("/api/mapping/{company}")
async def update_company_mapping(
    request: Request,
    company: str,
    mapping: dict,
    user: str = Depends(require_login)
):
    full = load_full_mapping()
    full["mappings"][company] = mapping
    save_full_mapping(full)
    return {"status": "saved"}

@app.post("/api/sheets")
async def get_sheet_names(
    request: Request,
    file: UploadFile,
    user: str = Depends(require_login)
):
    contents = await file.read()
    if file.filename.endswith(".xlsx"):
        wb = openpyxl.load_workbook(BytesIO(contents), read_only=True)
        return {"sheets": wb.sheetnames}
    df = pd.read_excel(BytesIO(contents), sheet_name=None)
    return {"sheets": list(df.keys())}

@app.get("/download-template")
async def download_template(
    request: Request,
    user: str = Depends(require_login)
):
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"

    headers = [
        'Sr','GSTIN','Recipient Name','Invoice Number',
        'Invoice date','Invoice Value','Taxable Value',
        'IGST','CGST','SGST','Cess'
    ]

    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)

    excel_bytes = io.BytesIO()
    wb.save(excel_bytes)
    excel_bytes.seek(0)

    return Response(
        content=excel_bytes.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=invoice_template.xlsx"}
    )
@app.get("/debug/persistence")
def debug_persistence():
    import os, sqlite3

    data_exists = os.path.exists("/data")
    data_files = os.listdir("/data") if data_exists else []

    users = []
    if os.path.exists(DB_PATH):
        users = sqlite3.connect(DB_PATH).execute(
            "SELECT username FROM users"
        ).fetchall()

    return {
        "data_dir_exists": data_exists,
        "data_dir_files": data_files,
        "db_path": DB_PATH,
        "users_in_db": users
    }