"""Automated Unit Tests for Phase 5: High-Performance FastAPI Backend & Dashboard API."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_api_model_info(client):
    """Verify that /api/model/info returns full multi-tier architecture metadata."""
    res = client.get("/api/model/info")
    assert res.status_code == 200
    data = res.json()
    assert "tiers" in data
    assert "tier1" in data["tiers"]
    assert "tier2" in data["tiers"]
    assert "tier3" in data["tiers"]
    assert "tier4" in data["tiers"]
    assert data["features_dim"] == 30
    assert "operational_metrics" in data


def test_api_forecast(client):
    """Verify that /api/forecast returns multi-horizon probability predictions."""
    res = client.get("/api/forecast?horizons=15&horizons=30&horizons=60")
    assert res.status_code == 200
    data = res.json()
    assert "probabilities" in data
    assert len(data["probabilities"]) == 3
    for p in data["probabilities"]:
        assert "minutes" in p
        assert "probability" in p
        assert 0.0 <= p["probability"] <= 1.0


def test_api_statistics(client):
    """Verify system statistics endpoint."""
    res = client.get("/api/statistics")
    assert res.status_code == 200
    data = res.json()
    assert "total_samples_processed" in data
    assert "forecast_accuracy" in data


def test_dashboard_static_page(client):
    """Verify that root / returns the clean HTML dashboard."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Solar Flare Early Warning System" in res.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
