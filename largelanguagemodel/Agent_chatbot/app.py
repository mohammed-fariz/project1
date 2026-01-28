import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from langchain_core.prompts import PromptTemplate

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()

# -----------------------------
# FASTAPI APP
# -----------------------------
app = FastAPI(title="Agent Chatbot API")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# SERVE FRONTEND (index.html)
# -----------------------------
# @app.get("/", response_class=HTMLResponse)
# def home():
#     with open("index.html", "r", encoding="utf-8") as f:
#         return f.read()
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# -----------------------------
# REQUEST MODEL
# -----------------------------
class ChatRequest(BaseModel):
    message: str

# -----------------------------
# LLM
# -----------------------------
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest",
    temperature=0
)


# -----------------------------
# TOOLS
# -----------------------------
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

from langchain_core.tools import Tool
from langchain_experimental.utilities.python import PythonREPL


# Web Search Tool
search = DuckDuckGoSearchAPIWrapper()

web_search_tool = Tool(
    name="Web Search",
    func=search.run,
    description="Search the web for real-time or current information"
)

# Python Tool
python_tool = Tool(
    name="Python Calculator",
    func=PythonREPL().run,
    description="Use this tool for math and calculations"
)

tools = [web_search_tool, python_tool]

# -----------------------------
# MEMORY
# -----------------------------
from langchain_classic.memory import ConversationBufferMemory

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# -----------------------------
# AGENT
# -----------------------------

from langchain_classic.agents import create_react_agent, AgentExecutor

from langchain_core.prompts import PromptTemplate

REACT_PROMPT = """
You are a helpful AI assistant that can use tools.

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: your reasoning about what to do next
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat)
Final Answer: the final answer to the user

Begin!

Question: {input}
{agent_scratchpad}
"""

prompt = PromptTemplate(
    input_variables=[
        "input",
        "tools",
        "tool_names",
        "agent_scratchpad",
    ],
    template=REACT_PROMPT,
)



agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True
)

# -----------------------------
# CHAT ENDPOINT
# -----------------------------
@app.post("/chat")
def chat(req: ChatRequest):
    try:
        result = agent_executor.invoke(
            {"input": req.message}
        )
        return {"response": result["output"]}

    except Exception as e:
        return JSONResponse(
            {"response": "⚠️ Something went wrong. Please try again."},
            status_code=200
        )
