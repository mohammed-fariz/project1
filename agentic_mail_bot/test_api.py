import pytest
from fastapi.testclient import TestClient
from backend.app import app, detect_intent

client = TestClient(app)


# --------------------------------------------------
# TEST FASTAPI ROOT
# --------------------------------------------------
def test_home():
    response = client.get("/")
    assert response.status_code == 200


# --------------------------------------------------
# TEST INTENT DETECTION
# --------------------------------------------------
def test_detect_email_intent():
    assert detect_intent("send email to john") == "email"


def test_detect_add_intent():
    assert detect_intent("add 2 and 3") == "add"


def test_detect_search_intent():
    assert detect_intent("who is elon musk") == "search"


# --------------------------------------------------
# TEST CHAT API
# --------------------------------------------------
def test_chat_endpoint():
    response = client.post(
        "/chat",
        json={
            "message": "hello",
            "user_id": "test_user",
            "session_id": "session1"
        }
    )

    assert response.status_code == 200
    assert "response" in response.json()