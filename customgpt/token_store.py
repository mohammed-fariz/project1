import json
import os

TOKEN_FILE = "tokens.json"

def _load():
    if not os.path.exists(TOKEN_FILE):
        return {}
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def _save(data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_user_token(user_id: str, token: dict):
    data = _load()
    data[user_id] = token
    _save(data)

def get_user_token(user_id: str):
    return _load().get(user_id)
