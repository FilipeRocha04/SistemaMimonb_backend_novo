
import os
import asyncio
from email.message import EmailMessage
from typing import Optional
import aiosmtplib
import logging

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_FROM = os.environ.get("SMTP_FROM") or SMTP_USER
SMTP_SSL = os.environ.get("SMTP_SSL", "true").lower() in ("1", "true", "yes")
logger = logging.getLogger("email")

async def _send_message(message: EmailMessage):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        logger.error("SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASS)")
        raise RuntimeError("SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASS)")
    use_tls = SMTP_SSL or SMTP_PORT == 465
    start_tls = not use_tls and SMTP_PORT in (587, 25)
    logger.info(f"Enviando e-mail para {message['To']} via {SMTP_HOST}:{SMTP_PORT} TLS={use_tls} STARTTLS={start_tls}")
    try:
        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=start_tls,
            use_tls=use_tls,
        )
        logger.info(f"E-mail enviado para {message['To']} com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail para {message['To']}: {e}")
        raise

def build_reset_email(to_email: str, reset_url: str, subject: Optional[str] = None) -> EmailMessage:
    subject = subject or "Redefinir senha - Mimonb"
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    plain = (
        f"Olá,\n\nRecebemos uma solicitação para redefinir sua senha. Clique no link abaixo para definir uma nova senha:\n\n{reset_url}\n\n"
        "Se você não solicitou esta alteração, ignore este e-mail.\n\nAtenciosamente,\nMimonb"
    )
    html = f"""
    <html>
        <body style='font-family: Arial, sans-serif; color: #111827;'>
            <div style='max-width:600px;margin:0 auto;padding:24px;background:#fff;border-radius:8px;'>
                <h2 style='color:#0f172a;'>Redefinir senha</h2>
                <p>Olá,</p>
                <p>Recebemos uma solicitação para redefinir a senha da sua conta. Clique no botão abaixo para escolher uma nova senha. Este link expira em 1 hora.</p>
                <div style='text-align:center;margin:20px 0;'>
                    <a href='{reset_url}' style='display:inline-block;padding:12px 20px;background:#ef4444;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;'>Redefinir senha</a>
                </div>
                <p style='color:#6b7280;font-size:13px;'>Se você não solicitou esta alteração, ignore este e-mail.</p>
                <hr style='margin:20px 0;border:none;border-top:1px solid #e6e6e6;' />
                <div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'>
                    <img src='https://drive.google.com/uc?export=view&id=1AhTRBV5LwPswHhBfJRTd3yA3tVWku9-z' alt='Logo Mimonb' style='max-width:40px;'/>
                    <span style='color:#9ca3af;font-size:14px;'>Atenciosamente,<br/>Mimonb</span>
                </div>
            </div>
        </body>
    </html>
    """
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html", charset="utf-8")
    return msg

def build_verification_email(to_email: str, verify_url: str, subject: Optional[str] = None) -> EmailMessage:
    subject = subject or "Verifique seu e-mail - Mimonb"
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    plain = (
        f"Olá,\n\nPor favor verifique seu e-mail clicando no link abaixo:\n\n{verify_url}\n\n"
        "Se você não solicitou este e-mail, ignore.\n\nAtenciosamente,\nMimonb"
    )
    html = f"""
    <html>
        <body style='font-family: Arial, sans-serif; color: #111827;'>
            <div style='max-width:600px;margin:0 auto;padding:24px;background:#fff;border-radius:8px;'>
                <h2 style='color:#0f172a;'>Verifique seu e-mail</h2>
                <p>Olá,</p>
                <p>Por favor confirme seu e-mail clicando no botão abaixo. Este link expira em 24 horas.</p>
                <div style='text-align:center;margin:20px 0;'>
                    <a href='{verify_url}' style='display:inline-block;padding:12px 20px;background:#0ea5a4;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;'>Verificar e-mail</a>
                </div>
                <p style='color:#6b7280;font-size:13px;'>Se você não solicitou este e-mail, ignore esta mensagem.</p>
                <hr style='margin:20px 0;border:none;border-top:1px solid #e6e6e6;' />
                <div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'>
                    <img src='https://drive.google.com/uc?export=view&id=1AhTRBV5LwPswHhBfJRTd3yA3tVWku9-z' alt='Logo Mimonb' style='max-width:40px;'/>
                    <span style='color:#9ca3af;font-size:14px;'>Atenciosamente,<br/>Mimonb</span>
                </div>
            </div>
        </body>
    </html>
    """
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html", charset="utf-8")
    return msg

def send_reset_email_sync(to_email: str, reset_url: str):
    # Garante que o reset_url seja sempre a URL completa
    if not reset_url.startswith("http"):
        reset_url = f"http://localhost:8080/reset-password?token={reset_url}"
    msg = build_reset_email(to_email, reset_url)
    try:
        asyncio.run(_send_message(msg))
    except RuntimeError as e:
        logger.warning(f"Reset email skipped: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to send reset email: {e}")
        return

def send_verification_email_sync(to_email: str, verify_url: str):
    # Garante que o verify_url seja sempre a URL completa
    if not verify_url.startswith("http"):
        verify_url = f"http://localhost:8080/verify?token={verify_url}"
    msg = build_verification_email(to_email, verify_url)
    try:
        asyncio.run(_send_message(msg))
    except RuntimeError as e:
        logger.warning(f"Verification email skipped: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        return
