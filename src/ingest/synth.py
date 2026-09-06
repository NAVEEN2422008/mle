import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from ..types import Instrument, QCFlag, FusedSample, FlareEvent
from ..constants import (
    LIGHT_SPEED_URL, AU_KM, AU_M, L1_HELIocentric_AU, EARTH_HELIOcetric_AU,
    SOLEXS_SDD1_AREA_MM2, SOLEXS_SDD2_AREA_MM2, SOLEXS_ENERGY_RANGE_KV,
    HEL1OS_CDTE_RANGE_KV, HEL1OS_CZT_RANGE_KV, HEL1OS_ENERGY_BANDS,
    NOWCAST_DEFAULTS, MERGE_DEFAULTS, GOES_CLASS_FLUX_THRESHOLDS,
    DATA_PATHS
)


class FlareModel:
    """Physics-based synthetic flare generator using beta profile model."""
    
    def __init__(self, base_rate=1000.0):
        self.base_rate = base_rate
        self.events = []
    
    def generate_beta_profile(self, peak_flux, duration_s, rise_frac=0.3):
        """Generate beta-profile flare light curve.
        
        Beta profile: F(t) = A * (t/T)^beta * (1 - t/T)^(1-beta)
        where T is the duration, beta controls the rise/decay asymmetry.
        """
        n = int(duration_s)
        t = np.linspace(0, 1, n)
        beta = 2.0  # shape parameter
        profile = (t ** beta) * ((1 - t) ** (1 - beta))
        profile = profile / np.max(profile) * peak_flux
        return profile
    
    def add_flare(self, start_dt, peak_flux, duration_s, instrument, band="total"):
        """Add a synthetic flare event."""
        profile = self.generate_beta_profile(peak_flux, duration_s)
        n = len(profile)
        
        # Generate timestamps
        timestamps = [start_dt + timedelta(seconds=i) for i in range(n)]
        
        # Add noise
        noise = np.random.normal(0, peak_flux * 0.05, n)
        counts = np.maximum(profile + noise, 1)
        
        event = FlareEvent(
            start_time=start_dt,
            peak_time=start_dt + timedelta(seconds=int(n * 0.3)),
            end_time=start_dt + timedelta(seconds=n),
            peak_flux_solexs=peak_flux if instrument == Instrument.SOLEXS_SDD2 else 0,
            peak_flux_hel1os=peak_flux if instrument in [Instrument.HEL1OS_CDTE, Instrument.HEL1OS_CZT] else 0,
            goes_class=self._classify_peak(peak_flux),
            confidence=0.9,
            duration_s=float(n)
        )
        self.events.append(event)
        
        return pd.DataFrame({
            "timestamp": timestamps,
            "counts": counts,
            "instrument": instrument,
            "energy_band": band,
            "qc_flag": QCFlag.GOOD,
            "source_id": f"synthetic_{instrument.name}",
            "provenance": "synthetic",
        })
    
    def _classify_peak(self, peak_flux):
        """Classify peak flux into GOES class."""
        if peak_flux < 1e-8:
            return "A"
        elif peak_flux < 1e-7:
            return "B"
        elif peak_flux < 1e-6:
            return "C"
        elif peak_flux < 1e-5:
            return "M"
        else:
            return "X"


def generate_synthetic_lightcurves():
    """Generate synthetic SoLEXS and HEL1OS light curves for testing."""
    import os
    synth_dir = DATA_PATHS.get("cached", "data/cached")
    Path(synth_dir).mkdir(parents=True, exist_ok=True)
    cache_file = os.path.join(synth_dir, "synthetic_lightcurves.parquet")
    
    if os.path.exists(cache_file):
        return pd.read_parquet(cache_file)
    
    print("Generating synthetic light curves...")
    
    model = FlareModel()
    base_time = datetime(2024, 7, 1, 12, 0, 0)
    
    # Generate flares with different magnitudes
    flare_specs = [
        (Instrument.SOLEXS_SDD2, "2-22 keV", 1000, 60, "C1"),
        (Instrument.HEL1OS_CDTE, "5-20 keV", 500, 45, "C0.5"),
        (Instrument.SOLEXS_SDD2, "2-22 keV", 5000, 90, "M5"),
        (Instrument.HEL1OS_CDTE, "5-20 keV", 2000, 60, "M2"),
        (Instrument.SOLEXS_SDD2, "2-22 keV", 50000, 120, "X5"),
        (Instrument.HEL1OS_CZT, "20-150 keV", 30000, 90, "X3"),
    ]
    
    all_dfs = []
    for i, (instr, band, peak, dur, goes) in enumerate(flare_specs):
        start = base_time + timedelta(minutes=i * 15)
        df = model.add_flare(start, peak, dur, instr, band)
        all_dfs.append(df)
    
    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
    else:
        df = pd.DataFrame()
    
    df.to_parquet(cache_file, index=False)
    print(f"Saved synthetic data to {cache_file}")
    return df