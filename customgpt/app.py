import os
import re
import json
from typing import TypedDict, Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from contextlib import asynccontextmanager
from urllib.parse import urlencode
import requests

from dotenv import load_dotenv
from fastmcp import Client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langgraph.graph import StateGraph, END

from token_store import get_user_token, save_user_token

# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI(title="Agentic Multi-User Gmail Bot")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str
    user_id: str

llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest",
    temperature=0
)

MCP_URL = "http://localhost:3333/mcp"
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
        "scope": "https://www.googleapis.com/auth/gmail.send",
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

    save_user_token(state, token)
    return RedirectResponse("/?gmail_connected=true")

# --------------------------------------------------
# INTENT
# --------------------------------------------------
def detect_intent(text: str) -> str:
    t = text.lower()
    if "add" in t:
        return "add"
    if "email" in t or "gmail" in t or "leave" in t:
        return "email"
    if "search" in t or "who is" in t or "news" in t:
        return "search"
    return "chat"

search_tool = DuckDuckGoSearchAPIWrapper()

# --------------------------------------------------
# EMAIL TEMPLATE
# --------------------------------------------------
EMAIL_PROMPT = """
Extract STRICT JSON only.

Fields:
- reason
- manager_name
"""

EMAIL_TEMPLATE = """
Subject: Leave Request

Dear {manager_name},

I would like to request leave due to {reason}.

Thanks,
Fariz
"""

# --------------------------------------------------
# LANGGRAPH STATE
# --------------------------------------------------
class AgentState(TypedDict):
    message: str
    user_id: str
    intent: Literal["chat", "add", "email", "search"]
    response: str

# --------------------------------------------------
# NODES
# --------------------------------------------------
async def router_node(state: AgentState):
    return {
        "message": state["message"],
        "user_id": state["user_id"],
        "intent": detect_intent(state["message"]),
        "response": ""
    }

async def chat_node(state: AgentState):
    res = await llm.ainvoke([HumanMessage(content=state["message"])])
    state["response"] = res.content
    return state

async def add_node(state: AgentState):
    nums = [int(n) for n in re.findall(r"\d+", state["message"])]
    if len(nums) < 2:
        state["response"] = "❌ Need two numbers."
        return state

    r = await mcp_client.call_tool("add", {"a": nums[0], "b": nums[1]})
    state["response"] = f"Result: {nums[0]} + {nums[1]} = {r}"
    return state


async def email_node(state: AgentState):
    token = get_user_token(state["user_id"])
    if not token:
        state["response"] = (
            "⚠️ Gmail is not connected.\n\n"
            "To send emails, please connect your Gmail:\n"
            f"👉 /auth/google?user_id={state['user_id']}"
        )
        return state


    extract = await llm.ainvoke([
        HumanMessage(content=EMAIL_PROMPT + state["message"])
    ])
    data = json.loads(extract.content)

    body = EMAIL_TEMPLATE.format(
        reason=data.get("reason", "personal reasons"),
        manager_name=data.get("manager_name", "Manager")
    )

    await mcp_client.call_tool(
        "send_gmail_oauth",
        {
            "user_id": state["user_id"],
            "to_email": "abc@gmail.com",
            "subject": "Leave Request",
            "body": body
        }
    )

    state["response"] = "✅ Email sent successfully"
    return state

async def search_node(state: AgentState):
    raw = search_tool.run(state["message"])
    res = await llm.ainvoke([HumanMessage(content=raw)])
    state["response"] = res.content
    return state

# --------------------------------------------------
# GRAPH
# --------------------------------------------------
graph = StateGraph(AgentState)
graph.add_node("router", router_node)
graph.add_node("chat", chat_node)
graph.add_node("add", add_node)
graph.add_node("email", email_node)
graph.add_node("search", search_node)

graph.set_entry_point("router")
graph.add_conditional_edges(
    "router",
    lambda s: s["intent"],
    {
        "chat": "chat",
        "add": "add",
        "email": "email",
        "search": "search"
    }
)

for n in ["chat", "add", "email", "search"]:
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
            "intent": "chat",
            "response": ""
        })
        return {"response": result["response"]}
    except Exception as e:
       
       
       import traceback
       traceback.print_exc()
       return JSONResponse(
          status_code=500,
          content={"error": str(e)}
    )

