import re
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from fastmcp import Client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from contextlib import asynccontextmanager

app = FastAPI(title="Gemini + MCP Agent")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

MCP_URL = "http://localhost:3333/mcp"

mcp_client: Client | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_client
    print("📡 Connecting to MCP client...")
    mcp_client = Client(MCP_URL)
    await mcp_client.__aenter__()
    print("✅ MCP client connected")
    yield
    print("🔴 Disconnecting MCP client...")
    await mcp_client.__aexit__(None, None, None)
    print("🔴 MCP client disconnected")

app.router.lifespan_context = lifespan

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Fix template response call order (Request first)
    return templates.TemplateResponse(request, "index.html")

def detect_intent(text: str) -> str:
    text = text.lower()
    if "add" in text:
        return "add"
    if "email" in text or "leave" in text:
        return "email"
    return "chat"

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        intent = detect_intent(req.message)

        if intent == "chat":
            reply = await llm.ainvoke([HumanMessage(content=req.message)])
            return {"response": reply.content}

        if intent == "add":
            extract = await llm.ainvoke([HumanMessage(content=f"Extract two numbers from: {req.message}")])
            nums = [int(num) for num in re.findall(r"\d+", extract.content)]
            if len(nums) < 2:
                return {"response": "❌ Could not extract two numbers."}
            a, b = nums[0], nums[1]

            result = await mcp_client.call_tool("add", {"a": a, "b": b})
            # result is already int, just stringify
            final = await llm.ainvoke([HumanMessage(content=f"The result of adding {a} and {b} is {result}")])
            return {"response": final.content}

        if intent == "email":
            draft = await llm.ainvoke([HumanMessage(content=f"Write a professional leave email: {req.message}")])
            result = await mcp_client.call_tool(
                "send_leave_email",
                {
                    "to_email": "jeevanandancolan@gmail.com",
                    "subject": "Leave Request",
                    "body": draft.content,
                },
            )
            return {"response":"✅ Email sent successfully"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})