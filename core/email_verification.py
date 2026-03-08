# ================================================================
#  core/email_verification.py
# ================================================================

import os
import smtplib
import ssl
import sqlite3
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# ── Config ─────────────────────────────────────────────────────
SECRET_KEY    = os.environ.get("SECRET_KEY", "change-this")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_FROM     = os.environ.get("MAIL_FROM", MAIL_USERNAME)
MAIL_SERVER   = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT     = int(os.environ.get("MAIL_PORT", "587"))
BASE_URL      = os.environ.get("BASE_URL", "http://localhost:8000")

# SQLite path
DB_PATH = "/data/users.db"

# ── Token serializer ───────────────────────────────────────────
_serializer = URLSafeTimedSerializer(SECRET_KEY)

# ── Router ─────────────────────────────────────────────────────
router = APIRouter()

# ================================================================
# TOKEN HELPERS
# ================================================================

def generate_token(email: str) -> str:
    return _serializer.dumps(email, salt="email-verify")


def decode_token(token: str, max_age: int = 86400) -> str:
    return _serializer.loads(token, salt="email-verify", max_age=max_age)


# ================================================================
# EMAIL SENDER
# ================================================================

def send_verification_email(to_email: str, token: str):

    verify_url = f"{BASE_URL}/verify-email/{token}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;">
      <div style="background:#0d1117;border-radius:16px;padding:2rem;
                  text-align:center;margin-bottom:1.5rem;">
        <span style="font-size:2rem;">🧾</span>
        <h2 style="color:#fff;font-size:1.3rem;margin:0.75rem 0 0.3rem;">
          Verify your email
        </h2>
        <p style="color:rgba(255,255,255,0.5);font-size:0.88rem;margin:0;">
          Click below to activate your Tally Tool account
        </p>
      </div>

      <a href="{verify_url}"
         style="display:block;background:linear-gradient(135deg,#1651e8,#3b29e8);
                color:#fff;text-align:center;padding:0.9rem 1.5rem;
                border-radius:12px;text-decoration:none;font-weight:700;
                font-size:0.95rem;margin-bottom:1.5rem;">
        ✅ Verify my email
      </a>

      <p style="color:#7a8fa8;font-size:0.78rem;text-align:center;line-height:1.6;">
        This link expires in <strong>24 hours</strong>.<br>
        If you did not sign up for Tally Tool, you can safely ignore this.
      </p>

      <hr style="border:none;border-top:1px solid #dce5f0;margin:1.5rem 0;">

      <p style="color:#b0bec8;font-size:0.7rem;text-align:center;">
        Tally Tool by Akshay · v3.3
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")

    msg["Subject"] = "✅ Verify your Tally Tool account"
    msg["From"]    = MAIL_FROM
    msg["To"]      = to_email

    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()

    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:

        server.ehlo()
        server.starttls(context=context)

        server.login(MAIL_USERNAME, MAIL_PASSWORD)

        server.sendmail(MAIL_FROM, to_email, msg.as_string())

    print(f"✅ Verification email sent → {to_email}")


# ================================================================
# PUBLIC HELPERS
# ================================================================

def register_and_send(email: str, token: str):
    """
    Send verification email
    """
    send_verification_email(email, token)


def check_verified(user: dict) -> bool:
    v = user.get("is_verified")
    return v is None or v == 1


# ================================================================
# ROUTES
# ================================================================

@router.get("/verify-email/{token}")
async def verify_email_route(token: str, request: Request):

    from app import templates

    try:

        email = decode_token(token)

    except SignatureExpired:

        return templates.TemplateResponse("pages/signup.html", {
            "request": request,
            "flashes": [{
                "category": "error",
                "message": "Verification link expired. Please sign up again."
            }]
        })

    except BadSignature:

        return templates.TemplateResponse("pages/signup.html", {
            "request": request,
            "flashes": [{
                "category": "error",
                "message": "Invalid verification link."
            }]
        })

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute(
        "UPDATE users SET is_verified=1 WHERE email=?",
        (email,)
    )

    conn.commit()
    conn.close()

    return RedirectResponse("/login?verified=1", status_code=302)


@router.post("/resend-verification")
async def resend_verification_route(email: str = Form(...)):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    )

    user = cur.fetchone()

    conn.close()

    if not user:
        return JSONResponse({"status": "ok"})

    if user["is_verified"] == 1:
        return JSONResponse({"status": "already_verified"})

    token = generate_token(email)

    try:

        register_and_send(email, token)

    except Exception as e:

        print(f"[RESEND ERROR] {e}")

        return JSONResponse({"status": "error"}, status_code=500)

    return JSONResponse({"status": "ok"})