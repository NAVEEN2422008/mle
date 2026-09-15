"""Automated Unit Tests for Phase 6: Space-Weather Validation & Superstorm Stress-Testing."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.test_historic_superstorms import (
    build_historic_superstorm_series,
    run_superstorm_simulation,
)


def test_historic_superstorm_generation():
    """Verify that the historic superstorm simulation generates valid multi-spectral events."""
    df_storm, events = build_historic_superstorm_series()
    
    assert len(df_storm) == 1800
    assert "soft" in df_storm.columns
    assert "hard" in df_storm.columns
    assert len(events) == 3
    
    # Check that X8.7 superflare is present and reaches >= 800,000 nW/m^2
    max_flux = df_storm["soft"].max()
    assert max_flux >= 800000.0


def test_phase6_end_to_end_superstorm_simulation():
    """Verify that Phase 6 multi-tier benchmark runs cleanly and returns verified skill metrics."""
    res = run_superstorm_simulation()
    
    assert "report_meta" in res
    assert "avg_lead_time" in res
    
    report = res["report_meta"]
    # Verify space-weather skill standards
    assert report.tss >= 0.70, f"TSS should be >= 0.70, got {report.tss}"
    assert report.pod >= 0.80, f"POD should be >= 80%, got {report.pod}"
    assert res["avg_lead_time"] >= 10.0, f"Lead time should be >= 10 mins, got {res['avg_lead_time']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
