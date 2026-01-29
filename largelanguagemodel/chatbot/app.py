# app.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# --------------------------------------------------
# ENV
# --------------------------------------------------
os.environ["GOOGLE_API_KEY"] = "AIzaSyDnwOtkRpegCA64CAiuy11j6WnU6NwBv40"

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------
app = FastAPI(title="Gemini + MCP Agent")
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
    model="gemini-2.5-flash",
    temperature=0
)

# --------------------------------------------------
# MCP CLIENT (SAFE LIFECYCLE)
# --------------------------------------------------
mcp_cm = None
mcp_session: ClientSession | None = None

@app.on_event("startup")
async def startup():
    global mcp_cm, mcp_session

    params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"]
    )

    mcp_cm = stdio_client(params)
    read, write = await mcp_cm.__aenter__()

    mcp_session = ClientSession(read, write)
    await mcp_session.__aenter__()
    await mcp_session.initialize()

@app.on_event("shutdown")
async def shutdown():
    if mcp_session:
        await mcp_session.__aexit__(None, None, None)
    if mcp_cm:
        await mcp_cm.__aexit__(None, None, None)

# --------------------------------------------------
# INTENT DETECTION
# --------------------------------------------------
def detect_intent(text: str) -> str:
    text = text.lower()
    if "add" in text:
        return "add"
    if "email" in text or "leave" in text:
        return "email"
    return "chat"

# --------------------------------------------------
# CHAT API
# --------------------------------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        intent = detect_intent(req.message)

        # 1️⃣ Normal chat
        if intent == "chat":
            reply = await llm.ainvoke([
                HumanMessage(content=req.message)
            ])
            return {"response": reply.content}

        # 2️⃣ Calculator
        if intent == "add":
            extract = await llm.ainvoke([
                HumanMessage(content=f"Extract two numbers from: {req.message}")
            ])

            nums = [int(s) for s in extract.content.split() if s.isdigit()]
            a, b = nums[0], nums[1]

            result = await mcp_session.call_tool(
                "add",
                {"a": a, "b": b}
            )

            final = await llm.ainvoke([
                HumanMessage(content=f"The result of adding {a} and {b} is {result.content}")
            ])

            return {"response": final.content}

        # 3️⃣ Email
        if intent == "email":
            draft = await llm.ainvoke([
                HumanMessage(content=f"Write a professional leave email: {req.message}")
            ])

            await mcp_session.call_tool(
                "send_leave_email",
                {
                    "to_email": "jeevanandancolan@gmail.com",
                    "subject": "Leave Request",
                    "body": draft.content
                }
            )

            return {"response": "✅ Leave email sent successfully"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
