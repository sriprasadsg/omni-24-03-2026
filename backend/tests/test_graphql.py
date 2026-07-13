import pytest
from fastapi.testclient import TestClient
from backend.app import app # Assuming app is imported from app.py

client = TestClient(app)

def test_graphql_hello():
    query = "{ hello }"
    response = client.post("/api/graphql", json={"query": query})
    assert response.status_code == 200
    assert response.json()["data"]["hello"] == "Hello World"
