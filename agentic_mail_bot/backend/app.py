
import os
import re
import json
from typing import TypedDict, Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from contextlib import asynccontextmanager
from urllib.parse import urlencode, quote
import requests

from dotenv import load_dotenv
from fastmcp import Client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage,AIMessage
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langgraph.graph import StateGraph, END

from token_store import get_user_token, save_user_token,delete_user_token


# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()


# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI(title="Agentic Multi-User Gmail Bot")
templates = Jinja2Templates(directory="templates")



llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest",
    temperature=0
)

search_tool = DuckDuckGoSearchAPIWrapper()
MCP_URL = "http://mcp:3333/mcp"
mcp_client: Client | None = None


# --------------------------------------------------
# MCP LIFESPAN
# --------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_client
    mcp_client = Client(MCP_URL)
    await mcp_client.__aenter__()
    yield
    await mcp_client.__aexit__(None, None, None)


app.router.lifespan_context = lifespan

SESSION_MEMORY={}
EMAIL_DRAFTS={}
MAX_HISTORY=20

class ChatRequest(BaseModel):
    message: str
    user_id: str
    session_id:str
# --------------------------------------------------
# UI
# --------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


# --------------------------------------------------
# GOOGLE OAUTH
# --------------------------------------------------
@app.get("/auth/google")
def google_login(user_id: str):
    params = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "response_type": "code",
        "scope": (
            "https://www.googleapis.com/auth/gmail.send "
            "https://www.googleapis.com/auth/userinfo.profile "
            "https://www.googleapis.com/auth/userinfo.email"
        ),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/auth/google/callback")
def google_callback(code: str, state: str):
    token = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        }
    ).json()

    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    ).json()

    token["email"] = userinfo.get("email")
    token["name"] = userinfo.get("name")
    token["given_name"] = userinfo.get("given_name")

    save_user_token(state, token)

    return HTMLResponse("""
<html>
  <body>
    <script>
      if (window.opener) {
        window.opener.postMessage("gmail_connected", "*");
      }
      window.close();
    </script>
    Gmail connected. You can close this window.
  </body>
</html>
""")

    # return RedirectResponse("/?gmail_connected=true")

@app.get("/auth/logout")
def logout(user_id: str):

    data = {}

    if os.path.exists("tokens.json"):
        with open("tokens.json", "r") as f:
            data = json.load(f)

    if user_id in data:
        del data[user_id]

        with open("tokens.json", "w") as f:
            json.dump(data, f)

    return HTMLResponse("""
    <html>
      <body>
        <script>
          if (window.opener) {
            window.opener.postMessage("gmail_disconnected", "*");
          }
          window.close();
        </script>
        Gmail disconnected.
      </body>
    </html>
    """)
# --------------------------------------------------
# INTENT
# --------------------------------------------------
def detect_intent(text: str) -> str:
    t = text.lower().strip()

    if "confirm" in t and "send" in t:
        return "confirm_email"
    if "disconnect gmail" in t:
        return "disconnect_gmail"

    if "system: gmail connected successfully" in t:
        return "gmail_connected"

    if "add" in t:
        return "add"

    if "email" in t or "gmail" in t or "leave" in t:
        return "email"

    if "search" in t or "who is" in t or "news" in t:
        return "search"

    return "chat"





# --------------------------------------------------
# STATE
# --------------------------------------------------
class AgentState(TypedDict):
    message: str
    user_id: str
    session_id:str
    intent: Literal[
        "chat",
        "add",
        "email",
        "disconnect_gmail",
        "confirm_email",
        "search",
        "gmail_connected"
    ]
    response: str


# --------------------------------------------------
# NODES
# --------------------------------------------------
async def router_node(state: AgentState):
    return {
        "message": state["message"],
        "user_id": state["user_id"],
        "session_id": state["session_id"],
        "intent": detect_intent(state["message"]),
        "response": ""
    }


async def chat_node(state: AgentState):

    session_id = state["session_id"]

    if session_id not in SESSION_MEMORY:
        SESSION_MEMORY[session_id] = []

    messages = SESSION_MEMORY[session_id]

    messages.append(HumanMessage(content=state["message"]))

    if len(messages) > MAX_HISTORY:
        messages[:] = messages[-MAX_HISTORY:]

    res = await llm.ainvoke(messages)

    # 🔥 Properly extract Gemini response text
    if isinstance(res.content, list):
        response_text = ""
        for part in res.content:
            if isinstance(part, dict) and "text" in part:
                response_text += part["text"]
    else:
        response_text = str(res.content)

    messages.append(AIMessage(content=response_text))

    state["response"] = response_text
    return state
   


async def add_node(state: AgentState):
    nums = [int(n) for n in re.findall(r"\d+", state["message"])]
    if len(nums) < 2:
        state["response"] = "❌ Need two numbers."
        return state

    result = await mcp_client.call_tool("add", {"a": nums[0], "b": nums[1]})
    value = result.data

    state["response"] = f"Result: {nums[0]} + {nums[1]} = {value}"
    return state


# --------------------------------------------------
# EMAIL NODE
# --------------------------------------------------
async def email_node(state: AgentState):
    token = get_user_token(state["user_id"])

    if not token:
        state["response"] = (
            "⚠️ Gmail not connected.<br><br>"
            f"<a href=\"javascript:void(0);\" "
            f"onclick=\"window.open('/auth/google?user_id={state['user_id']}',"
            "'gmailAuth','width=500,height=600');\" "
            "style='color:#19c37d;font-weight:bold;'>👉 Connect Gmail</a>"
        )
        return state

    message = state["message"]

    #
    emails = re.findall(r'[\w\.-]+@[\w\.-]+', message)

    if not emails:
        state["response"] = "❌ Please provide at least one recipient email address."
        return state


    # 🔥 Helper function to extract name from email
    def extract_name(email):
        name_part = email.split("@")[0]
        name_part = re.sub(r'[^A-Za-z]', ' ', name_part)
        name_part = name_part.split()[0] if name_part.split() else "User"
        return name_part.capitalize()


    # 🔥 Decide greeting
    if len(emails) == 1:
        greeting_line = f"Dear {extract_name(emails[0])},"
    else:
        greeting_line = "Dear Team,"


    # Gmail supports comma-separated emails
    to_email = ", ".join(emails)


    # 🔥 Extract sender name (for Best regards)
    sender_name = (
        token.get("given_name")
        or (token.get("name").split(" ")[0] if token.get("name") else None)
        or (token.get("email").split("@")[0].capitalize() if token.get("email") else None)
        or "User"
    )
    rewrite_prompt = f"""
Rewrite the user's message into a professional email.

Include a proper Subject line.
start the email with:
{greeting_line}
End with:
Best regards,
{sender_name}

User message:
{message}

Return only final email including Subject.
"""

    res = await llm.ainvoke([HumanMessage(content=rewrite_prompt)])

    body = (
        res.content[0].get("text", "")
        if isinstance(res.content, list)
        else str(res.content)
    )

    subject_match = re.search(r"Subject\s*:\s*(.*)", body, re.IGNORECASE)

    if subject_match:
        subject = subject_match.group(1).strip()
        body = re.sub(r"Subject\s*:\s*.*", "", body, flags=re.IGNORECASE).strip()
    else:
        subject = "No Subject"

    EMAIL_DRAFTS[state["session_id"]] = {
        "to_email": to_email,
        "subject": subject,
        "body": body
    }

    gmail_link = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(to_email)}"
        f"&su={quote(subject)}"
        f"&body={quote(body)}"
    )

    state["response"] = (
        f"📄 Email Preview\n\n"
        f"To: {to_email}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n\n"
        f"<a href='{gmail_link}' target='_blank' "
        "style='color:#19c37d;font-weight:bold;'>✉️ Open in Gmail</a>\n\n"
        "Type 'confirm send' to send directly via API."
    )

    return state




async def gmail_connected_node(state: AgentState):
    token = get_user_token(state["user_id"])

    if token:
        state["response"] = """
        📧 Your Gmail account has been successfully connected.

        You are now authorized to send emails directly through this platform.

        🔴 <a href="javascript:void(0);" 
        onclick="window.open('/auth/logout?user_id=""" + state["user_id"] + """',
        'gmailLogout',
        'width=400,height=500');"
        style="color:red;font-weight:bold;">
        Disconnect Gmail
        </a>
        """
        
    else:
        state["response"] = "❌ Something went wrong while connecting Gmail."

    return state

async def disconnect_node(state: AgentState):

    user_id = state["user_id"]
    session_id = state["session_id"]

    delete_user_token(user_id)

    SESSION_MEMORY.pop(session_id, None)
    EMAIL_DRAFTS.pop(session_id, None)

    state["response"] = f"""
🔴 Gmail disconnected successfully.<br><br>

👉 <a href="javascript:void(0);" 
onclick="window.open('/auth/google?user_id={user_id}',
'gmailAuth','width=500,height=600');"
style="color:#19c37d;font-weight:bold;">
Connect Gmail
</a>
"""

    return state

# --------------------------------------------------
# CONFIRM EMAIL
# --------------------------------------------------
#
async def confirm_email_node(state: AgentState):
    draft = EMAIL_DRAFTS.get(state["session_id"])

    if not draft:
        state["response"] = "❌ No email draft found."
        return state

    token = get_user_token(state["user_id"])

    if not token:
        state["response"] = "❌ Gmail not connected."
        return state

    try:
        result = await mcp_client.call_tool(
            "send_gmail_oauth",
            {
                "token": token,
                "to_email": draft["to_email"],
                "subject": draft["subject"],
                "body": draft["body"]
            }
        )

        # 🔥 Extract clean message
        final_message = "✅ Email sent successfully!"

        if hasattr(result, "content") and result.content:
            first_item = result.content[0]
            if hasattr(first_item, "text"):
                final_message = first_item.text

        del EMAIL_DRAFTS[state["session_id"]]

        state["response"] = final_message
        return state

    except Exception as e:
        state["response"] = f"❌ Failed to send email: {str(e)}"
        return state


# # --------------------------------------------------
# SEARCH NODE
# --------------------------------------------------
async def search_node(state: AgentState):
    raw = search_tool.run(state["message"])
    res = await llm.ainvoke([HumanMessage(content=str(raw))])

    if isinstance(res.content, list):
        state["response"] = res.content[0].get("text", "")
    else:
        state["response"] = str(res.content)

    return state


# --------------------------------------------------
# GRAPH
# --------------------------------------------------
graph = StateGraph(AgentState)

graph.add_node("router", router_node)
graph.add_node("chat", chat_node)
graph.add_node("add", add_node)
graph.add_node("email", email_node)
graph.add_node("confirm_email", confirm_email_node)
graph.add_node("search", search_node)
graph.add_node("gmail_connected", gmail_connected_node)
graph.add_node("disconnect_gmail",disconnect_node)

graph.set_entry_point("router")

graph.add_conditional_edges(
    "router",
    lambda s: s["intent"],
    {
        "chat": "chat",
        "add": "add",
        "email": "email",
        "confirm_email": "confirm_email",
        "search": "search",
        "gmail_connected": "gmail_connected",
        "disconnect_gmail":"disconnect_gmail",
    }
)

for n in [
    "chat",
    "add",
    "email",
    "confirm_email",
    "search",
    "gmail_connected",
    "disconnect_gmail"
]:
    graph.add_edge(n, END)

agent = graph.compile()


# --------------------------------------------------
# CHAT API
# --------------------------------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        result = await agent.ainvoke({
            "message": req.message,
            "user_id": req.user_id,
            "session_id":req.session_id,
            "intent": "chat",
            "response": ""
        })

        return {"response": str(result["response"])}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )