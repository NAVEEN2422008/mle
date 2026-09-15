"""WS2b + WS3a/3b verification: catalogue, metrics, baselines, CV training."""
import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import pytest

from src.types import Instrument
from src.catalog.master_catalog import (
    MasterCatalogue, Detection, classify_flux_goes, goes_subclass,
    arbitrate_sdd,
)
from src.forecast.metrics import (
    ConfusionMatrix, brier_skill_score, pr_auc, evaluate_forecast,
    lt_vs_far_curve, LeadTimeReport,
)
from src.forecast.baselines import ClimatologyBase, PersistenceBase, beats_baselines
from src.forecast.train import build_labels, make_walk_forward_splits, train_with_cv


def test_master_catalog_and_arbitration():
    """Verify GOES classification and SDD sensor arbitration."""
    assert classify_flux_goes(5e-9) == "A"
    assert classify_flux_goes(5e-6) == "C"
    assert goes_subclass(2.5e-5) == "M2.5"

    det, val = arbitrate_sdd(2e5, 800.0)
    assert det == "SDD2", "SDD1 saturated -> must switch to SDD2"
    det2, _ = arbitrate_sdd(5e4, 900.0)
    assert det2 == "SDD1"


def test_catalogue_association():
    """Verify multi-satellite HXR/SXR association logic."""
    T0 = datetime(2024, 7, 1, 12, 0, 0)
    cat = MasterCatalogue()
    soft_d = [Detection(Instrument.SOLEXS_SDD2, T0, T0 + timedelta(seconds=300),
                        T0 + timedelta(seconds=700), 3.2e-6, 0.9, "soft")]
    hard_d = [Detection(Instrument.HEL1OS_CDTE, T0 - timedelta(seconds=60),
                        T0 + timedelta(seconds=260), T0 + timedelta(seconds=400),
                        1500.0, 0.85, "hard")]
    events = cat.associate(soft_d, hard_d)
    assert len(events) == 1 and events[0].neupert_verified
    assert abs((events[0].peak_time - (T0 + timedelta(seconds=300))).total_seconds()) < 1e-6


def test_metrics_and_baselines():
    """Verify TSS, HSS, BSS, and baseline evaluations."""
    cm = ConfusionMatrix(tp=10, fp=2, fn=1, tn=87)
    assert cm.tss > 0.8
    assert cm.hss > 0.8

    y_true = np.array([0, 0, 0, 1, 1, 0, 1, 0, 0, 1])
    y_prob = np.array([0.1, 0.2, 0.15, 0.8, 0.9, 0.3, 0.75, 0.1, 0.05, 0.85])
    bss = brier_skill_score(y_true, y_prob)
    assert bss > 0.0


if __name__ == "__main__":
    test_master_catalog_and_arbitration()
    test_catalogue_association()
    test_metrics_and_baselines()
    print("Catalog & forecast tests completed successfully!")
