import os
import sys
import io
import sqlite3
import bcrypt
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, Form, HTTPException, Depends
from fastapi.responses import Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font

# =========================================================
# FIX PYTHON PATH (important for HuggingFace Spaces)
# =========================================================
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# =========================================================
# IMPORT CORE SERVICES
# =========================================================
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.process_service import image_to_excel

# =========================================================
# CREATE DATA FOLDER (persistent storage)
# =========================================================
os.makedirs("/data", exist_ok=True)

# =========================================================
# FASTAPI APP
# =========================================================
app = FastAPI(title="Tally Automation Tool")

# =========================================================
# SESSION CONFIG
# =========================================================
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="none",
    https_only=True
)

# =========================================================
# STATIC + TEMPLATE
# =========================================================
app.mount("/static", StaticFiles(directory="web/static"), name="static")

templates = Jinja2Templates(directory="web/templates")

# =========================================================
# USER DATABASE
# =========================================================
DB_PATH = "/data/users.db"


def init_user_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)

    conn.commit()
    conn.close()


init_user_db()


def get_user(username: str):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=?", (username,))

    user = cur.fetchone()

    conn.close()

    return user


def create_user(username: str, password: str):

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO users (username,password_hash) VALUES (?,?)",
        (username, hashed)
    )

    conn.commit()
    conn.close()


def verify_password(password: str, hashed: str):

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
# UI ROUTES
# =========================================================
@app.get("/")
async def home(request: Request):

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "username": user}
    )


@app.get("/login")
async def login_page(request: Request):

    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


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

    return templates.TemplateResponse(
        "signup.html",
        {"request": request}
    )


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

    return {
        "authenticated": bool(user),
        "username": user
    }


# =========================================================
# MAPPING HELPERS
# =========================================================
def load_full_mapping():

    data = load_mapping_json()

    if "companies" not in data:

        data = {
            "companies": ["Default"],
            "mappings": {"Default": data}
        }

        save_mapping_json(data)

    return data


# =========================================================
# API ROUTES
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
        raise HTTPException(400, "Only Excel allowed")

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
            "Content-Disposition": f"attachment; filename={file.filename}.xml",
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

    excel_bytes, filename = image_to_excel(
        await file.read(),
        file.filename,
        company_key
    )

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/sheets")
async def get_sheets(
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


# =========================================================
# DOWNLOAD TEMPLATE
# =========================================================
@app.get("/download-template")
async def download_template(
        request: Request,
        user: str = Depends(require_login)
):

    wb = Workbook()

    ws = wb.active
    ws.title = "Template"

    headers = [
        'Sr',
        'GSTIN',
        'Recipient Name',
        'Invoice Number',
        'Invoice date',
        'Invoice Value',
        'Taxable Value',
        'IGST',
        'CGST',
        'SGST',
        'Cess'
    ]

    ws.append(headers)

    for c in ws[1]:
        c.font = Font(bold=True)

    file = io.BytesIO()

    wb.save(file)

    file.seek(0)

    return Response(
        content=file.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=invoice_template.xlsx"
        }
    )


# =========================================================
# DEBUG ROUTE
# =========================================================
@app.get("/debug/persistence")
def debug():

    data_exists = os.path.exists("/data")

    files = os.listdir("/data") if data_exists else []

    users = []

    if os.path.exists(DB_PATH):

        users = sqlite3.connect(DB_PATH).execute(
            "SELECT username FROM users"
        ).fetchall()

    return {
        "data_dir": data_exists,
        "files": files,
        "users": users
    }