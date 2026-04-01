import os
from dotenv import load_dotenv
from fastapi import Request
load_dotenv()
import io
import uuid
import logging
import json
import bcrypt
import secrets
import tempfile

MATCH_SESSIONS = {}
JOBS = {}
RESULTS = {}
from datetime import datetime, timedelta
os.makedirs("/data", exist_ok=True)
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, Form, HTTPException, Depends, File
from fastapi.responses import Response, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from core.excel_service import (
    excel_to_xml,
    prepare_excel_party_matching,
    apply_corrections_and_build_final_df,
    export_dataframe_to_excel_bytes,
)
from core.tally_service import (
    build_ledger_xml,
    build_company_status_xml,
    parse_ledgers,
    parse_company_status,
)
from core.match_service import apply_match_results_to_dataframe

import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font

# PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

# Email verification imports
from itsdangerous import BadSignature, SignatureExpired
from core.email import generate_token, decode_token, send_verification_email, send_otp_email, send_welcome_email

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
# APP
# =========================================================
app = FastAPI(title="Tally Automation Tool")

# =========================================================
# SESSION (HF SAFE)
# =========================================================
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tallytool.online",
        "https://www.tallytool.online"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
SESSION_TIMEOUT_MINUTES = 60

@app.middleware("http")
async def session_timeout_middleware(request: Request, call_next):
    if "session" in request.scope:
        try:
            if request.session.get("username"):
                last_active = request.session.get("last_active")
                if last_active:
                    last_dt = datetime.fromisoformat(last_active)
                    if datetime.now() - last_dt > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                        request.session.clear()
                request.session["last_active"] = datetime.now().isoformat()
        except Exception:
            pass
    return await call_next(request)
 
# =========================================================
# STATIC & TEMPLATES
# =========================================================
import os
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "web", "static")),
    name="static"
)
templates = Jinja2Templates(directory="web/templates")

# =========================================================
# USER DB (PostgreSQL) – persistent across rebuilds
# =========================================================
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_user_db():
    """Create users and pending_users tables if they don't exist."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Users table (final) with email and verification fields
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_verified INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Pending registrations (temporary) – stores OTP before final signup
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_users (
            email TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            otp_expiry TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add reset token columns to users table if they don't exist
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
    columns = [col[0] for col in cur.fetchall()]

    if 'reset_token' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
        print("Added reset_token column to users table")

    if 'reset_expiry' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN reset_expiry TIMESTAMP")
        print("Added reset_expiry column to users table")

    conn.commit()
    cur.close()
    conn.close()
    print("✅ User database tables initialized in PostgreSQL")

init_user_db()

# =========================================================
# USER HELPERS (existing + new)
# =========================================================
def get_user(username: str):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def get_user_by_email(email: str):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

# ================= FIXED create_user =================
def create_user(username: str, email: str, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
        (username, email, hashed)
    )

    user_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ User '{username}' created")
    return user_id

# Legacy function (username only) – kept for backward compatibility if needed
def create_user_legacy(username: str, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
        (username, f"{username}@temp.local", hashed)  # placeholder email
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ User '{username}' created in PostgreSQL (legacy, with placeholder email)")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# =========================================================
# PASSWORD RESET HELPERS (NEW)
# =========================================================
def set_user_reset_token(email: str, token: str, expiry: datetime):
    """Store reset token and expiry for user."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET reset_token = %s, reset_expiry = %s WHERE email = %s",
        (token, expiry, email)
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Reset token set for {email}")

def get_user_by_reset_token(token: str):
    """Get user by valid reset token."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM users WHERE reset_token = %s AND reset_expiry > NOW()",
        (token,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def clear_reset_token(email: str):
    """Clear reset token after use."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET reset_token = NULL, reset_expiry = NULL WHERE email = %s",
        (email,)
    )
    conn.commit()
    cur.close()
    conn.close()

def update_user_password(email: str, new_password: str):
    """Update user's password (hashed)."""
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash = %s WHERE email = %s",
        (hashed, email)
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Password updated for {email}")

# =========================================================
# PENDING USER HELPERS (OTP)
# =========================================================
def save_pending_user(email: str, username: str, otp: str, expiry: datetime):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_users (email, username, otp_code, otp_expiry)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (email) DO UPDATE SET
            username = EXCLUDED.username,
            otp_code = EXCLUDED.otp_code,
            otp_expiry = EXCLUDED.otp_expiry
    """, (email, username, otp, expiry))
    conn.commit()
    cur.close()
    conn.close()

def get_pending_user(email: str):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM pending_users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def delete_pending_user(email: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_users WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()

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
USER_STATUS = {}

@app.post("/api/update-status/{user_id}")
def update_status(user_id: str, data: dict):
    print("🔥 STATUS RECEIVED:", user_id, data)

    # If already dict → update
    if isinstance(USER_STATUS.get(user_id), dict):
        USER_STATUS[user_id]["status"] = data.get("status")
        USER_STATUS[user_id]["company"] = data.get("company")
    else:
        # Convert old string → dict
        USER_STATUS[user_id] = {
            "status": data.get("status"),
            "company": data.get("company")
        }

    return {"success": True}

@app.get("/api/tally/status/{user_id}")
def tally_status(user_id: str):
    data = USER_STATUS.get(user_id)

    if isinstance(data, dict):
        return {
            "status": data.get("status", "not_running"),
            "company": data.get("company")
        }

    # fallback (old data)
    return {
        "status": data or "not_running",
        "company": None
    }

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
        request.session["user_id"] = user["id"]   # 🔥 ADD THIS
        return RedirectResponse("/", status_code=302)
    return RedirectResponse("/login?error=1", status_code=302)

@app.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("pages/signup.html", {"request": request})

# Legacy signup endpoint (username/password only) – kept for backward compatibility
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
    create_user_legacy(username, password)
    return RedirectResponse("/login?created=1", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    request.session.clear()
    if is_ajax:
        return JSONResponse({"success": True, "redirect": "/login"})
    return RedirectResponse("/login")

@app.get("/api/me")
async def api_me(request: Request):
    user = get_current_user(request)
    return {"authenticated": bool(user), "username": user}
    

# =========================================================
# OTP ENDPOINTS (for email verification signup)
# =========================================================
@app.post("/api/send-otp")
async def send_otp(email: str = Form(...), username: str = Form(...)):
    """Generate and email a 6-digit OTP for signup."""
    email = email.strip().lower()
    username = username.strip()

    # Basic validation
    if not email or not username:
        return JSONResponse({"status": "error", "message": "Email and username required."}, status_code=400)

    # Check if email already registered
    if get_user_by_email(email):
        return JSONResponse({"status": "error", "message": "Email already registered."}, status_code=400)

    # Check if username already exists
    if get_user(username):
        return JSONResponse({"status": "error", "message": "Username already taken."}, status_code=400)

    # Overwrite any existing pending record for this email
    if get_pending_user(email):
        delete_pending_user(email)

    # Generate 6-digit OTP
    otp = f"{secrets.randbelow(1000000):06d}"
    expiry = datetime.now() + timedelta(minutes=10)  # OTP valid for 10 minutes

    # Store pending record
    save_pending_user(email, username, otp, expiry)

    # Send OTP email
    try:
        send_otp_email(email, otp)
    except Exception as e:
        print(f"OTP email failed: {e}")
        delete_pending_user(email)
        return JSONResponse({"status": "error", "message": "Failed to send OTP email. Please check your email address or try again later."}, status_code=500)

    return JSONResponse({"status": "ok"})
@app.post("/api/verify-otp-signup")
async def verify_otp_signup(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    otp: str = Form(...)
):
    email = email.strip().lower()
    username = username.strip()

    pending = get_pending_user(email)
    if not pending:
        return JSONResponse({"status": "error", "message": "No pending registration found"}, status_code=400)

    if pending["username"] != username:
        return JSONResponse({"status": "error", "message": "Username mismatch"}, status_code=400)

    if pending["otp_code"] != otp:
        return JSONResponse({"status": "error", "message": "Invalid OTP"}, status_code=400)

    expiry = pending["otp_expiry"]
    if isinstance(expiry, str):
        expiry = datetime.fromisoformat(expiry)

    if datetime.now() > expiry:
        delete_pending_user(email)
        return JSONResponse({"status": "error", "message": "OTP expired"}, status_code=400)

    # Final validation
    if get_user_by_email(email) or get_user(username):
        delete_pending_user(email)
        return JSONResponse({"status": "error", "message": "User already exists"}, status_code=400)

    # ✅ CREATE USER
    user_id = create_user(username, email, password)

    # ✅ DEFAULT COMPANY
    from core.mapping import save_company_mapping_postgres, get_default_mapping
    save_company_mapping_postgres("Default", get_default_mapping(), user_id)

    # ✅ SEND EMAIL (optional)
    try:
        send_welcome_email(email, username)
    except Exception as e:
        print("Email error:", e)

    # ✅ DELETE PENDING USER
    delete_pending_user(email)

    return JSONResponse({"status": "ok"})
# =========================================================
# FORGOT USERNAME/PASSWORD ENDPOINTS (NEW)
# =========================================================

@app.post("/api/forgot-username")
async def forgot_username(email: str = Form(...)):
    """Send username to user's email."""
    email = email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        # Return success even if email not found (security)
        return JSONResponse({"status": "ok"})
    
    try:
        # Import the email function
        from core.email import send_username_reminder_email
        send_username_reminder_email(email, user["username"])
    except Exception as e:
        print(f"Failed to send username reminder: {e}")
        return JSONResponse({"status": "error", "message": "Failed to send email."}, status_code=500)
    
    return JSONResponse({"status": "ok"})

@app.post("/api/forgot-password")
async def forgot_password(email: str = Form(...)):
    """Send password reset link to user's email."""
    email = email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        return JSONResponse({"status": "ok"})  # Security: don't reveal existence
    
    # Generate reset token (valid for 1 hour)
    from core.email import generate_token
    reset_token = generate_token(email)
    expiry = datetime.now() + timedelta(hours=1)
    
    set_user_reset_token(email, reset_token, expiry)
    
    BASE_URL = os.environ.get("BASE_URL", "https://tallytool.online")
    reset_link = f"{BASE_URL}/reset-password?token={reset_token}"
    
    try:
        from core.email import send_password_reset_email
        send_password_reset_email(email, reset_link)
    except Exception as e:
        print(f"Failed to send password reset email: {e}")
        return JSONResponse({"status": "error", "message": "Failed to send email."}, status_code=500)
    
    return JSONResponse({"status": "ok"})

@app.post("/api/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    """Reset password using valid token."""
    if len(new_password) < 6:
        return JSONResponse({"status": "error", "message": "Password must be at least 6 characters."}, status_code=400)
    
    user = get_user_by_reset_token(token)
    if not user:
        return JSONResponse({"status": "error", "message": "Invalid or expired token."}, status_code=400)
    
    update_user_password(user["email"], new_password)
    clear_reset_token(user["email"])
    
    return JSONResponse({"status": "ok"})

# =========================================================
# LEGACY EMAIL VERIFICATION ROUTES (if you still need them)
# =========================================================
@app.get("/verify-email/{token}")
async def verify_email_route(request: Request, token: str):
    try:
        email = decode_token(token)
    except SignatureExpired:
        return templates.TemplateResponse("pages/signup.html", {
            "request": request,
            "flashes": [{"category": "error", "message": "Verification link expired. Please sign up again."}]
        })
    except BadSignature:
        return templates.TemplateResponse("pages/signup.html", {
            "request": request,
            "flashes": [{"category": "error", "message": "Invalid verification link."}]
        })

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_verified = 1 WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()

    return RedirectResponse("/login?verified=1", status_code=302)

@app.post("/resend-verification")
async def resend_verification_route(email: str = Form(...)):
    user = get_user_by_email(email)
    if not user or user["is_verified"] == 1:
        return JSONResponse({"status": "ok"})   # silently ignore

    token = generate_token(email)
    try:
        send_verification_email(email, token)
    except Exception:
        return JSONResponse({"status": "error"}, status_code=500)

    return JSONResponse({"status": "ok"})

# =========================================================
# MAPPING APIs (PERSISTENT – CORRECT VERSION)
# =========================================================

@app.get("/api/companies")
async def get_companies(
    request: Request,
    user: str = Depends(require_login)
):
    user_id = request.session.get("user_id") 
    return {"companies": load_companies(user_id)}

@app.post("/api/companies")
async def create_company(
    request: Request,
    name: str = Form(...),
    user: str = Depends(require_login)
):
    try:
        user_id = request.session.get("user_id")
        add_company(name, user_id)
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
        user_id = request.session.get("user_id")
        delete_company(name, user_id)
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
        user_id = request.session.get("user_id")
        return get_company_mapping_data(company, user_id)
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
        user_id = request.session.get("user_id")
        save_company_mapping(company, mapping, user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "saved"}

# ================================
# 🔌 CONNECTOR APIs
# ================================

@app.post("/api/add-job/{user_id}")
def add_job(user_id: str, data: dict):
    JOBS.setdefault(user_id, []).append(data)
    return {"ok": True}


@app.get("/api/get-job/{user_id}")
def get_job(user_id: str):
    print("📥 Connector requested job for:", user_id)

    if JOBS.get(user_id):
        job = JOBS[user_id].pop(0)
        print("📤 Sending job:", job)
        return job

    return {}


@app.post("/api/submit-result/{user_id}")
def submit_result(user_id: str, data: dict):
    RESULTS[user_id] = data
    return {"ok": True}


@app.get("/api/get-result/{user_id}")
def get_result(user_id: str):
    return RESULTS.get(user_id, {})

# =========================================================
# PROTECTED APIs (ORDER PRESERVED)
# =========================================================

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
        
        # Check pending_users table
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'pending_users')")
        pending_exists = cur.fetchone()[0]
        result["pending_users_table_exists"] = pending_exists
        
        if pending_exists:
            cur.execute("SELECT COUNT(*) FROM pending_users")
            pending_count = cur.fetchone()[0]
            result["pending_count"] = pending_count
        
        cur.close()
        conn.close()
        result["database_connected"] = True
        
    except Exception as e:
        result["database_connected"] = False
        result["database_error"] = str(e)
    
    # Check if old SQLite file exists (for reference)
    result["old_sqlite_exists"] = os.path.exists("/data/users.db")
    
    return result

@app.get("/debug/smtp-test")
async def debug_smtp():
    import socket
    import smtplib
    results = {}

    # Get settings from environment or defaults
    server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME", "")
    password = os.environ.get("MAIL_PASSWORD", "")

    # Test DNS resolution
    try:
        ip = socket.gethostbyname(server)
        results["dns_resolution"] = {"host": server, "ip": ip, "status": "ok"}
    except Exception as e:
        results["dns_resolution"] = {"error": str(e), "status": "fail"}

    # Test SMTP connection (without login)
    try:
        with smtplib.SMTP(server, port, timeout=10) as smtp:
            smtp.ehlo()
            if port == 587:
                smtp.starttls()
            smtp.ehlo()
            results["smtp_connection"] = {"status": "ok", "banner": str(smtp.ehlo())}
    except Exception as e:
        results["smtp_connection"] = {"error": str(e), "status": "fail"}

    # If connection works, test login (without sending email)
    if results.get("smtp_connection", {}).get("status") == "ok" and username and password:
        try:
            with smtplib.SMTP(server, port, timeout=10) as smtp:
                smtp.ehlo()
                if port == 587:
                    smtp.starttls()
                smtp.ehlo()
                smtp.login(username, password)
                results["smtp_login"] = {"status": "ok"}
        except Exception as e:
            results["smtp_login"] = {"error": str(e), "status": "fail"}

    return results
@app.get("/reset-password")
async def reset_password_page(request: Request, token: str = None):
    """Render the login page with the reset token for frontend handling."""
    # Pass the token to the template so JavaScript can pick it up
    return templates.TemplateResponse(
        "pages/login.html",
        {"request": request, "reset_token": token}
    )

@app.get("/api/tally/status")
def api_tally_status(request: Request):
    user_id = "1"
    data = USER_STATUS.get(user_id)

    if isinstance(data, dict):
        return {
            "status": data.get("status", "not_running"),
            "company": data.get("company")
        }

    return {
        "status": data or "not_running",
        "company": None
    }

from fastapi import Query

@app.get("/api/tally/ledgers")
def api_tally_ledgers(request: Request, group: str = Query(None)):

    print("📦 API received group:", group)  # ✅ NOW WORKS

    user_id = str(request.session.get("user_id"))

    # 1. create XML with group
    xml = build_ledger_xml(group)

    print("📤 XML SENT:\n", xml)  # 🔥 DEBUG

    # 2. send job
    JOBS.setdefault(user_id, []).append({"xml": xml})

    # 3. check result
    result = RESULTS.get(user_id)

    if not result:
        return {"status": "waiting"}

    # 4. parse result
    ledgers = parse_ledgers(result.get("data", ""))

    return {"status": "ok", "ledgers": ledgers}

@app.post("/api/match-party")
async def match_party(
    request: Request,
    file: UploadFile = File(...),
    tally_group: str = Form(None), 
    sheet_name: str = Form(None),
    manual_columns: str = Form("{}"),
   
):
    try:
        import io
        import json
        import time

        contents = await file.read()
        print("📄 Sheet received from frontend:", sheet_name)

        if sheet_name and sheet_name.strip():
            df = pd.read_excel(io.BytesIO(contents), sheet_name=sheet_name)
        else:
            print("⚠️ No sheet provided, using default Sheet1")
            df = pd.read_excel(io.BytesIO(contents))

        df = df.fillna("")

        from core.match_service import (
            detect_party_column,
            detect_gstin_column,
            match_party_names,
            apply_match_results_to_dataframe,
        )
        from core.tally_service import (
            parse_ledgers_with_gstin,
            build_ledger_xml,
        )

        # Detect columns automatically
        party_col = detect_party_column(df)
        gstin_col = detect_gstin_column(df)

        print("🧠 Detected party column:", party_col)
        print("🧠 Detected GSTIN column:", gstin_col)

        # Parse manual columns if provided
        try:
            manual_cols = json.loads(manual_columns) if isinstance(manual_columns, str) else manual_columns
        except:
            manual_cols = {}

        # Override with manual columns if provided
        if manual_cols.get("party"):
            party_col = manual_cols["party"]
            print("🔧 Using manual party column:", party_col)

        if manual_cols.get("gstin"):
            gstin_col = manual_cols["gstin"]
            print("🔧 Using manual GSTIN column:", gstin_col)

        # Check if both columns are available
        if not party_col or not gstin_col:
            print("⚠️ Missing columns - returning manual_required")
            return {
                "status": "manual_required",
                "columns": list(df.columns),
                "party_column": party_col,
                "gstin_column": gstin_col,
            }

        print("🔄 Fetching Tally ledgers...")
        user_id = "1"

        # 🔥 Send job to connector
        print("📦 MATCH using group:", tally_group)

        xml = build_ledger_xml(tally_group)
        RESULTS.pop(user_id, None) 
        JOBS.setdefault(user_id, []).append({"xml": xml})
        print("🧾 JOB ADDED:", JOBS)

        # 🔥 WAIT for connector response (IMPORTANT FIX)
        result = None
        for _ in range(20):  # ~5 seconds max
            import asyncio
            await asyncio.sleep(0.5)
            result = RESULTS.get(user_id)
            if result:
                break

        if not result:
            print("⏳ Waiting for connector response...")
            return {"status": "waiting"}

        # 🔥 Parse ledgers (FIXED)
        ledgers, gst_map = parse_ledgers_with_gstin(result.get("data", ""))

        print(f"✅ Ledgers fetched: {len(ledgers)}")

        # Match parties
        results = match_party_names(
            df=df,
            tally_ledgers=ledgers,
            tally_gstin_map=gst_map,
            party_col=party_col,
            gstin_col=gstin_col,
        )

        reviewed_df = apply_match_results_to_dataframe(
            df=df,
            match_results=results,
            party_col=party_col,
        )

        session_id = str(uuid.uuid4())
        MATCH_SESSIONS[session_id] = {
            "reviewed_df": reviewed_df,
            "match_results": results,
            "party_col": party_col,
            "gstin_col": gstin_col,
            "ledger_list": ledgers,
            "sheet_name": sheet_name,
            "source_filename": file.filename,
            "columns": list(df.columns),
        }

        unmatched_count = len(
            [r for r in results if r.get("status") != "matched"]
        )

        return {
            "status": "ok",
            "session_id": session_id,
            "party_column": party_col,
            "gstin_column": gstin_col,
            "rows": results,
            "ledger_list": ledgers,
            "unmatched_count": unmatched_count,
            "block_convert": unmatched_count > 0,
        }

    except Exception as e:
        print("❌ MATCH ERROR:", str(e))
        return {"status": "error", "message": str(e)}


@app.post("/api/apply-corrections")
async def api_apply_corrections(payload: dict):
    try:
        session_id = payload.get("session_id")
        corrections = payload.get("corrections", {})

        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = MATCH_SESSIONS.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Matching session not found")

        reviewed_df = session["reviewed_df"]
        party_col = session["party_col"]

        normalized_corrections = {}
        for k, v in corrections.items():
            try:
                normalized_corrections[int(k)] = v
            except Exception:
                continue

        final_df = apply_corrections_and_build_final_df(
            reviewed_df=reviewed_df,
            corrections=normalized_corrections,
            party_col=party_col,
        )

        session["reviewed_df"] = final_df

        unmatched = [
            row for row in session["match_results"]
            if row.get("status") != "matched" and not normalized_corrections.get(row["row_index"])
        ]

        return {
            "status": "ok",
            "unmatched_count": len(unmatched),
            "can_convert": len(unmatched) == 0,
            "preview_rows": final_df.to_dict(orient="records"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
import json

@app.post("/api/download-reviewed-excel")
async def api_download_reviewed_excel(payload: dict):
    try:
        session_id = payload.get("session_id")
        corrections = payload.get("corrections", {})

        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = MATCH_SESSIONS.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Matching session not found")

        # ✅ SAFE DATAFRAME FETCH
        reviewed_df = session.get("reviewed_df")
        if reviewed_df is None:
            reviewed_df = session.get("df")

        if reviewed_df is None:
            raise HTTPException(status_code=500, detail="No dataframe found in session")

        party_col = session.get("party_col")
        if not party_col:
            raise HTTPException(status_code=500, detail="Party column missing in session")

        # ✅ NORMALIZE CORRECTIONS
        normalized_corrections = {}
        for k, v in corrections.items():
            try:
                normalized_corrections[int(k)] = v
            except:
                continue

        print("Corrections:", normalized_corrections)

        # ✅ APPLY CORRECTIONS
        final_df = apply_corrections_and_build_final_df(
            reviewed_df=reviewed_df,
            corrections=normalized_corrections,
            party_col=party_col,
        )

        print("Final DF shape:", final_df.shape)

        # ✅ EXPORT TO EXCEL (BYTES)
        excel_bytes = export_dataframe_to_excel_bytes(final_df)

        # ✅ STREAM FILE (NO TEMP FILE NEEDED)
        output = BytesIO(excel_bytes)
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=reviewed_matching_result.xlsx"
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        print("❌ ERROR:", str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/convert")
async def convert_excel_api(
    request: Request,
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale"),
    company: str = Form("Default"),
    column_mapping: str = Form("{}"),
    tally_corrections: str = Form("{}"),
    user: str = Depends(require_login),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    user_id = request.session.get("user_id")

    try:
        mapping_data = json.loads(column_mapping)
    except Exception:
        mapping_data = {}

    try:
        tally_corrections_data = json.loads(tally_corrections)
        print("🔥 RECEIVED CORRECTIONS:", tally_corrections_data)
    except Exception:
        tally_corrections_data = {}

    xml_content, count = excel_to_xml(
        await file.read(),
        sheet_name,
        vtype,
        company,
        user_id,
        column_mapping=mapping_data,
        tally_corrections=tally_corrections_data,
    )

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={file.filename}_output.xml",
            "X-Records-Processed": str(count),
        },
    )
@app.get("/check-static")
def check_static():
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "web", "static", "downloads")
    return {
        "exists": os.path.exists(path),
        "files": os.listdir(path) if os.path.exists(path) else []
    }

 

