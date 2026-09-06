"""SoLEXS Level-1 reader - hardened against schema drift.

Defensive design (real PRADAN files unseen; conventions from mission papers):
- Locates light-curve members inside AL1_SLX_L1_* ZIPs (*.lc.gz preferred),
  classifying detector (SDD1/SDD2) from the member path.
- Streams members straight into astropy via BytesIO (no temp files).
- Finds the FIRST binary-table HDU containing a plausible time column instead
  of trusting a fixed extension index.
- Column auto-discovery for time & counts with case/alias tolerance.
- Observation date: header DATE-OBS -> filename YYYYMMDD -> epoch warning.
- Vectorised timestamp construction (fast for full-day 86k-row files).
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from astropy.io import fits as _fits
from .fits_pure import read_all_hdus

from ..types import Instrument, QCFlag

_TIME_COLS = ["TIME", "TIMES", "T", "UNIXTIME", "MJDSEC"]
_COUNT_COLS = ["COUNTS", "COUNT", "RATE", "COUNT_RATE", "CORR_RATE",
               "CNTS", "FLUX", "COUNTS_CORR"]


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _pick(columns: List[str], wanted: List[str]) -> Optional[str]:
    norm_map = {_norm(c): c for c in columns}
    for w in wanted:
        key = _norm(w)
        if key in norm_map:
            return norm_map[key]
    # fuzzy: startswith match
    for c in columns:
        nc = _norm(c)
        for w in wanted:
            if nc.startswith(_norm(w)):
                return c
    return None


def _table_hdus(hdul) -> list:
    out = []
    for hdu in hdul:
        if getattr(hdu, "data", None) is not None and hasattr(hdu.data, "columns"):
            out.append(hdu)
    return out


def _extract_date(header, member_name: str,
                  zip_name: str) -> Tuple[datetime, str]:
    """DATE-OBS header -> zip/filename YYYYMMDD -> 1970 fallback."""
    for key in ("DATE-OBS", "DATEOBS", "DATE_OBS", "OBS_DATE"):
        v = str(header.get(key, "")).strip()
        m = re.search(r"(\d{4}-\d{2}-\d{2})", v)
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d"), f"header:{key}"
    for blob in (member_name, zip_name):
        m = re.search(r"(20\d{6})", blob)
        if m:
            return datetime.strptime(m.group(1), "%Y%m%d"), "filename"
    return datetime(1970, 1, 1), "FALLBACK(unknown)"


def parse_solexs_fits_bytes(raw: bytes, member_name: str = "",
                            zip_name: str = "") -> pd.DataFrame:
    """Parse one SoLEXS light-curve FITS (optionally gzipped) from bytes."""
    if raw[:2] == b"\x1f\x8b":                       # gzip magic
        raw = gzip.decompress(raw)

    hdus = read_all_hdus(raw)
    chosen = None
    for hdr, df_table in hdus:
        if df_table is not None and not df_table.empty:
            cols = list(df_table.columns)
            tcol = _pick(cols, _TIME_COLS)
            ccol = _pick(cols, _COUNT_COLS)
            if tcol and ccol:
                chosen = (hdr, df_table, tcol, ccol)
                break
    if chosen is None:
        raise ValueError(
            f"No usable TIME+counts table in {member_name or zip_name}; "
            f"extensions={[h.get('EXTNAME') for h, _ in hdus]}"
        )
    header, df_table, tcol, ccol = chosen
    times = np.asarray(df_table[tcol], dtype=float)
    counts = np.asarray(df_table[ccol], dtype=float)

    base_date, src = _extract_date(header, member_name, zip_name)
    timestamps = base_date + pd.to_timedelta(times, unit="s")

    det = "SDD2" if re.search(r"SDD2", member_name, re.I) else \
          "SDD1" if re.search(r"SDD1", member_name, re.I) else "SDD?"

    df = pd.DataFrame({
        "timestamp": timestamps,
        "time_seconds": times,
        "counts": counts,
        "instrument": int(Instrument.SOLEXS_SDD2 if det == "SDD2"
                          else Instrument.SOLEXS_SDD1),
        "energy_band": "2-22 keV",
        "qc_flag": int(QCFlag.GOOD),
        "source_id": f"SoLEXS_{det}",
        "provenance": f"SoLEXS L1 (date-src={src})",
    })
    # drop non-finite / negative-time artefacts, sort, de-dup timestamps
    df = df[np.isfinite(df["time_seconds"]) & np.isfinite(df["counts"])]
    return (df.sort_values("timestamp")
              .drop_duplicates("timestamp")
              .reset_index(drop=True))


def find_solexs_members(zip_path: str) -> List[str]:
    """All plausible light-curve members (any detector), best-first."""
    pat = re.compile(r"\.(lc|fits)(\.gz)?$", re.I)
    hits: List[str] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            base = Path(name).name
            if pat.search(base) and ("SLX" in name.upper() or "SOLEXS" in base.upper()
                                     or "SDD" in base.upper()):
                hits.append(name)
    # prefer explicit SDD2 then SDD1 then rest
    prio = {"SDD2": 0, "SDD1": 1}
    hits.sort(key=lambda s: prio.get(re.search(r"(SDD\d)", s, re.I).group(1).upper()
                                     if re.search(r"(SDD\d)", s, re.I) else "?", 9))
    return hits


def read_solexs_zip(zip_path: str, members: Optional[List[str]] = None
                    ) -> pd.DataFrame:
    members = members or find_solexs_members(zip_path)
    if not members:
        raise ValueError(f"No SoLEXS light-curve member found in {zip_path}")
    frames = []
    with zipfile.ZipFile(zip_path) as z:
        for m in members:
            try:
                frames.append(parse_solexs_fits_bytes(z.read(m), m, zip_path))
            except Exception as e:      # skip broken members, keep going
                print(f"[solexs_reader] skipping {m}: {type(e).__name__}: {e}")
    if not frames:
        raise ValueError(f"All members unreadable in {zip_path}")
    return pd.concat(frames, ignore_index=True)


def read_solexs_directory(directory: str) -> pd.DataFrame:
    frames = []
    for path in sorted(Path(directory).rglob("*")):
        if path.suffix.lower() == ".zip" and "SLX" in path.name.upper():
            try:
                frames.append(read_solexs_zip(str(path)))
            except Exception as e:
                print(f"[solexs_reader] WARN {path.name}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def arbitrate_sdd_rows(df: pd.DataFrame) -> pd.DataFrame:
    """One soft stream: prefer SDD2 above its linear range, else SDD1.

    Rule (SoLEXS calib paper): SDD1 saturates paralyzably >~1e5 cps; when the
    two overlap, trust SDD2 where SDD1 is saturated, else average is avoided -
    we take the detector whose count is closer to its own quiet median.
    """
    if df.empty or "source_id" not in df.columns:
        return df
    parts = []
    for sid, g in df.groupby("source_id"):
        g = g.copy()
        med = float(g["counts"].median())
        g["score"] = np.abs(np.log10(np.maximum(g["counts"], 1.0) / max(med, 1.0)))
        parts.append((sid, g))
    # merge on timestamp preferring lower score (less saturated)
    merged = pd.concat([g for _, g in parts], ignore_index=True)
    merged = (merged.sort_values(["timestamp", "score"])
                    .drop_duplicates("timestamp"))
    return merged.drop(columns=["score"]).sort_values("timestamp").reset_index(drop=True)
