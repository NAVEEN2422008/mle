import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from ..types import Instrument, QCFlag, FusedSample
from ..constants import (
    LIGHT_SPEED_URL, AU_KM, AU_M, L1_HELIocentric_AU, EARTH_HELIOcetric_AU,
    SOLEXS_SDD1_AREA_MM2, SOLEXS_SDD2_AREA_MM2, SOLEXS_ENERGY_RANGE_KV,
    HEL1OS_CDTE_RANGE_KV, HEL1OS_CZT_RANGE_KV, HEL1OS_ENERGY_BANDS,
    NOWCAST_DEFAULTS, MERGE_DEFAULTS, GOES_CLASS_FLUX_THRESHOLDS,
    DATA_PATHS
)


def apply_light_travel_time_correction(df: pd.DataFrame, instrument: str) -> pd.DataFrame:
    """Apply light-travel-time correction to align timestamps to Earth frame."""
    if df.empty:
        return df
    
    df = df.copy()
    
    if "L1" in instrument.upper() or "ADITYA" in instrument.upper():
        offset_s = 5.0  # L1 is 1.5M km closer to Sun
    elif "SOLAR_ORBITER" in instrument.upper() or "STIX" in instrument.upper():
        offset_s = 249.0
    elif "STEREO" in instrument.upper():
        offset_s = 20.0
    elif "PARKER" in instrument.upper():
        offset_s = 476.0
    else:
        offset_s = 0.0
    
    df["timestamp"] = pd.to_datetime(df["timestamp"]) + pd.Timedelta(seconds=offset_s)
    df["ltt_offset_s"] = offset_s
    return df


def synchronize_timestamps(solexs_df: pd.DataFrame, hel1os_df: pd.DataFrame, goes_df: pd.DataFrame) -> pd.DataFrame:
    """Synchronize all instrument timestamps to a common 1-second grid."""
    all_dfs = []
    
    if not solexs_df.empty:
        df = apply_light_travel_time_correction(solexs_df, "ADITYA_L1")
        df["source"] = "solexs"
        all_dfs.append(df)
    
    if not hel1os_df.empty:
        df = apply_light_travel_time_correction(hel1os_df, "ADITYA_L1")
        df["source"] = "hel1os"
        all_dfs.append(df)
    
    if not goes_df.empty:
        df = apply_light_travel_time_correction(goes_df, "GOES")
        df["source"] = "goes"
        all_dfs.append(df)
    
    if not all_dfs:
        return pd.DataFrame()
    
    merged = pd.concat(all_dfs, ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"])
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    
    return merged


def create_unified_grid(df: pd.DataFrame, interval_s: int = 1) -> pd.DataFrame:
    """Create a unified timestamp grid and resample all data to it."""
    if df.empty:
        return df
    
    start = df["timestamp"].min()
    end = df["timestamp"].max()
    grid = pd.date_range(start, end, freq=f"{interval_s}s")
    
    result_rows = []
    for ts in grid:
        mask = df["timestamp"] == ts
        if mask.any():
            row = df[mask].iloc[0].to_dict()
            result_rows.append(row)
        else:
            result_rows.append({"timestamp": ts, "qc_flag": QCFlag.FILLED})
    
    return pd.DataFrame(result_rows)