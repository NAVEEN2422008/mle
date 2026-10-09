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


def test_api_model_load(client):
    """Verify that /api/model/load correctly loads the real SpatioTemporalGraphTransformer checkpoint."""
    res = client.get("/api/model/load")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "loaded"
    assert "checkpoint_path" in data
    assert "learned_alpha" in data
    assert "learned_beta" in data
    assert data["architecture"] == "SpatioTemporalGraphTransformer (5-Node GNN + PINN)"


def test_api_inference_custom_data(client):
    """Verify that /api/inference produces multi-horizon flare forecasts on input telemetry."""
    dummy_stream = [
        {"timestamp": f"2024-10-03T12:{i:02d}:00Z", "soft": 100.0 + i * 2.0, "hard": 20.0 + i * 1.5}
        for i in range(15)
    ]
    payload = {
        "model_path": "models/spatiotemporal_graph_transformer.pt",
        "data": dummy_stream
    }
    res = client.post("/api/inference", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "predictions" in data
    assert len(data["predictions"]) == 3
    assert data["predictions"][0]["horizon_minutes"] == 15
    assert 0.0 <= data["predictions"][0]["probability"] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
