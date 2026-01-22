# ------------------------------------
# backend.py
# LangChain + Gemini + FastAPI
# PromptTemplate + Tool + Memory (NO AGENT)
# ------------------------------------

import os
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# ------------------------------------------------
# API KEY
# ------------------------------------------------
os.environ["GOOGLE_API_KEY"] = "AIzaSyCotHbOC79dcmgXYb5kM_ht2iHJtaa7cvc"

# ------------------------------------------------
# GEMINI MODEL
# ------------------------------------------------
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="models/gemini-2.5-flash",
    temperature=0.7
)

# ------------------------------------------------
# PROMPT TEMPLATE
# ------------------------------------------------
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful AI assistant."),
    ("human", "{input}")
])

# ------------------------------------------------
# TOOL
# ------------------------------------------------
from langchain.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the weather of a city"""
    return f"It is sunny in {city}"

# ------------------------------------------------
# MEMORY (SESSION BASED)
# ------------------------------------------------
from langchain_classic.memory import ConversationBufferMemory

memory_store = {}

def get_memory(session_id: str):
    if session_id not in memory_store:
        memory_store[session_id] = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
    return memory_store[session_id]

# ------------------------------------------------
# FASTAPI APP
# ------------------------------------------------
app = FastAPI(title="Gemini LangChain Bot")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ------------------------------------------------
# CHAT ENDPOINT (NO AGENT)
# ------------------------------------------------
@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_input = data.get("message", "").strip()

        if not user_input:
            return JSONResponse({"response": ""})

        # Session-based memory
        session_id = request.client.host
        memory = get_memory(session_id)

        # ---- MANUAL TOOL LOGIC ----
        tool_context = ""

        if "weather" in user_input.lower():
            # very simple rule-based extraction
            city = user_input.split()[-1]
            tool_result = get_weather.run(city)
            tool_context = f"\nTool result: {tool_result}"

        # Load previous chat history
        history = memory.load_memory_variables({}).get("chat_history", [])

        history_text = ""
        for msg in history:
            role = "User" if msg.type == "human" else "Assistant"
            history_text += f"{role}: {msg.content}\n"

        # Final input to LLM
        final_input = f"{history_text}User: {user_input}{tool_context}"

        # LLM call
        response = llm.invoke(
            prompt.format_messages(input=final_input)
        )

        # Save memory
        memory.save_context(
            {"input": user_input},
            {"output": response.content}
        )

        return JSONResponse({"response": response.content})

    except Exception:
        traceback.print_exc()
        return JSONResponse(
            {"response": "⚠️ AI service unavailable. Please try again."},
            status_code=200
        )
