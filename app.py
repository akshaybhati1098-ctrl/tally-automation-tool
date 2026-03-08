import os
import io
import logging
import sqlite3
import bcrypt
import psycopg2 
from psycopg2.extras import RealDictCursor 
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

# Existing services – these now use persistent /data/mapping.json
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
# ✅ ADDITION 1 OF 4 — import the email verification router
# =========================================================
from core.email_verification import (
    router as verify_router,
    migrate_users_table,
    generate_token,
    register_and_send,
    check_verified,
)

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
# ✅ ADDITION 2 OF 4 — register the verification routes
# =========================================================
app.include_router(verify_router)

# =========================================================
# USER DB (PostgreSQL) – persistent across rebuilds
# =========================================================
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_user_db():
    """Create users table if it doesn't exist."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ User database table initialized in PostgreSQL")

# Initialize the table on startup
init_user_db()

# =========================================================
# ✅ ADDITION 3 OF 4 — run the column migration on startup
# =========================================================
migrate_users_table()

def get_user(username: str):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def create_user(username: str, password: str, email: str = ""):
    # ✅ ADDITION 4 OF 4 — also stores email when creating a user
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, email) VALUES (%s, %s, %s)",
        (username, hashed, email)
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ User '{username}' created in PostgreSQL")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# =========================================================
# AUTH HELPERS (FIXED – DEFINED BEFORE ROUTES THAT USE THEM)
# =========================================================
def get_current_user(request: Request) -> Optional[str]:
    return request.session.get("username")

def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return user

# =========================================================
# UI ROUTES
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
        # Block login if email is not yet verified
        if not check_verified(user):
            return templates.TemplateResponse("pages/signup.html", {
                "request": request,
                "flashes": [{
                    "category": "error",
                    "message": "Please verify your email before logging in. "
                               "Check your inbox or use the resend option."
                }]
            })
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
    password: str = Form(...),
    email: str = Form(default="")
):
    username = username.strip()
    email    = email.strip().lower()

    # ── Validation — return JSON errors so fetch() can read them ──
    if not username or not password:
        return JSONResponse({"status": "error", "message": "Username and password are required."}, status_code=400)

    if not email:
        return JSONResponse({"status": "error", "message": "Email address is required."}, status_code=400)

    if get_user(username):
        return JSONResponse({"status": "error", "message": "Username already taken. Please choose another."}, status_code=400)

    # ── Create user (is_verified = FALSE by default) ───────────────
    create_user(username, password, email)

    # ── Send verification email ────────────────────────────────────
    email_sent = False
    try:
        token = generate_token(email)
        register_and_send(email, token)
        email_sent = True
    except Exception as e:
        print(f"[SIGNUP] Email send failed: {e}")
        # Account is created — user can resend from the pending view

    # ── Always return JSON — the frontend JS handles the view switch ─
    return JSONResponse({
        "status": "ok",
        "email_sent": email_sent,
        "email": email,
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/api/me")
async def api_me(request: Request):
    user = get_current_user(request)
    return {"authenticated": bool(user), "username": user}

# =========================================================
# MAPPING APIs (PERSISTENT – CORRECT VERSION)
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
    import os
    
    result = {
        "app_status": "running",
        "database_url_set": bool(os.environ.get("DATABASE_URL")),
        "environment": os.environ.get("RENDER", "not set"),
    }
    
    # Test database connection
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check users table
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')")
        users_table_exists = cur.fetchone()[0]
        result["users_table_exists"] = users_table_exists
        
        if users_table_exists:
            cur.execute("SELECT COUNT(*) FROM users")
            user_count = cur.fetchone()[0]
            result["user_count"] = user_count
            
            cur.execute("SELECT username FROM users LIMIT 5")
            users = [row[0] for row in cur.fetchall()]
            result["sample_users"] = users
        
        # Check mapping table  
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'company_mapping')")
        mapping_table_exists = cur.fetchone()[0]
        result["mapping_table_exists"] = mapping_table_exists
        
        if mapping_table_exists:
            cur.execute("SELECT COUNT(*) FROM company_mapping")
            company_count = cur.fetchone()[0]
            result["company_count"] = company_count
            
            cur.execute("SELECT company FROM company_mapping LIMIT 5")
            companies = [row[0] for row in cur.fetchall()]
            result["sample_companies"] = companies
        
        cur.close()
        conn.close()
        result["database_connected"] = True
        
    except Exception as e:
        result["database_connected"] = False
        result["database_error"] = str(e)
    
    # Check if old SQLite file exists
    result["old_sqlite_exists"] = os.path.exists("/data/users.db")
    
    return result