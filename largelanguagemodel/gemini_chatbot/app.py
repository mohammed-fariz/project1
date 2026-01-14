# ------------------------------------
# Gemini Chatbot with Memory (FastAPI)
# LangChain v1.2.3
# ------------------------------------

import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

# ------------------------------------------------
# API KEY (HARDCODED AS REQUESTED)
# ------------------------------------------------
os.environ["GOOGLE_API_KEY"] = "AIzaSyD0g51vFwcWKEgJ6kdzGUzN6hhOE1qrmeg"

# ------------------------------------------------
# LOAD GEMINI MODEL
# ------------------------------------------------
llm = ChatGoogleGenerativeAI(
    model="models/gemini-flash-latest",
    temperature=0.7
)

# ------------------------------------------------
# MEMORY STORE
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
# FASTAPI APP
# ------------------------------------------------
app = FastAPI()

templates = Jinja2Templates(directory="templates")

# ------------------------------------------------
# SERVE FRONTEND
# ------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# ------------------------------------------------
# CHAT API
# ------------------------------------------------
@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message", "").strip()

    if not user_message:
        return JSONResponse({"response": ""})

    session_id = request.client.host

    response = chatbot.invoke(
        [HumanMessage(content=user_message)],
        config={"configurable": {"session_id": session_id}}
    )

    # Robust Gemini response handling
    if isinstance(response.content, str):
        bot_text = response.content
    else:
        bot_text = "".join(
            part.get("text", "")
            for part in response.content
            if isinstance(part, dict)
        )

    return JSONResponse({"response": bot_text})
