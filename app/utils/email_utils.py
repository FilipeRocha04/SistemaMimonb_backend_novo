import os
from app.utils.email import send_verification_email_sync, send_reset_email_sync, build_reset_email
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

def send_verification_email_sync(to_email: str, token: str):
    verify_url = f"{FRONTEND_URL}/verify?token={token}"
    msg = build_verification_email(to_email, verify_url)
    asyncio.run(_send_message(msg))


def send_reset_email_sync(to_email: str, token: str):
    reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
    msg = build_reset_email(to_email, reset_url)
    asyncio.run(_send_message(msg))
