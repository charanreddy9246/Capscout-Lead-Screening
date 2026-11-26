"""Sending the "set your password" email through the company's mail account (plain SMTP).

Nothing here ever raises into the request: it returns what happened, so the screen can say "sent" or
fall back to showing the link. The password and the link's token are never logged.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import Settings

log = logging.getLogger("mailer")


def configured(cfg: Settings) -> bool:
    return bool(cfg.smtp_host and cfg.smtp_user and cfg.smtp_password)


def build_invite(cfg: Settings, to: str, name: str, path: str, valid_hours: int) -> EmailMessage:
    link = cfg.app_url.rstrip("/") + path
    msg = EmailMessage()
    msg["Subject"] = f"Set your {cfg.smtp_from_name} password"
    msg["From"] = formataddr((cfg.smtp_from_name, cfg.smtp_from_email or cfg.smtp_user or ""))
    msg["To"] = to
    msg.set_content(
        f"Hi {name},\n\n"
        f"An account has been created for you on {cfg.smtp_from_name}.\n\n"
        f"Set your password here (the link works once and stops after {valid_hours} hours):\n{link}\n\n"
        f"After that, sign in with your email address, your mobile number and the password you chose.\n\n"
        f"If you were not expecting this, ignore this email."
    )
    msg.add_alternative(
        f"<p>Hi {_esc(name)},</p>"
        f"<p>An account has been created for you on {_esc(cfg.smtp_from_name)}.</p>"
        f'<p><a href="{_esc(link)}">Set your password</a><br>'
        f"<small>The link works once and stops after {valid_hours} hours.</small></p>"
        f"<p>After that, sign in with your email address, your mobile number and the password you chose.</p>"
        f"<p><small>If you were not expecting this, ignore this email.</small></p>",
        subtype="html",
    )
    return msg


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def send(cfg: Settings, msg: EmailMessage) -> str | None:
    """Send it. Returns None on success, or a short reason on failure (never the password)."""
    if not configured(cfg):
        return "Email is not set up on the server."
    try:
        if cfg.smtp_port == 465:
            smtp = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds)
        with smtp:
            if cfg.smtp_port != 465:
                smtp.starttls(context=ssl.create_default_context())
            smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
        return None
    except smtplib.SMTPAuthenticationError:
        log.warning("mail login was refused")
        return "The mail account refused the login. Check the app password."
    except (smtplib.SMTPException, OSError) as e:
        log.warning("mail send failed: %s", type(e).__name__)
        return "The email could not be sent. Check the mail settings and try again."


def send_invite(cfg: Settings, to: str | None, name: str, path: str, valid_hours: int) -> dict:
    """What the screen needs: {sent, to, error}."""
    if not to:
        return {"sent": False, "to": None, "error": "This person has no email address."}
    error = send(cfg, build_invite(cfg, to, name, path, valid_hours))
    return {"sent": error is None, "to": to, "error": error}
