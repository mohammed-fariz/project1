import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from fastapi import HTTPException


def create_message(to, subject, body):
    message = MIMEText(body)

    message["to"] = to
    message["from"] = "me"
    message["subject"] = subject

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    return {"raw": raw_message}


def send_email(credentials, to, subject, body):
    try:
        service = build("gmail", "v1", credentials=credentials)

        message = create_message(to, subject, body)

        send_message = (
            service.users()
            .messages()
            .send(userId="me", body=message)
            .execute()
        )

        return send_message

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gmail sending failed: {str(e)}"
        )
