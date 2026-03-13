from fastapi.testclient import TestClient
from agentic_mail_bot.backend.app import app

client = TestClient(app)

def test_home():
    response = client.get("/")
    assert response.status_code == 200