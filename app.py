# ========================= IMPORTS =========================
import os
import io
import logging
import bcrypt
import secrets
from datetime import datetime, timedelta
os.makedirs("/data", exist_ok=True)
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, Form, HTTPException, Depends
from fastapi.responses import Response, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font

import psycopg2
from psycopg2.extras import RealDictCursor

from itsdangerous import BadSignature, SignatureExpired
from core.email import generate_token, decode_token, send_verification_email, send_otp_email, send_welcome_email

from core.excel_service import excel_to_xml
from core.mapping import (
    load_companies,
    add_company,
    delete_company,
    get_company_mapping as get_company_mapping_data,
    save_company_mapping
)
from core.process_service import image_to_excel

# ========================= APP =========================
app = FastAPI(title="Tally Automation Tool")

# ========================= SESSION =========================
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY not set")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="none",
    https_only=True
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tallytool.online"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================= STATIC =========================
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# ========================= DB =========================
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# ========================= INIT =========================
def init_user_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_users (
            email TEXT PRIMARY KEY,
            username TEXT,
            otp_code TEXT,
            otp_expiry TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_user_db()

# ========================= USER =========================
def get_user(username):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def get_user_by_email(email):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

# ✅ FIXED
def create_user(username, email, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO users (username,email,password_hash) VALUES (%s,%s,%s) RETURNING id",
        (username, email, hashed)
    )

    user_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Created user {username}")
    return user_id

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ========================= SESSION HELPERS =========================
def get_current_user(request: Request):
    return request.session.get("username")

def require_login(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login")
    return request.session.get("username")

# ========================= ROUTES =========================
@app.get("/")
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("pages/login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username)
    if user and verify_password(password, user["password_hash"]):
        request.session["username"] = username
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=302)
    return RedirectResponse("/login?error=1")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# ========================= OTP =========================
@app.post("/api/send-otp")
async def send_otp(email: str = Form(...), username: str = Form(...)):
    otp = f"{secrets.randbelow(1000000):06d}"
    expiry = datetime.now() + timedelta(minutes=10)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_users (email,username,otp_code,otp_expiry)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT(email) DO UPDATE SET otp_code=%s, otp_expiry=%s
    """, (email, username, otp, expiry, otp, expiry))
    conn.commit()
    cur.close()
    conn.close()

    send_otp_email(email, otp)
    return {"status": "ok"}

# ✅ FIXED FULL BLOCK
@app.post("/api/verify-otp-signup")
async def verify_otp_signup(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    otp: str = Form(...)
):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM pending_users WHERE email=%s", (email,))
    pending = cur.fetchone()

    if not pending or pending["otp_code"] != otp:
        return {"status": "error"}

    # ✅ Create user
    user_id = create_user(username, email, password)
    
    # 🔥 ADD THIS HERE
    from core.mapping import migrate_json_to_postgres
    migrate_json_to_postgres(user_id)

    # ✅ Default company per user
    from core.mapping import save_company_mapping_postgres, get_default_mapping
    save_company_mapping_postgres("Default", get_default_mapping(), user_id)

    # email
    try:
        send_welcome_email(email, username)
    except:
        pass

    # delete pending
    cur.execute("DELETE FROM pending_users WHERE email=%s", (email,))
    conn.commit()

    cur.close()
    conn.close()

    return {"status": "ok"}

# ========================= COMPANIES =========================
@app.get("/api/companies")
async def get_companies(request: Request, user=Depends(require_login)):
    user_id = request.session.get("user_id")
    return {"companies": load_companies(user_id)}

@app.post("/api/companies")
async def add_comp(request: Request, name: str = Form(...), user=Depends(require_login)):
    user_id = request.session.get("user_id")
    add_company(name, user_id)
    return {"status": "ok"}

@app.delete("/api/companies/{name}")
async def delete_comp(request: Request, name: str, user=Depends(require_login)):
    user_id = request.session.get("user_id")
    delete_company(name, user_id)
    return {"status": "ok"}

@app.get("/api/mapping/{company}")
async def get_map(request: Request, company: str, user=Depends(require_login)):
    user_id = request.session.get("user_id")
    return get_company_mapping_data(company, user_id)

@app.post("/api/mapping/{company}")
async def save_map(request: Request, company: str, mapping: dict, user=Depends(require_login)):
    user_id = request.session.get("user_id")
    save_company_mapping(company, mapping, user_id)
    return {"status": "ok"}