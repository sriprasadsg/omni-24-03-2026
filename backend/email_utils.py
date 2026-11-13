"""
Asynchronous email utility using aiosmtplib.
"""

import os
import logging
from email.message import EmailMessage
import aiosmtplib

logger = logging.getLogger(__name__)


async def send_email_async(
    to_email: str | list[str],
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> bool:
    """
    Send an asynchronous email via SMTP.
    """
    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM_EMAIL", "noreply@omni-platform.internal")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() in ("true", "1", "yes")
    start_tls = os.getenv("SMTP_STARTTLS", "true").lower() in ("true", "1", "yes")

    if not smtp_host:
        logger.warning("[Email] SMTP_HOST not configured. Email to %s skipped.", to_email)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(to_email) if isinstance(to_email, list) else to_email

    if body_text:
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(body_html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            use_tls=use_tls,
            start_tls=start_tls,
        )
        logger.info("[Email] Successfully sent email to %s (Subject: %s)", to_email, subject)
        return True
    except Exception as e:
        logger.error("[Email] Failed to send email to %s: %s", to_email, e)
        return False
