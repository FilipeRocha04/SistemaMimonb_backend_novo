from app.utils.email import send_verification_email_sync, send_reset_email_sync

def send_verification_email(to_email: str, token: str):
    link = f"https://mimonb.com.br/verify?token={token}"
    send_verification_email_sync(to_email, link)

def send_reset_password_email(to_email: str, token: str):
    link = f"https://mimonb.com.br/reset-password?token={token}"
    send_reset_email_sync(to_email, link)
    <p>Se você não solicitou a redefinição, ignore este email.</p>
    """
    send_email(to_email, "Redefinição de senha - Mimonb", html)
