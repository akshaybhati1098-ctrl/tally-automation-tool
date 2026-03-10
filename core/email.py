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
    """Send a 6-digit OTP email using Resend API."""
    digit_cells = "".join([
        f'<td style="padding:0 4px;">'
        f'<div style="width:44px;height:54px;line-height:54px;text-align:center;'
        f'font-family:Courier New,monospace;font-size:1.7rem;font-weight:900;'
        f'color:#0d1117;background:#ffffff;border:2px solid #dce5f0;'
        f'border-radius:10px;">{d}</div>'
        f'</td>'
        for d in str(otp)
    ])

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f5f8fc;">
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:2rem auto;
                background:#ffffff;border-radius:20px;overflow:hidden;
                box-shadow:0 4px 24px rgba(0,20,60,0.10);">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#0d1117 60%,#1c2534);
                  padding:2.2rem 2rem 1.8rem;text-align:center;">
        <div style="display:inline-block;background:rgba(255,255,255,0.08);
                    border:1px solid rgba(255,255,255,0.14);border-radius:14px;
                    padding:0.5rem 0.8rem;font-size:1.6rem;margin-bottom:1rem;">🧾</div>
        <h1 style="color:#ffffff;font-size:1.25rem;font-weight:800;
                   margin:0 0 0.35rem;letter-spacing:-0.02em;">
          Verify your signup
        </h1>
        <p style="color:rgba(255,255,255,0.45);font-size:0.82rem;margin:0;">
          Tally Tool · Account creation
        </p>
      </div>

      <!-- Body -->
      <div style="padding:2rem 2rem 1.5rem;">

        <p style="color:#354460;font-size:0.9rem;line-height:1.6;margin:0 0 1.6rem;">
          Hi there! Enter the 6-digit code below in the signup form to verify
          your email address and create your account.
        </p>

        <!-- OTP digit boxes — table layout forces single row -->
        <div style="background:#f5f8fc;border:1.5px solid #dce5f0;border-radius:16px;
                    padding:1.6rem 1rem;text-align:center;margin-bottom:1.4rem;">
          <p style="color:#7a8fa8;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.08em;font-weight:700;margin:0 0 1rem;">
            Your one-time code
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0"
                 style="margin:0 auto;border-collapse:separate;border-spacing:0;">
            <tr>{digit_cells}</tr>
          </table>
          <div style="margin-top:1.1rem;display:inline-block;
                      background:rgba(22,81,232,0.07);border-radius:20px;
                      padding:0.3rem 0.9rem;">
            <span style="color:#1651e8;font-size:0.72rem;font-weight:700;">
              ⏱ Expires in 10 minutes
            </span>
          </div>
        </div>

        <!-- Security note -->
        <div style="background:#fff8ed;border:1.5px solid #fde68a;border-radius:12px;
                    padding:0.85rem 1rem;margin-bottom:1.4rem;">
          <p style="color:#92400e;font-size:0.78rem;margin:0;line-height:1.55;">
            🔒 <strong>Never share this code.</strong> Tally Tool will never ask for
            your OTP via phone or chat.
          </p>
        </div>

        <p style="color:#7a8fa8;font-size:0.76rem;text-align:center;
                   line-height:1.6;margin:0;">
          If you didn't request this, you can safely ignore this email.
        </p>
      </div>

      <!-- Footer -->
      <div style="background:#f5f8fc;border-top:1px solid #dce5f0;
                  padding:1rem 2rem;text-align:center;">
        <p style="color:#b0bec8;font-size:0.68rem;margin:0;">
          Tally Tool by Akshay · v3.3 &nbsp;·&nbsp;
          <a href="{BASE_URL}" style="color:#1651e8;text-decoration:none;">tallytool.in</a>
        </p>
      </div>

    </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": MAIL_FROM,
            "to": [to_email],
            "subject": "🔐 Your Tally Tool verification code",
            "html": html,
        }
        r = resend.Emails.send(params)
        print(f"✅ OTP email sent via Resend to {to_email}, ID: {r['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to send OTP email: {e}")
        return False


# ================================================================
# NEW: FORGOT USERNAME / PASSWORD EMAILS
# ================================================================
def send_username_reminder_email(to_email: str, username: str):
    """Send username reminder email."""
    letter_cells = "".join([
        f'<td style="padding:0 2px;">'
        f'<div style="padding:0.3rem 0.55rem;font-family:Courier New,monospace;'
        f'font-size:1.3rem;font-weight:800;color:#0d1117;background:#ffffff;'
        f'border:2px solid #dce5f0;border-radius:8px;white-space:nowrap;">{c}</div>'
        f'</td>'
        for c in str(username)
    ])

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f5f8fc;">
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:2rem auto;
                background:#ffffff;border-radius:20px;overflow:hidden;
                box-shadow:0 4px 24px rgba(0,20,60,0.10);">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#0d1117 60%,#1c2534);
                  padding:2.2rem 2rem 1.8rem;text-align:center;">
        <div style="display:inline-block;background:rgba(255,255,255,0.08);
                    border:1px solid rgba(255,255,255,0.14);border-radius:14px;
                    padding:0.5rem 0.8rem;font-size:1.6rem;margin-bottom:1rem;">👤</div>
        <h1 style="color:#ffffff;font-size:1.25rem;font-weight:800;
                   margin:0 0 0.35rem;letter-spacing:-0.02em;">
          Your username
        </h1>
        <p style="color:rgba(255,255,255,0.45);font-size:0.82rem;margin:0;">
          Tally Tool · Account recovery
        </p>
      </div>

      <!-- Body -->
      <div style="padding:2rem 2rem 1.5rem;">

        <p style="color:#354460;font-size:0.9rem;line-height:1.6;margin:0 0 1.6rem;">
          No worries! Here's the username linked to this email address.
          Use it to sign in below.
        </p>

        <!-- Username display — table layout forces single row -->
        <div style="background:#f5f8fc;border:1.5px solid #dce5f0;border-radius:16px;
                    padding:1.6rem 1rem;text-align:center;margin-bottom:1.4rem;">
          <p style="color:#7a8fa8;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.08em;font-weight:700;margin:0 0 1rem;">
            Your username
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0"
                 style="margin:0 auto;border-collapse:separate;border-spacing:0;">
            <tr>{letter_cells}</tr>
          </table>
        </div>

        <!-- CTA -->
        <a href="{BASE_URL}/login"
           style="display:block;background:linear-gradient(135deg,#1651e8,#3b29e8);
                  color:#ffffff;text-align:center;padding:0.9rem 1.5rem;
                  border-radius:12px;text-decoration:none;font-weight:700;
                  font-size:0.92rem;margin-bottom:1.4rem;">
          👤 Go to Sign In →
        </a>

        <p style="color:#7a8fa8;font-size:0.76rem;text-align:center;
                   line-height:1.6;margin:0;">
          If you didn't request this reminder, you can safely ignore this email.
        </p>
      </div>

      <!-- Footer -->
      <div style="background:#f5f8fc;border-top:1px solid #dce5f0;
                  padding:1rem 2rem;text-align:center;">
        <p style="color:#b0bec8;font-size:0.68rem;margin:0;">
          Tally Tool by Akshay · v3.3 &nbsp;·&nbsp;
          <a href="{BASE_URL}" style="color:#1651e8;text-decoration:none;">tallytool.in</a>
        </p>
      </div>

    </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": MAIL_FROM,
            "to": [to_email],
            "subject": "Your Tally Tool Username",
            "html": html,
        }
        email = resend.Emails.send(params)
        print(f"✅ Username reminder sent to {to_email}, ID: {email['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to send username reminder: {e}")
        return False


def send_password_reset_email(to_email: str, reset_link: str):
    """Send password reset link."""
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f5f8fc;">
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:2rem auto;
                background:#ffffff;border-radius:20px;overflow:hidden;
                box-shadow:0 4px 24px rgba(0,20,60,0.10);">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#0d1117 60%,#1c2534);
                  padding:2.2rem 2rem 1.8rem;text-align:center;">
        <div style="display:inline-block;background:rgba(255,255,255,0.08);
                    border:1px solid rgba(255,255,255,0.14);border-radius:14px;
                    padding:0.5rem 0.8rem;font-size:1.6rem;margin-bottom:1rem;">🔑</div>
        <h1 style="color:#ffffff;font-size:1.25rem;font-weight:800;
                   margin:0 0 0.35rem;letter-spacing:-0.02em;">
          Reset your password
        </h1>
        <p style="color:rgba(255,255,255,0.45);font-size:0.82rem;margin:0;">
          Tally Tool · Account security
        </p>
      </div>

      <!-- Body -->
      <div style="padding:2rem 2rem 1.5rem;">

        <p style="color:#354460;font-size:0.9rem;line-height:1.6;margin:0 0 1.6rem;">
          We received a request to reset the password for your Tally Tool account.
          Click the button below to choose a new password.
        </p>

        <!-- Reset CTA -->
        <a href="{reset_link}"
           style="display:block;background:linear-gradient(135deg,#1651e8,#3b29e8);
                  color:#ffffff;text-align:center;padding:1rem 1.5rem;
                  border-radius:12px;text-decoration:none;font-weight:700;
                  font-size:0.95rem;margin-bottom:1.4rem;
                  box-shadow:0 4px 14px rgba(22,81,232,0.35);">
          🔑 Reset My Password →
        </a>

        <!-- Expiry pill -->
        <div style="text-align:center;margin-bottom:1.4rem;">
          <div style="display:inline-block;background:rgba(239,68,68,0.07);
                      border:1px solid rgba(239,68,68,0.18);border-radius:20px;
                      padding:0.3rem 1rem;">
            <span style="color:#b91c1c;font-size:0.75rem;font-weight:700;">
              ⏱ Link expires in 1 hour
            </span>
          </div>
        </div>

        <!-- Fallback link -->
        <div style="background:#f5f8fc;border:1.5px solid #dce5f0;border-radius:12px;
                    padding:0.9rem 1rem;margin-bottom:1.4rem;">
          <p style="color:#7a8fa8;font-size:0.73rem;margin:0 0 0.4rem;font-weight:700;
                     text-transform:uppercase;letter-spacing:0.06em;">
            Button not working?
          </p>
          <p style="color:#354460;font-size:0.73rem;margin:0;word-break:break-all;line-height:1.5;">
            Copy and paste this link into your browser:<br>
            <a href="{reset_link}" style="color:#1651e8;text-decoration:none;">{reset_link}</a>
          </p>
        </div>

        <!-- Security note -->
        <div style="background:#fff8ed;border:1.5px solid #fde68a;border-radius:12px;
                    padding:0.85rem 1rem;margin-bottom:1.4rem;">
          <p style="color:#92400e;font-size:0.78rem;margin:0;line-height:1.55;">
            🔒 <strong>Didn't request this?</strong> Your password will not change
            unless you click the link above. You can safely ignore this email.
          </p>
        </div>

        <p style="color:#7a8fa8;font-size:0.76rem;text-align:center;
                   line-height:1.6;margin:0;">
          For security, this link can only be used once.
        </p>
      </div>

      <!-- Footer -->
      <div style="background:#f5f8fc;border-top:1px solid #dce5f0;
                  padding:1rem 2rem;text-align:center;">
        <p style="color:#b0bec8;font-size:0.68rem;margin:0;">
          Tally Tool by Akshay · v3.3 &nbsp;·&nbsp;
          <a href="{BASE_URL}" style="color:#1651e8;text-decoration:none;">tallytool.in</a>
        </p>
      </div>

    </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": MAIL_FROM,
            "to": [to_email],
            "subject": "Reset your Tally Tool password",
            "html": html,
        }
        email = resend.Emails.send(params)
        print(f"✅ Password reset email sent to {to_email}, ID: {email['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to send password reset email: {e}")
        return False


def send_welcome_email(to_email: str, username: str):
    """Send a welcome email after successful account creation."""
    login_url = f"{BASE_URL}/login"

    letter_cells = "".join([
        f'<td style="padding:0 2px;">'
        f'<div style="padding:0.3rem 0.55rem;font-family:Courier New,monospace;'
        f'font-size:1.3rem;font-weight:800;color:#0d1117;background:#ffffff;'
        f'border:2px solid #dce5f0;border-radius:8px;white-space:nowrap;">{c}</div>'
        f'</td>'
        for c in str(username)
    ])

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f5f8fc;">
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:2rem auto;
                background:#ffffff;border-radius:20px;overflow:hidden;
                box-shadow:0 4px 24px rgba(0,20,60,0.10);">

      <!-- Header with celebration gradient -->
      <div style="background:linear-gradient(135deg,#0d1117 60%,#1c2534);
                  padding:2.2rem 2rem 1.8rem;text-align:center;position:relative;">
        <div style="display:inline-block;background:rgba(255,255,255,0.08);
                    border:1px solid rgba(255,255,255,0.14);border-radius:14px;
                    padding:0.5rem 0.8rem;font-size:1.6rem;margin-bottom:1rem;">🎉</div>
        <h1 style="color:#ffffff;font-size:1.3rem;font-weight:800;
                   margin:0 0 0.35rem;letter-spacing:-0.02em;">
          Welcome to Tally Tool!
        </h1>
        <p style="color:rgba(255,255,255,0.45);font-size:0.82rem;margin:0;">
          Your account is ready · v3.3
        </p>
      </div>

      <!-- Green success banner -->
      <div style="background:linear-gradient(135deg,#17b26a,#0e9456);
                  padding:0.85rem 2rem;text-align:center;">
        <p style="color:#ffffff;font-size:0.82rem;font-weight:700;margin:0;
                   letter-spacing:0.01em;">
          ✅ Account created successfully
        </p>
      </div>

      <!-- Body -->
      <div style="padding:2rem 2rem 1.5rem;">

        <p style="color:#354460;font-size:0.9rem;line-height:1.6;margin:0 0 1.6rem;">
          Hi <strong style="color:#0d1117;">{username}</strong>! You're all set.
          Start converting Excel invoices to Tally XML in seconds — no setup required.
        </p>

        <!-- Username card — table layout forces single row -->
        <div style="background:#f5f8fc;border:1.5px solid #dce5f0;border-radius:16px;
                    padding:1.5rem 1rem;text-align:center;margin-bottom:1.4rem;">
          <p style="color:#7a8fa8;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.08em;font-weight:700;margin:0 0 0.9rem;">
            Your username — save this
          </p>
          <table role="presentation" cellpadding="0" cellspacing="0"
                 style="margin:0 auto;border-collapse:separate;border-spacing:0;">
            <tr>{letter_cells}</tr>
          </table>
          <p style="color:#7a8fa8;font-size:0.73rem;margin:0.75rem 0 0;line-height:1.5;">
            Use this with your password to sign in.
          </p>
        </div>

        <!-- Feature highlights -->
        <div style="margin-bottom:1.4rem;">
          <p style="color:#7a8fa8;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.08em;font-weight:700;margin:0 0 0.75rem;">
            What you can do now
          </p>
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="padding:0.55rem 0;vertical-align:top;width:32px;">
                <span style="display:inline-block;width:28px;height:28px;
                             background:rgba(22,81,232,0.08);border-radius:8px;
                             text-align:center;line-height:28px;font-size:0.85rem;">⚡</span>
              </td>
              <td style="padding:0.55rem 0 0.55rem 0.6rem;vertical-align:middle;">
                <span style="color:#0d1117;font-size:0.84rem;font-weight:600;">Convert invoices instantly</span><br>
                <span style="color:#7a8fa8;font-size:0.75rem;">Upload Excel → get Tally XML in seconds</span>
              </td>
            </tr>
            <tr>
              <td style="padding:0.55rem 0;vertical-align:top;width:32px;">
                <span style="display:inline-block;width:28px;height:28px;
                             background:rgba(22,81,232,0.08);border-radius:8px;
                             text-align:center;line-height:28px;font-size:0.85rem;">🔧</span>
              </td>
              <td style="padding:0.55rem 0 0.55rem 0.6rem;vertical-align:middle;">
                <span style="color:#0d1117;font-size:0.84rem;font-weight:600;">Save ledger mappings</span><br>
                <span style="color:#7a8fa8;font-size:0.75rem;">Map once, reuse forever across sessions</span>
              </td>
            </tr>
            <tr>
              <td style="padding:0.55rem 0;vertical-align:top;width:32px;">
                <span style="display:inline-block;width:28px;height:28px;
                             background:rgba(22,81,232,0.08);border-radius:8px;
                             text-align:center;line-height:28px;font-size:0.85rem;">📊</span>
              </td>
              <td style="padding:0.55rem 0 0.55rem 0.6rem;vertical-align:middle;">
                <span style="color:#0d1117;font-size:0.84rem;font-weight:600;">GST-compliant output</span><br>
                <span style="color:#7a8fa8;font-size:0.75rem;">CGST / SGST / IGST · TallyPrime & ERP9</span>
              </td>
            </tr>
          </table>
        </div>

        <!-- CTA -->
        <a href="{login_url}"
           style="display:block;background:linear-gradient(135deg,#1651e8,#3b29e8);
                  color:#ffffff;text-align:center;padding:1rem 1.5rem;
                  border-radius:12px;text-decoration:none;font-weight:700;
                  font-size:0.95rem;margin-bottom:1.4rem;
                  box-shadow:0 4px 14px rgba(22,81,232,0.35);">
          Go to Sign In →
        </a>

        <p style="color:#7a8fa8;font-size:0.76rem;text-align:center;
                   line-height:1.6;margin:0;">
          If you didn't create this account, please contact us immediately.
        </p>
      </div>

      <!-- Footer -->
      <div style="background:#f5f8fc;border-top:1px solid #dce5f0;
                  padding:1rem 2rem;text-align:center;">
        <p style="color:#b0bec8;font-size:0.68rem;margin:0;">
          Tally Tool by Akshay · v3.3 &nbsp;·&nbsp;
          <a href="{BASE_URL}" style="color:#1651e8;text-decoration:none;">tallytool.in</a>
        </p>
      </div>

    </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": MAIL_FROM,
            "to": [to_email],
            "subject": "🎉 Welcome to Tally Tool!",
            "html": html,
        }
        email = resend.Emails.send(params)
        print(f"✅ Welcome email sent to {to_email}, ID: {email['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to send welcome email: {e}")
        return False