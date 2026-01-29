import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load env variables INSIDE MCP process
load_dotenv()

FROM_EMAIL = os.getenv("GMAIL_FROM_EMAIL")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

mcp = FastMCP("utility-tools")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

@mcp.tool()
def send_leave_email(to_email: str, subject: str, body: str) -> str:
    """Send a leave email using Gmail SMTP."""

    if not FROM_EMAIL or not APP_PASSWORD:
        return "❌ Gmail credentials missing. Check .env file."

    try:
        msg = MIMEText(body)
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(FROM_EMAIL, APP_PASSWORD)
            smtp.send_message(msg)

        return f"✅ Email sent successfully to {to_email}"

    except smtplib.SMTPAuthenticationError:
        return "❌ Gmail authentication failed. Check App Password."

    except Exception as e:
        return f"❌ Email send failed: {str(e)}"

if __name__ == "__main__":
    print("📡 MCP Email Server running...")
    mcp.run()
