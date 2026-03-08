# ================================================================
#  core/email_verification.py
#
#  SAVE THIS FILE AT:
#      core/email_verification.py          ← same folder as excel_service.py
#
#  INSTALL (add to requirements.txt):
#      itsdangerous
#
#  ENV VARIABLES (add to Render → Environment):
#      MAIL_USERNAME   your@gmail.com
#      MAIL_PASSWORD   your-gmail-app-password   (Google App Password)
#      MAIL_FROM       your@gmail.com
#      BASE_URL        https://your-app.onrender.com
#
#  SECRET_KEY already exists in your app.py — reused here automatically.
# ================================================================

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# ── Config (mirrors app.py pattern — all from env) ──────────────
DATABASE_URL  = os.environ.get("DATABASE_URL")
SECRET_KEY    = os.environ.get("SECRET_KEY", "change-this")   # same var as app.py
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_FROM     = os.environ.get("MAIL_FROM", MAIL_USERNAME)
MAIL_SERVER   = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT     = int(os.environ.get("MAIL_PORT", "587"))
BASE_URL      = os.environ.get("BASE_URL", "http://localhost:8000")

# ── Token serializer ────────────────────────────────────────────
_serializer = URLSafeTimedSerializer(SECRET_KEY)

# ── Router — registered in app.py with app.include_router() ────
router = APIRouter()


# ================================================================
#  DB HELPER  (mirrors get_db_connection in app.py exactly)
#  Kept here to avoid a circular import.
# ================================================================
def _get_conn():
    return psycopg2.connect(DATABASE_URL)


# ================================================================
#  MIGRATION
#  Called once at startup from app.py (right after init_user_db).
#  Adds 4 new columns to the existing users table — safe to re-run.
# ================================================================
def migrate_users_table():
    conn = _get_conn()
    cur  = conn.cursor()
    for sql in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email              TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified        BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_created_at   TIMESTAMP",
    ]:
        try:
            cur.execute(sql)
        except Exception as e:
            print(f"[MIGRATION] Skipped: {e}")
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Email-verification columns ready in PostgreSQL")


# ================================================================
#  TOKEN HELPERS
# ================================================================
def generate_token(email: str) -> str:
    return _serializer.dumps(email, salt="email-verify")


def decode_token(token: str, max_age: int = 86400) -> str:
    """Returns email on success. Raises SignatureExpired / BadSignature."""
    return _serializer.loads(token, salt="email-verify", max_age=max_age)


# ================================================================
#  DB HELPERS (email-verification specific)
# ================================================================
def _get_user_by_email(email: str):
    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close(); conn.close()
    return user


def _save_token(email: str, token: str):
    conn = _get_conn()
    cur  = conn.cursor()
    cur.execute(
        """UPDATE users
              SET verification_token = %s,
                  token_created_at   = %s
            WHERE email = %s""",
        (token, datetime.utcnow(), email),
    )
    conn.commit()
    cur.close(); conn.close()


def _mark_verified(email: str):
    conn = _get_conn()
    cur  = conn.cursor()
    cur.execute(
        """UPDATE users
              SET is_verified        = TRUE,
                  verification_token = NULL,
                  token_created_at   = NULL
            WHERE email = %s""",
        (email,),
    )
    conn.commit()
    cur.close(); conn.close()


# ================================================================
#  EMAIL SENDER  (plain smtplib — no extra packages needed)
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
#  PUBLIC HELPERS — called from app.py
# ================================================================
def register_and_send(email: str, token: str):
    """
    Store the token in the DB then fire the email.
    Called from the signup POST route in app.py after create_user().
    """
    _save_token(email, token)
    send_verification_email(email, token)


def check_verified(user: dict) -> bool:
    """
    Returns True  → allow login.
    Returns False → block login, ask user to verify email.

    Users created before this feature have is_verified = NULL.
    NULL is treated as True so existing accounts are never locked out.
    """
    v = user.get("is_verified")
    return v is None or v is True


# ================================================================
#  ROUTES  (registered via app.include_router(router) in app.py)
# ================================================================

@router.get("/verify-email/{token}")
async def verify_email_route(token: str, request: Request):
    """User clicks the link in their inbox → marks account verified."""
    from app import templates  # late import avoids circular dependency

    try:
        email = decode_token(token)
    except SignatureExpired:
        return templates.TemplateResponse("pages/signup.html", {
            "request": request,
            "flashes": [{"category": "error",
                         "message": "Verification link expired. Please sign up again."}],
        })
    except BadSignature:
        return templates.TemplateResponse("pages/signup.html", {
            "request": request,
            "flashes": [{"category": "error",
                         "message": "Invalid verification link."}],
        })

    _mark_verified(email)
    return RedirectResponse("/login?verified=1", status_code=302)


@router.post("/resend-verification")
async def resend_verification_route(email: str = Form(...)):
    """Called by the resend button on the verify-pending page."""
    user = _get_user_by_email(email)

    if not user:
        return JSONResponse({"status": "ok"})  # silent — don't reveal existence

    if user.get("is_verified"):
        return JSONResponse({"status": "already_verified"})

    token = generate_token(email)
    try:
        register_and_send(email, token)
    except Exception as e:
        print(f"[RESEND ERROR] {e}")
        return JSONResponse({"status": "error"}, status_code=500)

    return JSONResponse({"status": "ok"})
