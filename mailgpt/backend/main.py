from fastapi import FastAPI, Header, HTTPException
from dotenv import load_dotenv
import os

from schemas import EmailRequest
from gmail_service import send_email
from oauth import get_credentials


# --------------------------------------------------
# Load Environment Variables
# --------------------------------------------------
load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# Optional validation (good practice)
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise ValueError("Missing Google OAuth credentials in .env")


# --------------------------------------------------
# FastAPI App Initialization
# --------------------------------------------------
app = FastAPI(title="MailGPT Backend")


# --------------------------------------------------
# Email Sending Endpoint
# --------------------------------------------------
@app.post("/send_email")
async def send_mail(
    email: EmailRequest,
    authorization: str = Header(None)
):

    # Check OAuth Header
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing OAuth Token"
        )

    # Extract Bearer Token
    token = authorization.replace("Bearer ", "")

    # Get Google Credentials
    credentials = get_credentials(token)

    # Send Email
    result = send_email(
        credentials,
        email.to,
        email.subject,
        email.body
    )

    return {
        "status": "Email Sent Successfully",
        "message_id": result.get("id")
    }
