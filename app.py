from io import BytesIO
from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.responses import Response, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging
import openpyxl
import pandas as pd
import os

# Existing services
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.process_service import image_to_excel

app = FastAPI(title="Tally Automation Tool")

# -------------------------
# Authentication Setup
# -------------------------

# Load users from environment variables (set in Hugging Face Secrets)
def load_users():
    """Read USERx_NAME and USERx_PASSWORD from environment variables."""
    users = {}
    i = 1
    while True:
        name = os.getenv(f"USER{i}_NAME")
        pwd = os.getenv(f"USER{i}_PASSWORD")
        if name is None or pwd is None:
            break
        users[name] = pwd
        i += 1
    return users

# First define AuthMiddleware class (keep its definition unchanged)
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ... your existing code (no changes) ...

# Then add middlewares in the correct order:
# AuthMiddleware first (so it runs after SessionMiddleware)
app.add_middleware(AuthMiddleware)

# SessionMiddleware second (so it runs before AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "default-insecure-change-me")
)
        # Don't require authentication for static files and login page
        if request.url.path.startswith("/static") or request.url.path == "/login":
            return await call_next(request)
        
        # Check if user is logged in
        user = request.session.get("user")
        if not user:
            # API requests get JSON 401 error
            if request.url.path.startswith("/api"):
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            # Web requests get redirected to login
            return RedirectResponse(url="/login", status_code=302)
        
        # User is authenticated, proceed
        return await call_next(request)

app.add_middleware(AuthMiddleware)

# Load users on startup
@app.on_event("startup")
async def startup_event():
    users = load_users()
    if not users:
        logging.warning("No users defined in secrets. Authentication will reject all logins.")
    app.state.users = users

# -------------------------
# Login Routes
# -------------------------

@app.get("/login")
async def login_form(request: Request):
    """Serve the login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Process login credentials."""
    users = request.app.state.users
    if username in users and users[username] == password:
        request.session["user"] = username
        return RedirectResponse(url="/", status_code=302)
    # Invalid credentials
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid username or password"}
    )

@app.post("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

# -------------------------
# Static files & templates
# -------------------------
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

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

# =========================================================
# Excel → XML API (with company selection)
# =========================================================
@app.post("/api/convert")
async def convert_excel_api(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale"),
    company: str = Form("Default")
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

        idx = full["companies"].index(old_name)
        full["companies"][idx] = new_name
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
# Sheet names detection
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