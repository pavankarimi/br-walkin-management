import os, smtplib, requests
from email.message import EmailMessage

def send_student_email(student, subject, message):
    host, user = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER")
    if not host or not user or not os.getenv("SMTP_PASSWORD"):
        return "Not configured"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", user)
    msg["To"] = student.email
    msg.set_content(f"Hello {student.full_name},\n\n{message}\n\nLogin to your BR Concepts Student Career Portal to view all updates.\n\nBR Concepts")
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as server:
        server.starttls(); server.login(user, os.getenv("SMTP_PASSWORD")); server.send_message(msg)
    return "Sent"

def send_student_whatsapp(student, title, message):
    token, phone_id = os.getenv("WA_ACCESS_TOKEN"), os.getenv("WA_PHONE_NUMBER_ID")
    template = os.getenv("WA_TEMPLATE_NAME", "br_student_update")
    if not token or not phone_id or not template: return "Not configured"
    digits = "".join(c for c in student.phone if c.isdigit())
    if len(digits) == 10: digits = "91" + digits
    body_text = f"{title}: {message}"
    payload = {"messaging_product":"whatsapp", "to":digits, "type":"template",
        "template":{"name":template,"language":{"code":os.getenv("WA_TEMPLATE_LANGUAGE","en_US")},
        "components":[{"type":"body","parameters":[{"type":"text","text":student.full_name},{"type":"text","text":body_text[:900]}]}]}}
    response = requests.post(f"https://graph.facebook.com/v21.0/{phone_id}/messages",
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}, json=payload, timeout=20)
    response.raise_for_status()
    return "Sent"
