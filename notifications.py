import os
import requests

def send_student_email(student, subject, message):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return "Not configured"
    
    sender = os.getenv("SMTP_FROM", "onboarding@resend.dev")
    
    payload = {
        "from": f"BR Concepts <{sender}>",
        "to": [student.email],
        "subject": subject,
        "text": (
            f"Hello {student.full_name},\n\n{message}\n\n"
            "Login to your BR Concepts Student Career Portal to view all updates.\n\nBR Concepts"
        )
    }
    
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=20
        )
        response.raise_for_status()
        return "Sent"
    except Exception as e:
        print(f"Resend API Error: {str(e)}")
        return f"Failed – {str(e)}"

def send_student_whatsapp(student, title, message):
    token, phone_id = os.getenv("WA_ACCESS_TOKEN"), os.getenv("WA_PHONE_NUMBER_ID")
    template = os.getenv("WA_TEMPLATE_NAME", "br_student_update")
    if not token or not phone_id or not template:
        return "Not configured"
    digits = "".join(c for c in student.phone if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    body_text = f"{title}: {message}"
    payload = {
        "messaging_product": "whatsapp",
        "to": digits,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": os.getenv("WA_TEMPLATE_LANGUAGE", "en_US")},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": student.full_name},
                    {"type": "text", "text": body_text[:900]}
                ]
            }]
        }
    }
    response = requests.post(
        f"https://graph.facebook.com/v21.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=20
    )
    response.raise_for_status()
    return "Sent"
