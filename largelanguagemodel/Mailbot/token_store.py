# import json
# import os

# TOKEN_FILE = "tokens.json"

# def save_user_token(user_id, token):
#     data = {}

#     if os.path.exists(TOKEN_FILE):
#         with open(TOKEN_FILE, "r") as f:
#             data = json.load(f)

#     data[user_id] = token

#     with open(TOKEN_FILE, "w") as f:
#         json.dump(data, f)


# def get_user_token(user_id):
#     if not os.path.exists(TOKEN_FILE):
#         return None

#     with open(TOKEN_FILE, "r") as f:
#         data = json.load(f)

#     return data.get(user_id)

# def delete_user_token(user_id):
#     if not os.path.exists(TOKEN_FILE):
#         return

#     with open(TOKEN_FILE, "r") as f:
#         data = json.load(f)

#     if user_id in data:
#         del data[user_id]

#     with open(TOKEN_FILE, "w") as f:
#         json.dump(data, f)



import sqlite3
import json

conn = sqlite3.connect("tokens.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tokens (
    user_id TEXT PRIMARY KEY,
    token TEXT
)
""")

conn.commit()


def save_user_token(user_id, token):
    cursor.execute(
        "REPLACE INTO tokens (user_id, token) VALUES (?, ?)",
        (user_id, json.dumps(token))
    )
    conn.commit()


def get_user_token(user_id):
    cursor.execute(
        "SELECT token FROM tokens WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()

    if row:
        return json.loads(row[0])
    return None


def delete_user_token(user_id):
    cursor.execute(
        "DELETE FROM tokens WHERE user_id=?",
        (user_id,)
    )
    conn.commit()

