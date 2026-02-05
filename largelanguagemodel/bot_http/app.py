# import re
# from fastapi import FastAPI, Request
# from fastapi.templating import Jinja2Templates
# from fastapi.responses import HTMLResponse, JSONResponse
# from pydantic import BaseModel
# from fastmcp import Client
# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_core.messages import HumanMessage
# from contextlib import asynccontextmanager

# app = FastAPI(title="Gemini + MCP Agent")
# templates = Jinja2Templates(directory="templates")

# class ChatRequest(BaseModel):
#     message: str

# llm = ChatGoogleGenerativeAI(
#     model="gemini-2.5-flash",
#       temperature=0
# )

# MCP_URL = "http://localhost:3333/mcp"

# mcp_client: Client | None = None

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global mcp_client
#     print("📡 Connecting to MCP client...")
#     mcp_client = Client(MCP_URL)
#     await mcp_client.__aenter__()
#     print("✅ MCP client connected")
#     yield
#     print("🔴 Disconnecting MCP client...")
#     await mcp_client.__aexit__(None, None, None)
#     print("🔴 MCP client disconnected")

# app.router.lifespan_context = lifespan

# @app.get("/", response_class=HTMLResponse)
# async def home(request: Request):
#     # Fix template response call order (Request first)
#     return templates.TemplateResponse(request, "index.html")

# def detect_intent(text: str) -> str:
#     text = text.lower()
#     if "add" in text:
#         return "add"
#     if "email" in text or "leave" in text:
#         return "email"
#     return "chat"

# @app.post("/chat")
# async def chat(req: ChatRequest):
#     try:
#         intent = detect_intent(req.message)

#         if intent == "chat":
#             reply = await llm.ainvoke([HumanMessage(content=req.message)])
#             return {"response": reply.content}

#         if intent == "add":
#             extract = await llm.ainvoke([HumanMessage(content=f"Extract two numbers from: {req.message}")])
#             nums = [int(num) for num in re.findall(r"\d+", extract.content)]
#             if len(nums) < 2:
#                 return {"response": "❌ Could not extract two numbers."}
#             a, b = nums[0], nums[1]

#             result = await mcp_client.call_tool("add", {"a": a, "b": b})
#             # result is already int, just stringify
#             final = await llm.ainvoke([HumanMessage(content=f"The result of adding {a} and {b} is {result}")])
#             return {"response": final.content}

#         if intent == "email":
#             draft = await llm.ainvoke([HumanMessage(content=f"Write a professional leave email: {req.message}")])
#             result = await mcp_client.call_tool(
#                 "send_leave_email",
#                 {
#                     "to_email": "jeevanandancolan@gmail.com",
#                     "subject": "Leave Request",
#                     "body": draft.content,
#                 },
#             )
#             return {"response":"✅ Email sent successfully"}

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return JSONResponse(status_code=500, content={"error": str(e)})



# import re
# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse, JSONResponse
# from fastapi.templating import Jinja2Templates
# from pydantic import BaseModel
# from contextlib import asynccontextmanager

# from fastmcp import Client
# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_core.messages import HumanMessage
# from langchain_core.tools import Tool
# from langgraph.graph import StateGraph, END

# # ------------------ FastAPI ------------------

# app = FastAPI(title="Gemini + MCP + LangGraph Agent")
# templates = Jinja2Templates(directory="templates")

# class ChatRequest(BaseModel):
#     message: str

# # ------------------ LLM ------------------

# llm = ChatGoogleGenerativeAI(
#     model="gemini-2.5-flash",
#     temperature=0
# )

# # ------------------ MCP Client ------------------

# MCP_URL = "http://localhost:3333/mcp"
# mcp_client: Client | None = None

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global mcp_client
#     print("📡 Connecting MCP...")
#     mcp_client = Client(MCP_URL)
#     await mcp_client.__aenter__()
#     print("✅ MCP Connected")
#     yield
#     print("🔴 Disconnecting MCP...")
#     await mcp_client.__aexit__(None, None, None)
#     print("🔴 MCP Disconnected")

# app.router.lifespan_context = lifespan

# # ------------------ Search Tool (Simple) ------------------

# async def search_tool(query: str) -> str:
#     """
#     Simple search stub.
#     Replace later with Tavily, SerpAPI, Bing, etc.
#     """
#     return f"Search results for '{query}': (mocked search response)"

# search = Tool(
#     name="search",
#     description="Search the web for information",
#     func=search_tool
# )

# # ------------------ MCP Tool Wrappers ------------------

# async def add_tool(a: int, b: int) -> int:
#     return await mcp_client.call_tool("add", {"a": a, "b": b})

# async def email_tool(body: str) -> str:
#     return await mcp_client.call_tool(
#         "send_leave_email",
#         {
#             "to_email": "jeevanandancolan@gmail.com",
#             "subject": "Leave Request",
#             "body": body,
#         },
#     )

# # ------------------ LangGraph State ------------------

# class AgentState(dict):
#     """
#     keys:
#     - input
#     - result
#     """

# # ------------------ Agent Nodes ------------------

# async def router_node(state: AgentState):
#     text = state["input"].lower()
#     if "add" in text:
#         return "math"
#     if "email" in text or "leave" in text:
#         return "email"
#     if "search" in text or "who" in text or "what" in text:
#         return "search"
#     return "chat"

# async def chat_node(state: AgentState):
#     response = await llm.ainvoke([HumanMessage(content=state["input"])])
#     state["result"] = response.content
#     return state

# async def math_node(state: AgentState):
#     nums = [int(n) for n in re.findall(r"\d+", state["input"])]
#     if len(nums) < 2:
#         state["result"] = "Could not extract two numbers"
#         return state

#     result = await add_tool(nums[0], nums[1])
#     final = await llm.ainvoke([
#         HumanMessage(content=f"Explain the result: {nums[0]} + {nums[1]} = {result}")
#     ])
#     state["result"] = final.content
#     return state

# async def email_node(state: AgentState):
#     draft = await llm.ainvoke([
#         HumanMessage(content=f"Write a professional leave email: {state['input']}")
#     ])
#     await email_tool(draft.content)
#     state["result"] = "✅ Leave email sent successfully"
#     return state

# async def search_node(state: AgentState):
#     result = await search_tool(state["input"])
#     state["result"] = result
#     return state

# # ------------------ LangGraph ------------------

# graph = StateGraph(AgentState)

# graph.add_node("chat", chat_node)
# graph.add_node("math", math_node)
# graph.add_node("email", email_node)
# graph.add_node("search", search_node)

# graph.set_conditional_entry_point(
#     router_node,
#     {
#         "chat": "chat",
#         "math": "math",
#         "email": "email",
#         "search": "search",
#     },
# )

# graph.add_edge("chat", END)
# graph.add_edge("math", END)
# graph.add_edge("email", END)
# graph.add_edge("search", END)

# agent = graph.compile()

# # ------------------ Routes ------------------

# @app.get("/", response_class=HTMLResponse)
# async def home(request: Request):
#     return templates.TemplateResponse(request, "index.html")

# @app.post("/chat")
# async def chat(req: ChatRequest):
#     try:
#         result = await agent.ainvoke({"input": req.message})
#         return {"response": result["result"]}
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"error": str(e)})



import re
import json
from typing import TypedDict, Literal

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from fastmcp import Client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

from langgraph.graph import StateGraph, END


# --------------------------------------------------
# APP SETUP
# --------------------------------------------------

app = FastAPI(title="Gemini + MCP Agent")
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
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
    print("📡 Connecting to MCP client...")
    mcp_client = Client(MCP_URL)
    await mcp_client.__aenter__()
    print("✅ MCP client connected")
    yield
    print("🔴 Disconnecting MCP client...")
    await mcp_client.__aexit__(None, None, None)
    print("🔴 MCP client disconnected")

app.router.lifespan_context = lifespan


# --------------------------------------------------
# UI
# --------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


# --------------------------------------------------
# INTENT DETECTION
# --------------------------------------------------

def detect_intent(text: str) -> str:
    text = text.lower()
    if "add" in text:
        return "add"
    if "email" in text or "leave" in text:
        return "email"
    if "search" in text or "who is" in text or "news" in text:
        return "search"
    return "chat"


# --------------------------------------------------
# SEARCH TOOL
# --------------------------------------------------

search_tool = DuckDuckGoSearchAPIWrapper()


# --------------------------------------------------
# EMAIL PROMPT (STRICT JSON)
# --------------------------------------------------

EMAIL_EXTRACTION_PROMPT = """
Extract the following details from the user message.
Return STRICT JSON only.

Fields:

- reason
- manager_name

User message:
{message}
"""


EMAIL_TEMPLATE = """
Subject: Leave Request – {date}

Dear {manager_name},

I hope this email finds you well.

I would like to request leave on {date} due to {reason}.
I will ensure all my responsibilities are managed accordingly.

Kindly let me know if you need any further information.

Thank you for your understanding.

Best regards,
Fariz
"""



# --------------------------------------------------
# LANGGRAPH STATE
# --------------------------------------------------

class AgentState(TypedDict):
    message: str
    intent: Literal["chat", "add", "email", "search"]
    response: str


# --------------------------------------------------
# ROUTER NODE
# --------------------------------------------------

async def router_node(state: AgentState):
    return {
        "message": state["message"],
        "intent": detect_intent(state["message"]),
        "response": ""
    }


# --------------------------------------------------
# CHAT NODE
# --------------------------------------------------

async def chat_node(state: AgentState):
    reply = await llm.ainvoke([
        HumanMessage(content=state["message"])
    ])
    state["response"] = reply.content
    return state


# --------------------------------------------------
# ADD NODE
# --------------------------------------------------

async def add_node(state: AgentState):
    extract = await llm.ainvoke([
        HumanMessage(content=f"Extract two numbers only: {state['message']}")
    ])

    nums = [int(n) for n in re.findall(r"\d+", extract.content)]
    if len(nums) < 2:
        state["response"] = "❌ Could not extract two numbers."
        return state

    result = await mcp_client.call_tool("add", {
        "a": nums[0],
        "b": nums[1]
    })

    state["response"] = f"The result of adding {nums[0]} and {nums[1]} is {result}"
    return state


# --------------------------------------------------
# EMAIL NODE (SAFE & CONTROLLED)
# --------------------------------------------------

async def email_node(state: AgentState):
    extract = await llm.ainvoke([
        HumanMessage(content=EMAIL_EXTRACTION_PROMPT.format(
            message=state["message"]
        ))
    ])

    data = json.loads(extract.content)

    email_body = EMAIL_TEMPLATE.format(
        date=data.get("date", "tomorrow"),
        reason=data.get("reason", "personal reasons"),
        employee_name=data.get("employee_name", "Your Name"),
        manager_name=data.get("manager_name", "Manager"),
    )

    await mcp_client.call_tool(
        "send_leave_email",
        {
            "to_email": "jeevanandancolan@gmail.com",
            "subject": f"Leave Request ",
            "body": email_body,
        },
    )

    state["response"] = "✅ Leave email sent successfully"
    return state


# --------------------------------------------------
# SEARCH NODE
# --------------------------------------------------

async def search_node(state: AgentState):
    raw = search_tool.run(state["message"])
    reply = await llm.ainvoke([
        HumanMessage(content=f"Answer using this info:\n{raw}")
    ])
    state["response"] = reply.content
    return state


# --------------------------------------------------
# LANGGRAPH SETUP
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
        "search": "search",
    }
)

graph.add_edge("chat", END)
graph.add_edge("add", END)
graph.add_edge("email", END)
graph.add_edge("search", END)

agent = graph.compile()


# --------------------------------------------------
# CHAT ENDPOINT
# --------------------------------------------------

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        result = await agent.ainvoke({
            "message": req.message,
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
