"""Real Aditya-L1 L1 data ingest for ML pipeline.

Reads genuine PRADAN SoLEXS + HEL1OS archives, aligns on a common 1-min grid
with GTI masking, and returns a DataFrame with (timestamp, soft, hard) columns
compatible with FlareForecastPipeline.

SoLEXS: 2-22 keV (SDD2 preferred) -> soft
HEL1OS: CZT 40-60 keV (genuine HXR above SoLEXS ceiling) -> hard
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from astropy.io import fits


# Energy band selection
SOLEXS_HIGH_KEV = 22.0
HEL1OS_TARGET_BAND = "40-60 keV"  # CZT 40-60 keV: genuine HXR, good sensitivity
_BAND_RE = re.compile(r"BAND_(\d+(?:\.\d+)?)KEV_TO_(\d+(?:\.\d+)?)KEV")


def _open_fits(z: zipfile.ZipFile, member: str):
    raw = z.read(member)
    if member.lower().endswith(".gz"):
        import gzip
        raw = gzip.decompress(raw)
    return fits.open(io.BytesIO(raw))


def _rate_series(hdu):
    """Extract (time_seconds, rate) from a light-curve HDU."""
    import io
    cols = [c.upper() for c in hdu.columns.names] if hasattr(hdu, "columns") else []
    data = hdu.data
    tcol = next((c for c in ("MJD", "ISOT", "TIME", "T", "SEC") if c in cols), None)
    rcol = next((c for c in ("CTR", "RATE", "COUNTS", "COUNT_RATE", "RATE_COUNTS",
                             "COUNTS_CORR", "CORR_RATE", "FLUX")
                 if c in cols), None)
    if rcol is None:
        return None
    if tcol == "MJD":
        t = (np.asarray(data[tcol], float) - 40587.0) * 86400.0
    elif tcol == "ISOT":
        isot = np.asarray(data[tcol])
        t = np.array([pd.Timestamp(s).timestamp() for s in isot], dtype=float)
    else:
        t = np.asarray(data[tcol], float) if tcol else np.arange(len(data[rcol]), dtype=float)
    return t, np.asarray(data[rcol], float), rcol

def _gti_intervals(z: zipfile.ZipFile, members):
    """Return GTI as [(start_unix, end_unix), ...] merged and sorted.

    Handles both MJD (HEL1OS, ~60000) and Unix (SoLEXS, ~1.7e9) epochs.
    """
    spans = []
    for m in members:
        if not (m.lower().endswith(".gti.gz") or
                ("aux/gtic" in m.lower() and m.lower().endswith(".fits"))):
            continue
        with _open_fits(z, m) as h:
            for hdu in h[1:]:
                cols = [c.upper() for c in hdu.columns.names] if hasattr(hdu, "columns") else []
                s = next((c for c in ("TSTART", "START", "GSTART") if c in cols), None)
                e = next((c for c in ("TSTOP", "STOP", "GSTOP", "END") if c in cols), None)
                if s and e:
                    sv = np.asarray(hdu.data[s], float)
                    ev = np.asarray(hdu.data[e], float)
                    if sv.size == 0:
                        continue
                    # Detect epoch: MJD ~ 60000, Unix ~ 1.7e9
                    median_val = float(np.median(np.concatenate([sv, ev])))
                    if median_val < 1e6:
                        # MJD -> Unix
                        sv = (sv - 40587.0) * 86400.0
                        ev = (ev - 40587.0) * 86400.0
                    # else already Unix
                    spans += list(zip(sv, ev))
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(float(a), float(b)) for a, b in merged]


def _in_gti(t, gti):
    if not gti:
        return np.ones(len(t), bool)
    ok = np.zeros(len(t), bool)
    for a, b in gti:
        ok |= (t >= a) & (t < b)
    return ok


def _resample_to(t, rate, tgrid):
    """Linear resample onto tgrid (1 Hz)."""
    idx = np.searchsorted(t, tgrid)
    idx = np.clip(idx, 1, len(t) - 1)
    lo, hi = t[idx - 1], t[idx]
    w = np.where(hi > lo, (tgrid - lo) / np.maximum(hi - lo, 1e-9), 0.0)
    return rate[idx - 1] * (1 - w) + rate[idx] * w


def read_solexs_zip(path: str):
    """Read SoLEXS L1 zip -> (t_unix, rate, gti_list)."""
    z = zipfile.ZipFile(path)
    lcs = [m for m in z.namelist() if ".lc." in m or m.endswith("lc.fits.gz")]
    best = None
    best_rate = None
    best_gti = None
    for m in lcs:
        det = "SDD2" if "SDD2" in m.upper() else ("SDD1" if "SDD1" in m.upper() else "SDD?")
        if det != "SDD2":
            continue
        with _open_fits(z, m) as h:
            for hdu in h[1:]:
                got = _rate_series(hdu)
                if got:
                    best = got
                    break
            if best:
                break
    if not best:
        raise ValueError(f"No usable SDD2 light curve in {path}")
    t, rate, _ = best
    gti = _gti_intervals(z, z.namelist())
    return t, rate, gti


def read_hel1os_zip(path: str, target_band: str = HEL1OS_TARGET_BAND):
    """Read HEL1OS L1 zip -> (t_unix, rate, gti_list) for the target band."""
    z = zipfile.ZipFile(path)
    lcs = [m for m in z.namelist()
           if ("lightcurve_cdte" in m.lower() or "lightcurve_czt" in m.lower())
           and m.lower().endswith(".fits")]
    best = None
    for m in lcs:
        with _open_fits(z, m) as h:
            for hdu in h[1:]:
                got = _rate_series(hdu)
                if not got:
                    continue
                ext = hdu.name or ""
                bm = _BAND_RE.search(ext)
                if bm:
                    lo, hi = float(bm.group(1)), float(bm.group(2))
                    band_str = f"{lo:g}-{hi:g} keV"
                else:
                    band_str = "unknown"
                if band_str == target_band:
                    best = (got[0], got[1], band_str)
                    break
            if best:
                break
    if not best:
        raise ValueError(f"No {target_band} band found in {path}")
    t, rate, _ = best
    gti = _gti_intervals(z, z.namelist())
    return t, rate, gti


def align_solexs_hel1os(solexs_path: str, hel1os_path: str,
                        target_band: str = HEL1OS_TARGET_BAND,
                        resample_min: int = 1):
    """Align SoLEXS and HEL1OS on a common grid with GTI masking.

    Returns DataFrame with columns: timestamp (datetime), soft (counts/s), hard (counts/s).
    """
    ts, rs, soft_gti = read_solexs_zip(solexs_path)
    th, rh, _ = read_hel1os_zip(hel1os_path, target_band)

    # Common time range
    lo = int(max(ts.min(), th.min()))
    hi = int(min(ts.max(), th.max()))
    if hi - lo < 600:
        raise ValueError("Insufficient time overlap")

    # 1-second grid
    tgrid = np.arange(lo, hi + 1, dtype=float)
    sxr = _resample_to(ts, rs, tgrid)
    hxr = _resample_to(th, rh, tgrid)

    # GTI mask
    # _gti_intervals now auto-detects MJD vs Unix and returns Unix seconds
    hard_gti_unix = _gti_intervals(zipfile.ZipFile(hel1os_path),
                                   zipfile.ZipFile(hel1os_path).namelist())
    ok = _in_gti(tgrid, soft_gti) & _in_gti(tgrid, hard_gti_unix)
    if ok.sum() < 600:
        raise ValueError("Insufficient GTI overlap")

    # Resample to target cadence (default 1 min = 60 s)
    if resample_min > 1:
        step = resample_min * 60
        tgrid = tgrid[::step]
        sxr = sxr[::step]
        hxr = hxr[::step]
        ok = ok[::step]

    # Apply mask
    tgrid = tgrid[ok]
    sxr = sxr[ok]
    hxr = hxr[ok]

    # Convert to datetime
    timestamps = pd.to_datetime(tgrid, unit="s", utc=True)

    return pd.DataFrame({
        "timestamp": timestamps,
        "soft": sxr.astype(float),
        "hard": hxr.astype(float),
    })


def find_matching_pairs(raw_dir: str = "data/raw"):
    """Find SoLEXS/HEL1OS pairs by date."""
    slx = sorted(glob.glob(os.path.join(raw_dir, "AL1_SLX_L1_*.zip")))
    hld = sorted(glob.glob(os.path.join(raw_dir, "HLS_*.zip")))
    pairs = []
    for s in slx:
        m = re.search(r"_L1_(\d{8})_", os.path.basename(s))
        if not m:
            continue
        date = m.group(1)
        h = next((p for p in hld if f"HLS_{date}_" in p), None)
        if h:
            pairs.append((date, s, h))
    return pairs


def build_aditya_pipeline_df(raw_dir: str = "data/raw",
                             target_band: str = HEL1OS_TARGET_BAND,
                             resample_min: int = 1) -> pd.DataFrame:
    """Build a single concatenated DataFrame from all available Aditya-L1 pairs.

    Concatenates all matching SoLEXS/HEL1OS pairs, sorted by time.
    """
    pairs = find_matching_pairs(raw_dir)
    frames = []
    for date, slx, hld in pairs:
        try:
            df = align_solexs_hel1os(slx, hld, target_band, resample_min)
            df["date"] = date
            frames.append(df)
            print(f"  {date}: {len(df)} samples")
        except Exception as e:
            print(f"  {date}: SKIPPED - {e}")
    if not frames:
        raise ValueError("No valid Aditya-L1 pairs found")
    return pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)


if __name__ == "__main__":
    import sys
    raw = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    df = build_aditya_pipeline_df(raw)
    print(f"\nTotal: {len(df)} samples")
    print(f"Time range: {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(df.head())