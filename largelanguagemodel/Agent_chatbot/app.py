# app.py
import os
import json
import asyncio
from typing import TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from langgraph.graph import StateGraph, END
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# --------------------------------------------------
# ENV
# --------------------------------------------------
os.environ["GOOGLE_API_KEY"] = "AIzaSyBCC23ewXKWNyVdeGlOey4MC4QM17uGHVs"
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
# MCP MANAGER (SAFE BACKGROUND LIFECYCLE)
# --------------------------------------------------
class MCPManager:
    def __init__(self):
        self.session: ClientSession | None = None
        self._task: asyncio.Task | None = None

    async def start(self):
        params = StdioServerParameters(
            command="python",
            args=["mcp_server.py"]
        )

        async def runner():
            async with stdio_client(params) as (read, write):
                self.session = ClientSession(read, write)
                async with self.session:
                    await self.session.initialize()
                    await asyncio.Event().wait()

        self._task = asyncio.create_task(runner())

        while self.session is None:
            await asyncio.sleep(0.1)

    async def stop(self):
        if self._task:
            self._task.cancel()

mcp_manager = MCPManager()

@app.on_event("startup")
async def startup():
    await mcp_manager.start()

@app.on_event("shutdown")
async def shutdown():
    await mcp_manager.stop()

# --------------------------------------------------
# SEARCH TOOL
# --------------------------------------------------
search_tool = DuckDuckGoSearchAPIWrapper()

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
                "Extract email details STRICTLY as JSON.\n\n"
                "Required keys:\n"
                "- to_email\n"
                "- subject\n"
                "- body\n\n"
                f"User request: {state['user_message']}\n\n"
                "Return ONLY valid JSON. No markdown. No explanation."
            )
        )
    ])

    # 🔧 FIX: Normalize Gemini output
    raw_content = plan.content

    if isinstance(raw_content, list):
        # Gemini often returns list of text blocks
        raw_content = raw_content[0].get("text", "")

    if not isinstance(raw_content, str):
        raise ValueError("LLM did not return text output")

    # 🔧 FIX: Extract JSON safely
    try:
        email_data = json.loads(raw_content)
    except json.JSONDecodeError:
        raise ValueError(
            f"Invalid JSON returned by LLM:\n{raw_content}"
        )

    return {
        "user_message": state["user_message"],
        "email_data": email_data
    }


async def email_tool_node(state: EmailState):
    await mcp_manager.session.call_tool(
        "send_leave_email",
        {
            "to_email": state["email_data"]["to_email"],
            "subject": state["email_data"]["subject"],
            "body": state["email_data"]["body"],
        }
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

        # 🟢 Chat
        if route == "chat":
            reply = await llm.ainvoke([
                HumanMessage(content=req.message)
            ])
            return {"response": reply.content}

        # 🟡 Math
        if route == "math":
            extract = await llm.ainvoke([
                HumanMessage(content=f"Extract two numbers from: {req.message}")
            ])
            nums = [int(s) for s in extract.content.split() if s.isdigit()]
            a, b = nums[0], nums[1]

            result = await mcp_manager.session.call_tool(
                "add",
                {"a": a, "b": b}
            )
            return {"response": f"The result is {result.content}"}

        # 🔵 Email
        if route == "email":
            await email_agent.ainvoke({
                "user_message": req.message
            })
            return {"response": "✅ Email sent successfully"}

        # 🟣 Search
        if route == "search":
            raw = search_tool.run(req.message)
            final = await llm.ainvoke([
                HumanMessage(
                    content=f"Answer clearly using this info:\n\n{raw}"
                )
            ])
            return {"response": final.content}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
