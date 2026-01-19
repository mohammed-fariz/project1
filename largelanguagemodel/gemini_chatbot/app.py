# ------------------------------------
# Gemini Chatbot with Memory (FastAPI)
# LangChain v1.2.3
# API-Failure Safe Version
# ------------------------------------

import os
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

# ------------------------------------------------
# 1. API KEY (HARDCODED AS REQUESTED)
# ------------------------------------------------
os.environ["GOOGLE_API_KEY"] = "AIzaSyByjM5S8tdgXJi0MAy6Lp9vYB39afpZxLA"

# ------------------------------------------------
# 2. LOAD GEMINI MODEL (SAFE INIT)
# ------------------------------------------------
try:
    llm = ChatGoogleGenerativeAI(
        model="models/gemini-flash-latest",
        temperature=0.7
    )
except Exception as e:
    print("❌ Failed to initialize Gemini model")
    traceback.print_exc()
    raise RuntimeError("Gemini model initialization failed")

# ------------------------------------------------
# 3. MEMORY STORE
# ------------------------------------------------
store = {}

def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

chatbot = RunnableWithMessageHistory(
    llm,
    get_session_history
)

# ------------------------------------------------
# 4. FASTAPI APP
# ------------------------------------------------
app = FastAPI(title="Gemini Chatbot")

templates = Jinja2Templates(directory="templates")

# ------------------------------------------------
# 5. FRONTEND
# ------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# ------------------------------------------------
# 6. CHAT API (FAILURE SAFE)
# ------------------------------------------------
@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return JSONResponse({"response": ""})

        session_id = request.client.host

        response = chatbot.invoke(
            [HumanMessage(content=user_message)],
            config={"configurable": {"session_id": session_id}}
        )

        # Gemini response handling
        if isinstance(response.content, str):
            bot_text = response.content
        else:
            bot_text = "".join(
                part.get("text", "")
                for part in response.content
                if isinstance(part, dict)
            )

        return JSONResponse({"response": bot_text})

    except Exception as e:
        # Log full error on server
        print("❌ Gemini API call failed")
        traceback.print_exc()

        # Safe message for frontend
        return JSONResponse(
            {
                "response": (
                    "⚠️ Sorry, the AI service is temporarily unavailable.\n"
                    "Please try again in a moment."
                )
            },
            status_code=200
        )
