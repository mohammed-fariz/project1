import os
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# -----------------------------
# LangChain imports
# -----------------------------
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain

from langchain_google_genai import ChatGoogleGenerativeAI

# -----------------------------
# SET GOOGLE API KEY
# -----------------------------
os.environ["GOOGLE_API_KEY"] = "AIzaSyBQ9AktSrcy6G98TlFqYOIM91JcZPS4f1Y"

# -----------------------------
# LOAD & PREPARE VECTOR DB (ONCE AT STARTUP)
# -----------------------------
pdf_files = ["cs.pdf", "transformers.pdf"]
documents = []

for pdf in pdf_files:
    loader = PyPDFLoader(pdf)
    documents.extend(loader.load())


splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100
)
chunks = splitter.split_documents(documents)

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vectorstore = FAISS.from_documents(chunks, embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# -----------------------------
# LLM (GEMINI)
# -----------------------------
llm = ChatGoogleGenerativeAI(
    model="models/gemini-2.5-flash",
    temperature=0.7,
    convert_system_message_to_human=True
)

# -----------------------------
# MEMORY STORE (SESSION-BASED)
# -----------------------------
memory_store = {}

def get_memory(session_id: str):
    if session_id not in memory_store:
        memory_store[session_id] = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
    return memory_store[session_id]

def get_qa_chain(memory):
    return ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=False
    )

# -----------------------------
# FASTAPI APP
# -----------------------------
app = FastAPI(title="RAG Chatbot with Memory")
templates = Jinja2Templates(directory="templates")

# -----------------------------
# ROUTES
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return JSONResponse({"response": ""})

        # Simple session id (per user/IP)
        session_id = request.client.host if request.client else "anonymous"

        # Get memory for this session
        memory = get_memory(session_id)

        # Build chain with memory
        qa_chain = get_qa_chain(memory)

        # Ask question
        result = qa_chain({"question": user_message})

        return JSONResponse(
            {"response": result["answer"]}
        )

    except Exception:
        print("❌ RAG/Gemini call failed")
        traceback.print_exc()

        return JSONResponse(
            {
                "response": (
                    "⚠️ Sorry, the RAG service is temporarily unavailable.\n"
                    "Please try again in a moment."
                )
            }
        )
