# app.py
import os
import json
from typing import TypedDict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

from mcp.client.http import HTTPClient   # ✅ HTTP CLIENT

# --------------------------------------------------
# ENV
# --------------------------------------------------
os.environ["GOOGLE_API_KEY"] = "YOUR_GEMINI_KEY"

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------
app = FastAPI(title="Agent Orchestrated MCP Chatbot")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --------------------------------------------------
# LLM
# --------------------------------------------------
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest",
    temperature=0
)

# --------------------------------------------------
# MCP HTTP CLIENT
# --------------------------------------------------
mcp_client = HTTPClient("http://127.0.0.1:3333")

# --------------------------------------------------
# ORCHESTRATOR
# --------------------------------------------------
def orchestrator(text: str) -> str:
    text = text.lower()

    if any(k in text for k in ["add", "sum", "calculate"]):
        return "math"
    if any(k in text for k in ["email", "leave", "send mail"]):
        return "email"
    if any(k in text for k in ["search", "who is", "latest", "news"]):
        return "search"
    return "chat"

# --------------------------------------------------
# EMAIL AGENT (LANGGRAPH)
# --------------------------------------------------
class EmailState(TypedDict):
    user_message: str
    email_data: dict

async def email_llm_node(state: EmailState):
    plan = await llm.ainvoke([
        HumanMessage(
            content=(
                "Extract email details strictly as JSON.\n\n"
                "Keys: to_email, subject, body\n\n"
                f"User request: {state['user_message']}\n\n"
                "Return ONLY JSON."
            )
        )
    ])

    raw = plan.content
    if isinstance(raw, list):
        raw = raw[0]["text"]

    return {
        "user_message": state["user_message"],
        "email_data": json.loads(raw)
    }

async def email_tool_node(state: EmailState):
    await mcp_client.call_tool(
        "send_leave_email",
        state["email_data"]
    )
    return state

email_graph = StateGraph(EmailState)
email_graph.add_node("llm", email_llm_node)
email_graph.add_node("send", email_tool_node)
email_graph.set_entry_point("llm")
email_graph.add_edge("llm", "send")
email_graph.add_edge("send", END)

email_agent = email_graph.compile()

# --------------------------------------------------
# CHAT ENDPOINT
# --------------------------------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        route = orchestrator(req.message)

        if route == "chat":
            reply = await llm.ainvoke([HumanMessage(content=req.message)])
            return {"response": reply.content}

        if route == "math":
            extract = await llm.ainvoke([
                HumanMessage(content=f"Extract two numbers from: {req.message}")
            ])
            nums = [int(x) for x in extract.content.split() if x.isdigit()]
            result = await mcp_client.call_tool("add", {"a": nums[0], "b": nums[1]})
            return {"response": f"Result: {result.content}"}

        if route == "email":
            await email_agent.ainvoke({"user_message": req.message})
            return {"response": "✅ Email sent successfully"}

        if route == "search":
            search = DuckDuckGoSearchAPIWrapper()
            raw = search.run(req.message)
            final = await llm.ainvoke([
                HumanMessage(content=f"Answer clearly:\n{raw}")
            ])
            return {"response": final.content}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
