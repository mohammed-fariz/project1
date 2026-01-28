import os
from dotenv import load_dotenv
from typing import TypedDict, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# -----------------------------
# ENV
# -----------------------------
load_dotenv()

# -----------------------------
# FASTAPI
# -----------------------------
app = FastAPI(title="LangGraph + Gemini + MCP Chatbot")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# -----------------------------
# GEMINI LLM
# -----------------------------
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0
)

# -----------------------------
# MCP CLIENT (CORRECT WAY)
# -----------------------------
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

mcp_session: ClientSession | None = None

@app.on_event("startup")
async def startup_event():
    """
    Start MCP once when FastAPI starts
    """
    global mcp_session

    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
    )

    read, write = await stdio_client(server_params).__aenter__()
    mcp_session = ClientSession(read, write)
    await mcp_session.__aenter__()

@app.on_event("shutdown")
async def shutdown_event():
    if mcp_session:
        await mcp_session.__aexit__(None, None, None)

# -----------------------------
# LANGGRAPH STATE
# -----------------------------
class AgentState(TypedDict):
    messages: List[BaseMessage]

# -----------------------------
# LLM NODE
# -----------------------------
def llm_node(state: AgentState):
    response = llm.invoke(state["messages"])
    return {"messages": state["messages"] + [response]}

# -----------------------------
# TOOL NODE (DIRECT MCP CALL)
# -----------------------------
async def tool_node(state: AgentState):
    last_msg = state["messages"][-1]
    tool_call = last_msg.additional_kwargs["tool_calls"][0]

    result = await mcp_session.call_tool(
        tool_call["name"],
        tool_call["args"]
    )

    return {
        "messages": state["messages"] + [
            ToolMessage(
                content=str(result),
                tool_name=tool_call["name"]
            )
        ]
    }

# -----------------------------
# ROUTER
# -----------------------------
def router(state: AgentState):
    last_msg = state["messages"][-1]
    if "tool_calls" in last_msg.additional_kwargs:
        return "tool"
    return "end"

# -----------------------------
# BUILD LANGGRAPH
# -----------------------------
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
        "end": END,
    }
)

graph.add_edge("tool", "llm")

chat_graph = graph.compile()

# -----------------------------
# CHAT ENDPOINT
# -----------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    result = await chat_graph.ainvoke({
        "messages": [HumanMessage(content=req.message)]
    })

    return {
        "response": result["messages"][-1].content
    }
