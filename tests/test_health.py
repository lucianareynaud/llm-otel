"""Tests for health endpoints (/healthz, /readyz)."""

from fastapi.testclient import TestClient

import app.routes.health as health_module
from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestHealthz:
    def test_healthz_always_200(self):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_healthz_no_auth_required(self):
        """Liveness probe must be accessible without any headers."""
        response = client.get("/healthz", headers={})
        assert response.status_code == 200


class TestReadyz:
    def test_readyz_when_ready(self, monkeypatch):
        monkeypatch.setattr(health_module, "_ready", True)
        response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    def test_readyz_when_not_ready(self, monkeypatch):
        monkeypatch.setattr(health_module, "_ready", False)
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}

    def test_set_ready_true(self, monkeypatch):
        monkeypatch.setattr(health_module, "_ready", False)
        health_module.set_ready(True)
        assert health_module._ready is True

    def test_set_ready_false(self, monkeypatch):
        monkeypatch.setattr(health_module, "_ready", True)
        health_module.set_ready(False)
        assert health_module._ready is False
