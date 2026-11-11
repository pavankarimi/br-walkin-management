import os
import requests

def send_student_email(student, subject, message):
    script_url = os.getenv("GAS_EMAIL_URL")
    if not script_url:
        return "Not configured"
    
    payload = {
        "secret": os.getenv("GAS_SECRET_KEY", "BR_CONCEPTS_SECRET_KEY_2026"),
        "to": student.email,
        "student_name": getattr(student, 'full_name', 'Student'),
        "subject": subject,
        "message": message
    }
    
    try:
        response = requests.post(script_url, json=payload, timeout=20)
        res_data = response.json()
        if res_data.get("status") == "Sent":
            return "Sent"
        print(f"Apps Script Error: {res_data.get('message')}")
        return f"Failed – {res_data.get('message', 'Execution error')}"
    except Exception as e:
        print(f"Request Exception: {str(e)}")
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
    try:
        response = requests.post(
            f"https://graph.facebook.com/v21.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=20
        )
        response.raise_for_status()
        return "Sent"
    except Exception as e:
        return f"Failed – {str(e)}"
