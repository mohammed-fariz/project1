
import os
import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
from token_store import get_user_token
 

load_dotenv()

mcp = FastMCP("utility-tools")

@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b


@mcp.tool()
def send_gmail_oauth(token: dict, to_email: str, subject: str, body: str):

   

    creds = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    service = build("gmail", "v1", credentials=creds)

    msg = MIMEText(body)
    msg["To"] = to_email
    msg["Subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    return "✅ Email sent successfully!"

if __name__ == "__main__":
    mcp.run(transport="http", host="localhost", port=3333)