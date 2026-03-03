"""Tests for the query engine and API."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "engine_ready" in data


class TestFrontend:
    def test_root_serves_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "LegacyLens" in response.text


class TestQueryEndpoint:
    def test_empty_query_rejected(self, client):
        response = client.post("/api/query", json={"query": ""})
        assert response.status_code == 422  # Validation error

    def test_query_without_engine_returns_503(self, client):
        response = client.post("/api/query", json={"query": "test question"})
        assert response.status_code == 503

    def test_top_k_validation(self, client):
        response = client.post("/api/query", json={"query": "test", "top_k": 0})
        assert response.status_code == 422

        response = client.post("/api/query", json={"query": "test", "top_k": 25})
        assert response.status_code == 422
