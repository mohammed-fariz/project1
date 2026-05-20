from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI

import mysql.connector
import os
import json
import re

# ==========================================
# LOAD ENV VARIABLES
# ==========================================
load_dotenv()

# ==========================================
# OPENAI CLIENT
# ==========================================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ==========================================
# MYSQL CONNECTION
# ==========================================
db = mysql.connector.connect(

    host=os.getenv("MYSQL_HOST"),

    user=os.getenv("MYSQL_USER"),

    password=os.getenv("MYSQL_PASSWORD"),

    database=os.getenv("MYSQL_DATABASE"),

    port=int(os.getenv("MYSQL_PORT"))

)

cursor = db.cursor(
    dictionary=True
)

print("MYSQL CONNECTED SUCCESSFULLY")

# ==========================================
# FLASK APP
# ==========================================
app = Flask(__name__)

CORS(app)

# ==========================================
# SHORT TERM MEMORY
# ==========================================
# STORES CURRENT SESSION CHAT TEMPORARILY

short_term_memory = {}

# ==========================================
# SYSTEM PROMPT
# ==========================================
SYSTEM_PROMPT = """

You are SiteAI,
an AI-powered assistant for:

- HVAC Engineers
- MEP Engineers
- Site Engineers
- Installation Engineers

RULES:

1. Always answer like experienced site engineer.
2. Never give generic internet-style answers.
3. Prioritize project database information first.
4. Keep responses practical and professional.
5. Keep short answers within 2-5 lines.
6. If user asks procedures:
   provide step-by-step explanation.
7. Add recommendation section when useful.
8. Return JSON ONLY if user explicitly asks.
9. Use memory context for follow-up questions.

"""

# ==========================================
# CLEAN TEXT
# ==========================================
def clean_text(text):

    text = text.lower()

    text = re.sub(
        r"[^a-zA-Z0-9\s-]",
        "",
        text
    )

    return text

# ==========================================
# DETECT RESPONSE MODE
# ==========================================
def detect_response_mode(user_message):

    message = user_message.lower()

    json_keywords = [

        "json",
        "api format",
        "structured output"

    ]

    for word in json_keywords:

        if word in message:

            return "json"

    return "text"

# ==========================================
# SEARCH PROJECT DATA
# ==========================================
def search_project_data(user_message):

    try:

        message = user_message.lower()

        # ======================================
        # ROOM PATTERN EXTRACTION
        # ======================================
        room_patterns = [

            "bedroom 1",
            "bedroom 2",
            "bedroom 3",
            "living area",
            "other area"

        ]

        found_room = None

        for room in room_patterns:

            if room in message:

                found_room = room

                break

        if not found_room:

            return []

        print("FOUND ROOM:")
        print(found_room)

        # ======================================
        # MYSQL SEARCH
        # ======================================
        sql = """

        SELECT *

        FROM rooms

        WHERE LOWER(room_name) = %s

        LIMIT 5

        """

        cursor.execute(

            sql,

            (found_room,)

        )

        results = cursor.fetchall()

        print("DATABASE RESULTS:")
        print(results)

        return results

    except Exception as e:

        print(e)

        return []

# ==========================================
# LONG TERM MEMORY SAVE
# ==========================================
def save_chat_history(

    session_id,
    role,
    message

):

    connection = None
    local_cursor = None

    try:

        # ==================================
        # CREATE NEW CONNECTION
        # ==================================
        connection = mysql.connector.connect(

            host=os.getenv("MYSQL_HOST"),

            user=os.getenv("MYSQL_USER"),

            password=os.getenv("MYSQL_PASSWORD"),

            database=os.getenv("MYSQL_DATABASE"),

            port=int(os.getenv("MYSQL_PORT"))

        )

        # ==================================
        # CREATE LOCAL CURSOR
        # ==================================
        local_cursor = connection.cursor()

        # ==================================
        # CREATE TABLE IF NOT EXISTS
        # ==================================
        create_table_query = """

        CREATE TABLE IF NOT EXISTS
        chat_history (

            id INT PRIMARY KEY AUTO_INCREMENT,

            session_id VARCHAR(255),

            role VARCHAR(50),

            message TEXT,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP

        )

        """

        local_cursor.execute(

            create_table_query

        )

        # ==================================
        # INSERT CHAT
        # ==================================
        sql = """

        INSERT INTO chat_history (

            session_id,
            role,
            message

        )

        VALUES (%s, %s, %s)

        """

        local_cursor.execute(

            sql,

            (

                session_id,
                role,
                message

            )

        )

        connection.commit()

        print("CHAT HISTORY SAVED")

    except Exception as e:

        print("SAVE ERROR:")
        print(e)

    finally:

        if local_cursor:

            local_cursor.close()

        if connection:

            connection.close()

# ==========================================
# LONG TERM MEMORY FETCH
# ==========================================
def get_long_term_memory(

    session_id,
    limit=6

):

    try:

        sql = """

        SELECT role, message

        FROM chat_history

        WHERE session_id=%s

        ORDER BY id DESC

        LIMIT %s

        """

        cursor.execute(

            sql,

            (

                session_id,
                limit

            )

        )

        results = cursor.fetchall()

        results.reverse()

        return results

    except Exception as e:

        print(e)

        return []

# ==========================================
# SHORT TERM MEMORY FETCH
# ==========================================
def get_short_term_memory(session_id):

    if session_id in short_term_memory:

        return short_term_memory[session_id]

    return []

# ==========================================
# SHORT TERM MEMORY SAVE
# ==========================================
def save_short_term_memory(

    session_id,
    role,
    message

):

    if session_id not in short_term_memory:

        short_term_memory[session_id] = []

    short_term_memory[session_id].append({

        "role": role,
        "message": message

    })

    # KEEP ONLY LAST 6 CHATS
    short_term_memory[session_id] = \
    short_term_memory[session_id][-6:]

# ==========================================
# HOME PAGE
# ==========================================
@app.route("/")
def home():

    return render_template("index.html")

# ==========================================
# HEALTH CHECK
# ==========================================
@app.route("/health")
def health():

    return jsonify({

        "status": "ok"

    })

# ==========================================
# CHAT API
# ==========================================
@app.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json()

        user_message = data.get(

            "query",
            ""

        )

        session_id = data.get(

            "session_id",
            "default_session"

        )

        if not user_message:

            return jsonify({

                "success": False,

                "error": "Query required"

            }), 400

        print("===================================")
        print("USER QUESTION:")
        print(user_message)

        # ==================================
        # RESPONSE MODE
        # ==================================
        response_mode = detect_response_mode(

            user_message

        )

        # ==================================
        # SHORT TERM MEMORY
        # ==================================
        short_memory = get_short_term_memory(

            session_id

        )

        short_memory_text = ""

        for item in short_memory:

            short_memory_text += f"""

{item['role']}:
{item['message']}

"""

        # ==================================
        # LONG TERM MEMORY
        # ==================================
        long_memory = get_long_term_memory(

            session_id

        )

        long_memory_text = ""

        for item in long_memory:

            long_memory_text += f"""

{item['role']}:
{item['message']}

"""

        # ==================================
        # PROJECT DATABASE SEARCH
        # ==================================
        db_results = search_project_data(

            user_message

        )

        db_context = json.dumps(

            db_results,
            indent=2

        )

        # ==================================
        # FINAL PROMPT
        # ==================================
        enhanced_prompt = f"""

SHORT TERM MEMORY:

{short_memory_text}

LONG TERM MEMORY:

{long_memory_text}

PROJECT DATABASE:

{db_context}

USER QUESTION:

{user_message}

RESPONSE MODE:
{response_mode}

IMPORTANT:

1. Use project database information first.

2. Use memory for follow-up understanding.

3. Default response:
   natural engineering response.

4. Keep answers practical and concise.

5. If user asks installation procedure:
   explain step-by-step.

6. Return JSON ONLY if user explicitly asks.

"""

        print("===================================")
        print("FINAL PROMPT:")
        print(enhanced_prompt)

        # ==================================
        # OPENAI RESPONSE
        # ==================================
        response = client.chat.completions.create(

            model="gpt-5-mini",

            messages=[

                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },

                {
                    "role": "user",
                    "content": enhanced_prompt
                }

            ],

            temperature=1

        )

        answer = response.choices[0].message.content

        print("===================================")
        print("GPT RESPONSE:")
        print(answer)

        # ==================================
        # SAVE SHORT TERM MEMORY
        # ==================================
        save_short_term_memory(

            session_id,
            "user",
            user_message

        )

        save_short_term_memory(

            session_id,
            "assistant",
            answer

        )

        # ==================================
        # SAVE LONG TERM MEMORY
        # ==================================
        save_chat_history(

            session_id,
            "user",
            user_message

        )

        save_chat_history(

            session_id,
            "assistant",
            answer

        )

        # ==================================
        # FINAL RESPONSE
        # ==================================
        return jsonify({

            "success": True,

            "response": answer

        })

    except Exception as e:

        print("CHAT ERROR:")
        print(e)

        return jsonify({

            "success": False,

            "error": str(e)

        }), 500

# ==========================================
# RUN SERVER
# ==========================================
if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )