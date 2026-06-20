from fastapi import FastAPI, Depends, Form, Request
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware  # optional if using sessions
from database import get_db, init_db
from auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
)
import secrets
import sqlite3

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Initialize database on startup
@app.on_event("startup")
def startup():
    init_db()

# ---------- AUTH ROUTES ----------
@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
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
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password, is_active) VALUES (?, ?, 1)",
                (username, hashed)
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return templates.TemplateResponse(
            "pages/register.html",
            {"request": request, "error": "Username already taken"}
        )

    # Redirect to login with success message
    response = RedirectResponse(url="/login?registered=1", status_code=302)
    return response

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    with get_db() as conn:
        # Explicit column selections ensure accurate index matching regardless of database configuration
        user = conn.execute(
            "SELECT id, username, password, is_active FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not user:
        return templates.TemplateResponse(
            "pages/login.html",
            {"request": request, "error": "Invalid username or password"}
        )

    # 🔥 SECURITY GUARD BLOCK: Intercept suspended user nodes immediately
    # Supports dictionary rows or traditional index tuples (where is_active is the 4th column)
    is_active_val = user["is_active"] if isinstance(user, dict) else user[3]
    if is_active_val == 0 or is_active_val is False:
        return templates.TemplateResponse(
            "pages/login.html",
            {"request": request, "error": "Your account has been suspended. Please contact support."}
        )

    password_hash = user["password"] if isinstance(user, dict) else user[2]
    if not verify_password(password, password_hash):
        return templates.TemplateResponse(
            "pages/login.html",
            {"request": request, "error": "Invalid username or password"}
        )

    # Create JWT token
    user_id = user["id"] if isinstance(user, dict) else user[0]
    user_name = user["username"] if isinstance(user, dict) else user[1]
    token = create_access_token(data={"sub": str(user_id), "username": user_name})

    # Set cookie and redirect to dashboard
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=False,   
        samesite="lax"  
    )
    return response

@app.post("/logout")
async def logout_post():
    response = JSONResponse({"message": "logged out"})
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return response

# ---------- PROTECTED PAGE EXAMPLE ----------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        "pages/dashboard.html",
        {"request": request, "username": user["username"]}
    )

# ---------- PUBLIC PAGES ----------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, registered: int = 0):
    return templates.TemplateResponse(
        "pages/login.html",
        {
            "request": request,
            "success": "Registration successful! Please log in." if registered else None
        }
    )

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("pages/register.html", {"request": request})

@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    try:
        user = await get_current_user(request)
    except:
        user = None

    request.state.user = user
    response = await call_next(request)
    return response