import json
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

from ..types import Instrument, QCFlag
from ..constants import GOES_SWPC_URL, GOES_EVENTS_URL


_UA = {"User-Agent": "AdityaFlareCast/0.1 (research; +python-urllib)"}


def _http_get_json(url: str, timeout_s: int = 30):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_goes_xrs_json(url: str = GOES_SWPC_URL) -> pd.DataFrame:
    """Fetch GOES XRS light curves.

    Handles BOTH observed schemas:
      A) per-channel rows: [{time_tag, satellite, flux, energy: '1-8 A'|'0.5-4 A'}, ...]
      B) combined rows:    [{time_tag, flux_short, flux_long}, ...]
    Returns columns: timestamp, flux_long (1-8 A), flux_short (0.5-4 A).
    """
    try:
        raw = _http_get_json(url)
    except Exception as e:
        print(f"GOES fetch failed: {e}")
        return pd.DataFrame()

    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]

    # ---- schema B fast path ----
    if raw and isinstance(raw[0], dict) and "flux_long" in raw[0]:
        return _rows_to_df(_combined_rows(raw))

    # ---- schema A: pivot per-channel rows on time_tag ----
    by_time = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ts = item.get("time_tag") or item.get("time")
        if not ts:
            continue
        try:
            dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            continue
        val = item.get("observed_flux", item.get("flux"))
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        energy = str(item.get("energy", ""))
        slot = by_time.setdefault(dt, {})
        if "8" in energy:          # '1-8 A'
            slot["flux_long"] = val
        elif "4" in energy:        # '0.5-4 A'
            slot["flux_short"] = val

    rows = [
        {
            "timestamp": dt,
            "flux_short": slot.get("flux_short", np.nan),
            "flux_long": slot.get("flux_long", np.nan),
        }
        for dt, slot in sorted(by_time.items())
    ]
    return _rows_to_df(rows)


def _combined_rows(raw) -> list:
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            dt = datetime.strptime((item.get("time_tag") or "")[:19],
                                   "%Y-%m-%dT%H:%M:%S")
            rows.append({
                "timestamp": dt,
                "flux_short": float(item.get("flux_short", np.nan)),
                "flux_long": float(item.get("flux_long", np.nan)),
            })
        except Exception:
            continue
    return rows


def _rows_to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["instrument"] = int(Instrument.GOES_XRS)
    df["energy_band"] = "1-8 A / 0.5-4 A"
    df["qc_flag"] = int(QCFlag.GOOD)
    df["source_id"] = "GOES_XRS"
    df["provenance"] = "NOAA SWPC"
    df = df.dropna(subset=["flux_long"]).sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_goes_events_json(url: Optional[str] = None) -> pd.DataFrame:
    """Fetch the NOAA GOES flare event list.

    Defaults to the 7-day catalogue (falls back to 'latest' on failure).
    Handles both observed schemas:
      7-day rows: {begin_time, max_time, max_class, max_xrlong, end_time, ...}
      latest row: same fields (single entry)
    """
    from ..constants import GOES_EVENTS_7DAY_URL

    raw = None
    for candidate in (url, GOES_EVENTS_7DAY_URL, GOES_EVENTS_URL):
        if candidate is None:
            continue
        try:
            raw = _http_get_json(candidate)
            if isinstance(raw, list) and len(raw) > 1:
                break
            if isinstance(raw, list) and len(raw) == 1:
                last_resort = raw
        except Exception:
            continue
    if raw is None:
        try:
            raw = last_resort  # type: ignore[name-defined]
        except NameError:
            print("GOES events fetch failed: all endpoints unreachable")
            return pd.DataFrame()

    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]

    rows = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        peak_time = item.get("max_time") or item.get("peak_time")
        goes_class = item.get("max_class") or item.get("goes_class", "")
        flux_raw = item.get("max_xrlong", item.get("peak_flux"))
        try:
            peak_flux = float(flux_raw) if flux_raw not in (None, "") else np.nan
        except (TypeError, ValueError):
            peak_flux = np.nan
        begin_time = item.get("begin_time", "")
        end_time = item.get("end_time", "")
        try:
            dt = datetime.strptime(str(peak_time)[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            continue
        rows.append({
            "timestamp": dt,
            "goes_class": str(goes_class),
            "peak_flux": peak_flux,
            "start_time": str(begin_time)[:19],
            "end_time": str(end_time)[:19],
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def get_goes_xrs_cached() -> pd.DataFrame:
    import os
    from ..constants import DATA_PATHS
    cache_dir = DATA_PATHS.get("cached", "data/cached")
    cache_file = os.path.join(cache_dir, "goes_xrs_sample.json")
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                raw = json.load(f)
            return _parse_goes_json(raw)
        except Exception:
            pass
    
    return pd.DataFrame()


def _parse_goes_json(raw):
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            ts = item.get("time_tag") or item.get("time")
            flux_short = float(item.get("flux_short", 0))
            flux_long = float(item.get("flux_long", 0))
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
            rows.append({
                "timestamp": dt,
                "flux_short": flux_short,
                "flux_long": flux_long,
                "instrument": Instrument.GOES_XRS,
                "energy_band": "1-8 Å / 0.5-4 Å",
                "qc_flag": QCFlag.GOOD,
                "source_id": "GOES_XRS",
                "provenance": "NOAA SWPC",
            })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
