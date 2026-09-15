"""Multi-Instrument Fusion and Advanced Feature Engineering for Aditya-L1.

Includes:
1. Inverse-variance sensor fusion and Kalman 1D state estimation.
2. Dynamic background baseline subtraction (Solar Cycle 25 drift adaptation via rolling quantile).
3. Savitzky-Golay numerical derivatives (dSXR/dt, dHXR/dt).
4. Continuous Wavelet Transform (CWT Morlet) for Quasi-Periodic Pulsations (QPPs) and microbursts.
5. HOPE-inspired physical proxies: Temperature (Te), Emission Measure (EM), Hardness Ratios.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import scipy.signal as signal

from ..types import Instrument, QCFlag, FusedSample
from ..constants import MERGE_DEFAULTS


class KalmanFilter1D:
    """Optimal 1D linear Kalman state estimator for solar X-ray flux tracking."""

    def __init__(self, process_noise: float = 1e-4, measurement_noise: float = 1e-2) -> None:
        self.x = 0.0
        self.P = 1.0
        self.Q = process_noise
        self.R = measurement_noise

    def predict(self) -> float:
        self.P += self.Q
        return self.x

    def update(self, z: float) -> float:
        K = self.P / (self.P + self.R + 1e-12)
        self.x = self.x + K * (z - self.x)
        self.P = (1.0 - K) * self.P
        return self.x


def inverse_variance_fusion(
    measurements: Union[List[float], np.ndarray],
    uncertainties: Union[List[float], np.ndarray],
) -> Tuple[float, float]:
    """
    Fuse multiple sensor measurements via optimal inverse-variance weighting.
    Var(Fused) = 1 / sum(1 / sigma_i^2)
    """
    m = np.asarray(measurements, dtype=float)
    u = np.asarray(uncertainties, dtype=float)
    valid = ~np.isnan(m) & ~np.isnan(u) & (u > 0)
    m, u = m[valid], u[valid]

    if len(m) == 0:
        return np.nan, np.nan
    if len(m) == 1:
        return float(m[0]), float(u[0])

    weights = 1.0 / (u**2 + 1e-12)
    total_weight = np.sum(weights)
    fused_val = np.sum(weights * m) / total_weight
    fused_unc = np.sqrt(1.0 / total_weight)
    return float(fused_val), float(fused_unc)


def compute_wavelet_qpp_power(signal_arr: np.ndarray, num_scales: int = 8) -> np.ndarray:
    """
    Extract high-frequency Quasi-Periodic Pulsation (QPP) power using Morlet continuous wavelets.
    Pre-flare micro-bursts exhibit localized wavelet power surges in 10s-120s periods.
    Uses FFT convolution over multi-scale Morlet wavelets: psi(t, s) = exp(-t^2/(2*s^2)) * exp(i*w0*t/s).
    """
    arr = np.asarray(signal_arr, dtype=float)
    if len(arr) < 16:
        return np.zeros(len(arr), dtype=float)

    total_power = np.zeros(len(arr), dtype=float)
    scales = np.linspace(2, 16, num_scales)

    for s in scales:
        M = int(max(15, 6 * s))
        if M % 2 == 0:
            M += 1
        t = np.linspace(-3, 3, M)
        wavelet_r = np.exp(-t**2 / 2.0) * np.cos(5.0 * t) / np.sqrt(s)
        wavelet_i = np.exp(-t**2 / 2.0) * np.sin(5.0 * t) / np.sqrt(s)

        conv_r = signal.fftconvolve(arr, wavelet_r, mode="same")
        conv_i = signal.fftconvolve(arr, wavelet_i, mode="same")
        total_power += (conv_r**2 + conv_i**2)

    return total_power / max(num_scales, 1)


def compute_physics_features(df: pd.DataFrame, cadence_s: float = 1.0) -> pd.DataFrame:
    """
    Extracts complete 30-Dimensional Precursor Physics Feature Vector for multi-tier ML & DL.
    
    Feature Categories:
    1. Base & Quiescent Solar Cycle 25 Baselines (4 features)
    2. 1st & 2nd Order Flux Derivatives & Accelerations (6 features)
    3. Multi-Scale EMA Momentum & Turbulence (6 features)
    4. Astrophysical Spectral Indices & Plasma Proxies (6 features)
    5. Neupert Precursor Coupling & Cross-Band Lag (4 features)
    6. Multi-Scale Morlet Continuous Wavelet QPP Power (4 features)
    """
    out = df.copy()
    dt = max(float(cadence_s), 0.1)

    # Identify primary columns
    s_col = "soft" if "soft" in out.columns else ("solexs_flux" if "solexs_flux" in out.columns else None)
    h_col = "hard" if "hard" in out.columns else ("hel1os_flux" if "hel1os_flux" in out.columns else None)

    if s_col is None:
        for c in ["counts", "flux", "rate", "goes_soft"]:
            if c in out.columns:
                s_col = c
                break
    if h_col is None:
        for c in ["goes_hard", "flux_short"]:
            if c in out.columns:
                h_col = c
                break

    if s_col is None:
        return out

    s_num = pd.to_numeric(out[s_col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(1e-3).to_numpy(dtype=float)
    s_vals = np.clip(s_num, 1e-4, 1e9)
    
    if h_col and h_col in out.columns:
        h_num = pd.to_numeric(out[h_col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(1e-4).to_numpy(dtype=float)
        h_vals = np.clip(h_num, 1e-5, 1e9)
    else:
        h_vals = np.clip(s_vals * 0.1, 1e-5, 1e9)

    eps = 1e-6
    n = len(s_vals)

    # =========================================================================
    # Group 1: Base & Solar Cycle 25 Baselines (4 features)
    # =========================================================================
    out["f01_soft_flux"] = s_vals
    out["f02_hard_flux"] = h_vals
    
    # Dynamic background subtraction (6-hour 5th percentile)
    window_6h = int(6 * 3600 / dt)
    min_p_6h = max(10, min(n // 5, window_6h // 10))
    s_series = pd.Series(s_vals, index=out.index)
    bg_series = s_series.rolling(window_6h, min_periods=min_p_6h).quantile(0.05).bfill().ffill()
    out["f03_soft_bg"] = bg_series.values
    out["f04_soft_excess"] = np.maximum(0.0, s_vals - bg_series.values)

    # =========================================================================
    # Group 2: 1st & 2nd Order Derivatives (Velocity & Acceleration) (6 features)
    # =========================================================================
    win_sg = 11 if n >= 11 else (n // 2 * 2 + 1)
    if win_sg >= 5:
        d_s = signal.savgol_filter(s_vals, window_length=win_sg, polyorder=2, deriv=1, delta=dt)
        d_h = signal.savgol_filter(h_vals, window_length=win_sg, polyorder=2, deriv=1, delta=dt)
        d2_s = signal.savgol_filter(s_vals, window_length=win_sg, polyorder=2, deriv=2, delta=dt)
        d2_h = signal.savgol_filter(h_vals, window_length=win_sg, polyorder=2, deriv=2, delta=dt)
    else:
        d_s = np.gradient(s_vals, dt)
        d_h = np.gradient(h_vals, dt)
        d2_s = np.gradient(d_s, dt)
        d2_h = np.gradient(d_h, dt)

    out["f05_d_soft_dt"] = d_s
    out["f06_d_hard_dt"] = d_h
    out["f07_d2_soft_dt2"] = d2_s
    out["f08_d2_hard_dt2"] = d2_h
    out["f09_rel_rate_soft"] = d_s / (s_vals + eps)
    out["f10_rel_rate_hard"] = d_h / (h_vals + eps)

    # =========================================================================
    # Group 3: Multi-Scale EMA Momentum & Turbulence (6 features)
    # =========================================================================
    span_5m = max(5, int(300 / dt))
    span_15m = max(15, int(900 / dt))
    span_60m = max(60, int(3600 / dt))
    
    ema_s_5m = s_series.ewm(span=span_5m).mean().bfill().values
    ema_s_15m = s_series.ewm(span=span_15m).mean().bfill().values
    ema_s_60m = s_series.ewm(span=span_60m).mean().bfill().values
    
    h_series = pd.Series(h_vals, index=out.index)
    ema_h_5m = h_series.ewm(span=span_5m).mean().bfill().values
    ema_h_15m = h_series.ewm(span=span_15m).mean().bfill().values
    
    out["f11_soft_ema_5m_ratio"] = s_vals / (ema_s_5m + eps)
    out["f12_soft_ema_15m_ratio"] = s_vals / (ema_s_15m + eps)
    out["f13_soft_ema_60m_ratio"] = s_vals / (ema_s_60m + eps)
    out["f14_hard_ema_5m_ratio"] = h_vals / (ema_h_5m + eps)
    out["f15_hard_ema_15m_ratio"] = h_vals / (ema_h_15m + eps)
    out["f16_soft_std_15m"] = s_series.rolling(span_15m, min_periods=3).std().fillna(0.0).values

    # =========================================================================
    # Group 4: Astrophysical Spectral Indices & Plasma Proxies (6 features)
    # =========================================================================
    out["f17_hardness_ratio"] = h_vals / (out["f04_soft_excess"].values + eps)
    out["f18_log_hardness"] = np.log10(np.clip(h_vals / (s_vals + eps), 1e-4, 1e4))
    out["f19_temp_proxy_te"] = (h_vals / (s_vals + eps)) ** 0.5
    out["f20_em_proxy"] = (s_vals ** 2) / (h_vals + eps)
    out["f21_thermal_integral"] = np.cumsum(s_vals * dt) / 1e6
    out["f22_nonthermal_power"] = h_vals * np.maximum(0.0, d_s)

    # =========================================================================
    # Group 5: Neupert Precursor Coupling & Dynamics (4 features)
    # =========================================================================
    out["f23_neupert_coupling"] = (h_vals * np.maximum(0.0, d_s)) / 1000.0
    
    # Rolling Pearson correlation between HXR and dSXR/dt over 10m window
    win_10m = max(10, int(600 / dt))
    ds_series = pd.Series(np.maximum(0.0, d_s), index=out.index)
    roll_corr = h_series.rolling(win_10m, min_periods=5).corr(ds_series).fillna(0.0).values
    out["f24_neupert_corr_10m"] = roll_corr
    
    # Neupert integral residual: SXR - cumulative sum of HXR
    h_cum = np.cumsum(h_vals * dt)
    scale_alpha = np.mean(s_vals) / (np.mean(h_cum) + eps)
    out["f25_neupert_residual"] = np.abs(s_vals - scale_alpha * h_cum) / (s_vals + eps)
    
    # Estimated time-lag peak proxy (cross-correlation slope)
    out["f26_cross_band_lag_proxy"] = (ema_h_5m - ema_s_5m) / (s_vals + eps)

    # =========================================================================
    # Group 6: Multi-Scale Morlet Continuous Wavelet QPP Power (4 features)
    # =========================================================================
    out["f27_qpp_power_10s"] = compute_wavelet_qpp_power(h_vals, num_scales=4)
    out["f28_qpp_power_30s"] = compute_wavelet_qpp_power(h_vals, num_scales=8)
    out["f29_qpp_power_60s"] = compute_wavelet_qpp_power(h_vals, num_scales=12)
    out["f30_qpp_total_power"] = (out["f27_qpp_power_10s"] + out["f28_qpp_power_30s"] + out["f29_qpp_power_60s"]) / 3.0

    # Retain backward compatibility aliases
    out["solexs_bg"] = out["f03_soft_bg"]
    out["solexs_excess"] = out["f04_soft_excess"]
    out["d_solexs_dt"] = out["f05_d_soft_dt"]
    out["d_hel1os_dt"] = out["f06_d_hard_dt"]
    out["hardness_ratio"] = out["f17_hardness_ratio"]
    out["qpp_wavelet_power"] = out["f30_qpp_total_power"]
    out["temp_proxy"] = out["f19_temp_proxy_te"]
    out["em_proxy"] = out["f20_em_proxy"]

    # Final numerical safety guard: ensure zero NaN / Inf across all feature columns
    f_cols = [c for c in out.columns if c.startswith("f")]
    out[f_cols] = out[f_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)

    return out


def fuse_instruments(merged_df: pd.DataFrame) -> pd.DataFrame:
    """Fuse multi-instrument soft and hard X-ray measurements into standardized FusedSample series."""
    if merged_df.empty:
        return pd.DataFrame()

    df = merged_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    fusion_method = MERGE_DEFAULTS.get("fusion_method", "inverse_variance")

    fused_rows: List[FusedSample] = []
    soft_kf = KalmanFilter1D()
    hard_kf = KalmanFilter1D()

    for _, row in df.iterrows():
        ts = row["timestamp"]
        soft_flux = np.nan
        soft_sigma = np.nan
        n_soft = 0
        hard_flux = np.nan
        hard_sigma = np.nan
        n_hard = 0

        source = str(row.get("source", ""))
        if source == "solexs":
            soft_flux = float(row.get("counts", 0.0))
            soft_sigma = np.sqrt(max(soft_flux, 1.0))
            n_soft = 1
        elif source == "goes":
            soft_flux = float(row.get("flux_long", 0.0)) * 1e5
            soft_sigma = max(soft_flux * 0.1, 0.1)
            n_soft = 1
        elif source == "hel1os":
            hard_flux = float(row.get("counts", 0.0))
            hard_sigma = np.sqrt(max(hard_flux, 1.0))
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

        qc = QCFlag.GOOD if (not np.isnan(soft_flux) or not np.isnan(hard_flux)) else QCFlag.FILLED

        fused_rows.append(
            FusedSample(
                timestamp=ts,
                soft_flux=soft_flux if not np.isnan(soft_flux) else 0.0,
                soft_sigma=soft_sigma if not np.isnan(soft_sigma) else 0.0,
                hard_flux=hard_flux if not np.isnan(hard_flux) else 0.0,
                hard_sigma=hard_sigma if not np.isnan(hard_sigma) else 0.0,
                hardness_ratio=hardness if not np.isnan(hardness) else 0.0,
                qc_flag=qc,
                n_sources_soft=n_soft,
                n_sources_hard=n_hard,
            )
        )

    out_df = pd.DataFrame([s.to_dict() for s in fused_rows])
    return out_df