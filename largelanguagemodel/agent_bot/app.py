import os
from dotenv import load_dotenv
from typing import TypedDict, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# -------------------------------------------------
# ENV
# -------------------------------------------------
# load_dotenv()
os.environ["GOOGLE_API_KEY"] = "AIzaSyDnwOtkRpegCA64CAiuy11j6WnU6NwBv40"

# -------------------------------------------------
# FASTAPI
# -------------------------------------------------
app = FastAPI(title="LangGraph + Gemini + MCP Agent")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# -------------------------------------------------
# GEMINI LLM
# -------------------------------------------------
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0
)

# -------------------------------------------------
# MCP CLIENT (INSIDE app.py)
# -------------------------------------------------
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

mcp_cm = None
mcp_session: ClientSession | None = None

@app.on_event("startup")
async def startup():
    global mcp_cm, mcp_session

    params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"]
    )

    # keep MCP process alive
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

# -------------------------------------------------
# LANGGRAPH STATE
# -------------------------------------------------
class AgentState(TypedDict):
    messages: List
    last_user_message: str

# -------------------------------------------------
# INTENT CHECK (NO MCP FOR HELLO)
# -------------------------------------------------
def needs_tools(text: str) -> bool:
    text = text.lower()
    return any(k in text for k in ["add", "sum", "calculate"])

# -------------------------------------------------
# LLM NODE
# -------------------------------------------------
async def llm_node(state: AgentState):
    response = await llm.ainvoke(state["messages"])
    return {
        "messages": state["messages"] + [response],
        "last_user_message": state["last_user_message"]
    }

# -------------------------------------------------
# TOOL NODE (ONLY PLACE MCP IS CALLED)
# -------------------------------------------------
async def tool_node(state: AgentState):
    last = state["messages"][-1]

    tool_call = last.additional_kwargs["tool_calls"][0]
    tool_name = tool_call["function"]["name"]
    tool_args = tool_call["function"]["arguments"]

    result = await mcp_session.call_tool(tool_name, tool_args)

    return {
        "messages": state["messages"] + [
            ToolMessage(
                content=str(result.content),
                name=tool_name
            )
        ],
        "last_user_message": state["last_user_message"]
    }

# -------------------------------------------------
# ROUTER
# -------------------------------------------------
def router(state: AgentState):
    last = state["messages"][-1]

    if "tool_calls" in last.additional_kwargs:
        return "tool"

    return "end"

# -------------------------------------------------
# BUILD LANGGRAPH
# -------------------------------------------------
from langgraph.graph import StateGraph, END

graph = StateGraph(AgentState)

graph.add_node("llm", llm_node)
graph.add_node("tool", tool_node)

graph.set_entry_point("llm")

graph.add_conditional_edges(
    "llm",
    router,
    {
        "tool": "tool",
        "end": END
    }
)

graph.add_edge("tool", "llm")

chat_graph = graph.compile()

# -------------------------------------------------
# CHAT API
# -------------------------------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        # greeting / small talk → LLM only
        if not needs_tools(req.message):
            response = await llm.ainvoke([HumanMessage(content=req.message)])
            return {"response": response.content}

        # tool-required query → LangGraph
        result = await chat_graph.ainvoke({
            "messages": [HumanMessage(content=req.message)],
            "last_user_message": req.message
        })

        return {"response": result["messages"][-1].content}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"response": f"Error: {str(e)}"}
        )

# -------------------------------------------------
# HEALTH CHECK
# -------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mcp_connected": mcp_session is not None
    }
