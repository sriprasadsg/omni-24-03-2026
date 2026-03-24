import pytest
from fastapi.testclient import TestClient
from backend.app import app
import motor.motor_asyncio
import os

@pytest.fixture
def client():
    """Provides a TestClient for the FastAPI app."""
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_db(monkeypatch):
    """Mocks the MongoDB client for testing."""
    class MockCollection:
        async def find_one(self, query): return None
        async def insert_one(self, doc): pass
        async def update_one(self, query, update, upsert=False): pass
        
    class MockDatabase:
        def __getitem__(self, name): return MockCollection()
        
    class MockClient:
        def __getitem__(self, name): return MockDatabase()
        
    monkeypatch.setattr("backend.database.client", MockClient())
    return MockClient()
