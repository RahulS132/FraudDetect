"""Pluggable email service.

When SMTP is configured (``SMTP_HOST`` + ``SMTP_USER`` set in ``.env``) emails
are sent over SMTP. Otherwise the service runs in **dev mode**: it logs the
message (including any OTP) to the console and reports ``dev=True`` so callers
can echo the code back in the API response for local testing. This means the
verification / 2FA flows are fully functional with zero configuration, and
become real emails the moment SMTP credentials are added — no code change.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional, Dict, Any

from config import get_settings

settings = get_settings()


def is_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


def send_email(to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> Dict[str, Any]:
    """Send an email. Returns {"sent": bool, "dev": bool, "error": str?}."""
    if not is_configured():
        print("\n" + "=" * 60)
        print(f"[email:dev] (SMTP not configured — logging instead of sending)")
        print(f"  To:      {to}")
        print(f"  Subject: {subject}")
        print(f"  Body:    {body_text}")
        print("=" * 60 + "\n")
        return {"sent": False, "dev": True}

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        if settings.SMTP_USE_TLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                  context=ssl.create_default_context(), timeout=15) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        return {"sent": True, "dev": False}
    except Exception as e:  # pragma: no cover - network dependent
        print(f"[email] send failed: {e}")
        return {"sent": False, "dev": False, "error": str(e)}


_PURPOSE_LABEL = {
    "verify_email": "verify your email address",
    "login_2fa": "complete your sign-in",
}


def send_otp_email(to: str, code: str, purpose: str) -> Dict[str, Any]:
    label = _PURPOSE_LABEL.get(purpose, "verify your account")
    app = settings.APP_NAME
    subject = f"{app} verification code: {code}"
    text = (
        f"Your {app} verification code is {code}.\n\n"
        f"Use it to {label}. This code expires in {settings.OTP_EXP_MINUTES} minutes.\n\n"
        f"If you didn't request this, you can ignore this email."
    )
    html = f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#0f172a">{app}</h2>
      <p style="color:#334155">Use this code to {label}:</p>
      <div style="font-size:32px;font-weight:700;letter-spacing:8px;color:#2563eb;
                  background:#f1f5f9;padding:16px;border-radius:12px;text-align:center">{code}</div>
      <p style="color:#64748b;font-size:13px">This code expires in {settings.OTP_EXP_MINUTES} minutes.
         If you didn't request it, you can ignore this email.</p>
    </div>
    """
    return send_email(to, subject, text, html)
