import json
import os

TOKEN_FILE = "tokens.json"

def save_user_token(user_id, token):
    data = {}

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)

    data[user_id] = token

    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)


def get_user_token(user_id):
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)

    return data.get(user_id)

def delete_user_token(user_id):
    if not os.path.exists(TOKEN_FILE):
        return

    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)

    if user_id in data:
        del data[user_id]

    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)