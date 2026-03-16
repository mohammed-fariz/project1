import pytest
from fastapi.testclient import TestClient
from backend.app import app, detect_intent

client = TestClient(app)


def test_home():
    response = client.get("/")
    assert response.status_code == 200


def test_detect_email_intent():
    assert detect_intent("send email to john") == "email"


def test_detect_add_intent():
    assert detect_intent("add 5 and 3") == "add"


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