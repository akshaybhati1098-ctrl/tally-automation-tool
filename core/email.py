# core/email.py
import os
import resend
from itsdangerous import URLSafeTimedSerializer

# ── Config ─────────────────────────────────────────────────────
SECRET_KEY    = os.environ.get("SECRET_KEY", "change-this")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
MAIL_FROM     = os.environ.get("MAIL_FROM", "onboarding@resend.dev")  # Resend test sender
BASE_URL      = os.environ.get("BASE_URL", "http://localhost:8000")

# Initialize Resend
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
else:
    print("⚠️  RESEND_API_KEY not set. Email sending will fail.")

_serializer = URLSafeTimedSerializer(SECRET_KEY)

# ================================================================
# TOKEN HELPERS (used for legacy link verification)
# ================================================================
def generate_token(email: str) -> str:
    """Generate a signed token for email verification."""
    return _serializer.dumps(email, salt="email-verify")

def decode_token(token: str, max_age: int = 86400) -> str:
    """Decode a token. Raises SignatureExpired or BadSignature on failure."""
    return _serializer.loads(token, salt="email-verify", max_age=max_age)

# ================================================================
# EMAIL SENDING FUNCTIONS (Resend API)
# ================================================================
def send_verification_email(to_email: str, token: str, code: str = None):
    """
    Send a verification email with a link and optional code.
    This function is kept for compatibility with the legacy flow,
    but the OTP flow uses send_otp_email() instead.
    """
    verify_url = f"{BASE_URL}/verify-email/{token}"
    code_html = ""
    if code:
        code_html = f"""
        <div style="text-align:center;margin:1.5rem 0;">
          <p style="color:#7a8fa8;font-size:0.8rem;">Or enter this code on the website:</p>
          <div style="font-family:monospace;font-size:2rem;font-weight:700;
                      letter-spacing:0.5rem;background:#f5f8fc;padding:0.75rem;
                      border-radius:12px;border:1px solid #dce5f0;color:#0d1117;">
            {code}
          </div>
        </div>
        """

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;">
      <div style="background:#0d1117;border-radius:16px;padding:2rem;
                  text-align:center;margin-bottom:1.5rem;">
        <span style="font-size:2rem;">🧾</span>
        <h2 style="color:#fff;font-size:1.3rem;margin:0.75rem 0 0.3rem;">
          Verify your email
        </h2>
        <p style="color:rgba(255,255,255,0.5);font-size:0.88rem;margin:0;">
          Click the button or enter the code below
        </p>
      </div>

      <a href="{verify_url}"
         style="display:block;background:linear-gradient(135deg,#1651e8,#3b29e8);
                color:#fff;text-align:center;padding:0.9rem 1.5rem;
                border-radius:12px;text-decoration:none;font-weight:700;
                font-size:0.95rem;margin-bottom:1.5rem;">
        ✅ Verify my email
      </a>

      {code_html}

      <p style="color:#7a8fa8;font-size:0.78rem;text-align:center;line-height:1.6;">
        This link and code expire in <strong>24 hours</strong>.<br>
        If you did not sign up for Tally Tool, you can safely ignore this.
      </p>

      <hr style="border:none;border-top:1px solid #dce5f0;margin:1.5rem 0;">
      <p style="color:#b0bec8;font-size:0.7rem;text-align:center;">
        Tally Tool by Akshay · v3.3
      </p>
    </div>
    """

    try:
        params = {
            "from": MAIL_FROM,
            "to": [to_email],
            "subject": "✅ Verify your Tally Tool account",
            "html": html,
        }
        r = resend.Emails.send(params)
        print(f"✅ Verification email sent via Resend to {to_email}, ID: {r['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to send verification email: {e}")
        return False


def send_otp_email(to_email: str, otp: str):
    """Send a 6‑digit OTP email using Resend API."""
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:2rem;">
      <div style="background:#0d1117;border-radius:16px;padding:2rem;text-align:center;">
        <span style="font-size:2rem;">🧾</span>
        <h2 style="color:#fff;font-size:1.3rem;margin:0.75rem 0 0.3rem;">
          Your OTP Code
        </h2>
        <p style="color:rgba(255,255,255,0.5);font-size:0.88rem;">
          Use the code below to complete your signup
        </p>
      </div>

      <div style="text-align:center;margin:2rem 0;">
        <div style="font-family:monospace;font-size:2.5rem;font-weight:700;
                    letter-spacing:0.5rem;background:#f5f8fc;padding:1rem;
                    border-radius:12px;border:1px solid #dce5f0;color:#0d1117;">
          {otp}
        </div>
        <p style="color:#7a8fa8;font-size:0.8rem;margin-top:1rem;">
          This code expires in 10 minutes.
        </p>
      </div>

      <hr style="border:none;border-top:1px solid #dce5f0;margin:1.5rem 0;">
      <p style="color:#b0bec8;font-size:0.7rem;text-align:center;">
        Tally Tool by Akshay · v3.3
      </p>
    </div>
    """

    try:
        params = {
            "from": MAIL_FROM,
            "to": [to_email],
            "subject": "🔐 Your Tally Tool OTP Code",
            "html": html,
        }
        r = resend.Emails.send(params)
        print(f"✅ OTP email sent via Resend to {to_email}, ID: {r['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to send OTP email: {e}")
        return False