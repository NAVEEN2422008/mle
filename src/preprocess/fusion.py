import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from scipy.interpolate import interp1d

from ..types import Instrument, QCFlag, FusedSample
from ..constants import (
    MERGE_DEFAULTS, DATA_PATHS
)


class KalmanFilter1D:
    """Simple 1D Kalman filter for flux fusion."""
    
    def __init__(self, process_noise=1e-4, measurement_noise=1e-2):
        self.x = 0.0
        self.P = 1.0
        self.Q = process_noise
        self.R = measurement_noise
    
    def predict(self):
        self.P += self.Q
        return self.x
    
    def update(self, z):
        K = self.P / (self.P + self.R)
        self.x = self.x + K * (z - self.x)
        self.P = (1 - K) * self.P
        return self.x


def inverse_variance_fusion(measurements, uncertainties):
    """Fuse multiple measurements using inverse-variance weighting."""
    if len(measurements) == 0:
        return np.nan, np.nan
    if len(measurements) == 1:
        return measurements[0], uncertainties[0]
    
    weights = np.array([1.0 / (u**2 + 1e-12) for u in uncertainties])
    weighted_sum = np.sum(weights * np.array(measurements))
    total_weight = np.sum(weights)
    
    fused_value = weighted_sum / total_weight
    fused_uncertainty = np.sqrt(1.0 / total_weight)
    
    return fused_value, fused_uncertainty


def fuse_instruments(merged_df: pd.DataFrame) -> pd.DataFrame:
    """Fuse soft and hard X-ray measurements from multiple instruments."""
    if merged_df.empty:
        return pd.DataFrame()
    
    merged_df = merged_df.copy()
    merged_df["timestamp"] = pd.to_datetime(merged_df["timestamp"])
    merged_df = merged_df.sort_values("timestamp").reset_index(drop=True)
    
    fusion_method = MERGE_DEFAULTS.get("fusion_method", "inverse_variance")
    
    fused_rows = []
    soft_kf = KalmanFilter1D()
    hard_kf = KalmanFilter1D()
    
    soft_band_name = "soft"
    hard_band_name = "hard"
    
    for idx, row in merged_df.iterrows():
        ts = row["timestamp"]
        
        soft_flux = np.nan
        soft_sigma = np.nan
        n_soft = 0
        hard_flux = np.nan
        hard_sigma = np.nan
        n_hard = 0
        
        if row.get("source") == "solexs":
            soft_flux = float(row.get("counts", 0))
            soft_sigma = np.sqrt(soft_flux) if soft_flux > 0 else 1.0
            n_soft = 1
        elif row.get("source") == "goes":
            soft_flux = float(row.get("flux_long", 0)) * 1e5
            soft_sigma = soft_flux * 0.1 if soft_flux > 0 else 0.1
            n_soft = 1
        elif row.get("source") == "hel1os":
            hard_flux = float(row.get("counts", 0))
            hard_sigma = np.sqrt(hard_flux) if hard_flux > 0 else 1.0
            n_hard = 1
        
        if fusion_method == "kalman" and not np.isnan(soft_flux):
            soft_kf.predict()
            soft_flux = soft_kf.update(soft_flux)
            soft_sigma = soft_kf.P
        
        if fusion_method == "kalman" and not np.isnan(hard_flux):
            hard_kf.predict()
            hard_flux = hard_kf.update(hard_flux)
            hard_sigma = hard_kf.P
        
        hardness = np.nan
        if not np.isnan(soft_flux) and not np.isnan(hard_flux) and soft_flux > 0:
            hardness = hard_flux / soft_flux
        
        if not np.isnan(soft_flux) or not np.isnan(hard_flux):
            qc = QCFlag(row.get("qc_flag", QCFlag.GOOD)) if pd.notna(row.get("qc_flag")) else QCFlag.GOOD
        else:
            qc = QCFlag.FILLED
        
        fused_rows.append(FusedSample(
            timestamp=ts,
            soft_flux=soft_flux if not np.isnan(soft_flux) else 0.0,
            soft_sigma=soft_sigma if not np.isnan(soft_sigma) else 0.0,
            hard_flux=hard_flux if not np.isnan(hard_flux) else 0.0,
            hard_sigma=hard_sigma if not np.isnan(hard_sigma) else 0.0,
            hardness_ratio=hardness if not np.isnan(hardness) else 0.0,
            qc_flag=qc,
            n_sources_soft=n_soft,
            n_sources_hard=n_hard
        ))
    
    return pd.DataFrame([f.to_dict() if hasattr(f, 'to_dict') else {
        'timestamp': f.timestamp,
        'soft_flux': f.soft_flux,
        'soft_sigma': f.soft_sigma,
        'hard_flux': f.hard_flux,
        'hard_sigma': f.hard_sigma,
        'hardness_ratio': f.hardness_ratio,
        'n_sources_soft': f.n_sources_soft,
        'n_sources_hard': f.n_sources_hard
    } for f in fused_rows])