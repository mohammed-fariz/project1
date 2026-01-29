# mcp_server.py
import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

FROM_EMAIL = os.getenv("GMAIL_FROM_EMAIL")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

mcp = FastMCP(
    name="utility-tools",
    host="127.0.0.1",
    port=3333   # MCP HTTP PORT
)

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def send_leave_email(to_email: str, subject: str, body: str) -> str:
    """Send an email via Gmail SMTP"""

    if not FROM_EMAIL or not APP_PASSWORD:
        return "❌ Email credentials not set"

    msg = MIMEText(body)
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(FROM_EMAIL, APP_PASSWORD)
        smtp.send_message(msg)

    return f"✅ Email sent to {to_email}"

if __name__ == "__main__":
    mcp.run_http()
