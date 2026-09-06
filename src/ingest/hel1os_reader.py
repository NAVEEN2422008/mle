"""HEL1OS Level-1 reader - hardened for multi-extension band light curves.

Documented L1 layout (HEL1OS mission paper): light curves per detector at 1-s
cadence in DIFFERENT ENERGY SUB-BANDS saved as SEPARATE TABLE EXTENSIONS,
plus event lists and auxiliary files in the same ZIP.

Defensive design:
- Scans every FITS member; every binary-table HDU becomes a candidate.
- Detector (CdTe/CZT) from member filename or HDU EXTNAME; energy band from
  EXTNAME/keywords/filename patterns (band1..4 / numeric keV ranges).
- Multi-count-column tables are MELTED long: one row per (time, band).
- Same tolerant column discovery & date extraction as the SoLEXS reader.
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from astropy.io import fits as _fits
from .fits_pure import read_all_hdus

from ..types import Instrument, QCFlag

_TIME_COLS = ["TIME", "TIMES", "T", "MJDSEC"]
_COUNT_HINT = ("COUNT", "RATE", "CNT", "FLUX")
_BAND_PAT = [
    (re.compile(r"band\s*1|5\s*-\s*20", re.I), "5-20 keV"),
    (re.compile(r"band\s*2|20\s*-\s*30", re.I), "20-30 keV"),
    (re.compile(r"band\s*3|30\s*-\s*40", re.I), "30-40 keV"),
    (re.compile(r"band\s*4|40\s*-\s*60", re.I), "40-60 keV"),
    (re.compile(r"total|full|all", re.I), "total"),
]


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _pick_time(columns: List[str]) -> Optional[str]:
    nm = {_norm(c): c for c in columns}
    for w in _TIME_COLS:
        if _norm(w) in nm:
            return nm[_norm(w)]
    for c in columns:
        if _norm(c).startswith("TIME"):
            return c
    return None


def _count_columns(columns: List[str]) -> List[str]:
    return [c for c in columns
            if any(h in _norm(c) for h in _COUNT_HINT)]


def _detect_instrument(*blobs: str) -> Instrument:
    txt = " ".join(blobs).upper()
    if "CZT" in txt:
        return Instrument.HEL1OS_CZT
    if "CDTE" in txt or "CD TE" in txt:
        return Instrument.HEL1OS_CDTE
    return Instrument.HEL1OS_CDTE      # paper: CdTe is primary/low band


def _detect_band(extname: str, header,
                 count_col: str) -> str:
    blob = f"{extname} {count_col}"
    for pat, label in _BAND_PAT:
        if pat.search(blob):
            return label
    for key in ("BAND", "EBAND", "ENERGY_BAND"):
        v = str(header.get(key, ""))
        if v:
            return v
    return extname or "unknown"


def _extract_date(header, member: str, zip_name: str) -> datetime:
    for key in ("DATE-OBS", "DATEOBS", "DATE_OBS", "OBS_DATE", "TSTART_ISO"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(header.get(key, "")))
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
    for blob in (member, zip_name):
        m = re.search(r"(20\d{6})", blob)
        if m:
            return datetime.strptime(m.group(1), "%Y%m%d")
    return datetime(1970, 1, 1)


def parse_hel1os_fits_bytes(raw: bytes, member: str = "",
                            zip_name: str = "") -> pd.DataFrame:
    """Parse one HEL1OS FITS -> long-format rows across all table HDUs."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    instr_default = _detect_instrument(member, zip_name)
    frames: List[pd.DataFrame] = []

    hdus = read_all_hdus(raw)
    for hdr, data in hdus:
        if data is None or data.empty:
            continue
        cols = list(data.columns)
        tcol = _pick_time(cols)
        if tcol is None:
            continue
        ccols = _count_columns(cols)
        if not ccols:
            continue

        times = np.asarray(data[tcol], dtype=float)
        extname = str(hdr.get("EXTNAME", "")).strip()
        base_date = _extract_date(hdr, member, zip_name)
        stamps = base_date + pd.to_timedelta(times, unit="s")

        for cc in ccols:
            vals = np.asarray(data[cc], dtype=float)
            band = _detect_band(extname, hdr, cc)
            instr = instr_default
            if "CZT" in extname.upper():
                instr = Instrument.HEL1OS_CZT
            elif "CDTE" in extname.upper():
                instr = Instrument.HEL1OS_CDTE
            frames.append(pd.DataFrame({
                "timestamp": stamps,
                "time_seconds": times,
                "counts": vals,
                "instrument": int(instr),
                "energy_band": band,
                "qc_flag": int(QCFlag.GOOD),
                "source_id": f"HEL1OS_{extname}_{cc}",
                "provenance": f"HEL1OS L1 ({Path(member).name})",
            }))

    if not frames:
        raise ValueError(f"No usable tables in HEL1OS member {member}")

    df = pd.concat(frames, ignore_index=True)
    keep = np.isfinite(df["time_seconds"]) & np.isfinite(df["counts"])
    return (df[keep]
              .sort_values(["energy_band", "timestamp"])
              .drop_duplicates(["energy_band", "timestamp"])
              .reset_index(drop=True))


def find_hel1os_members(zip_path: str) -> List[str]:
    pat = re.compile(r"\.(fits?)(\.gz)?$", re.I)
    skip = re.compile(r"(event|gti|housekeep|hk_|attitude)", re.I)
    hits: List[str] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            base = Path(name).name
            if pat.search(base) and not skip.search(base):
                hits.append(name)
    # prefer explicit lc names first
    hits.sort(key=lambda s: (0 if re.search(r"lc|lightcurve", s, re.I) else 1, s))
    return hits


def read_hel1os_zip(zip_path: str, members: Optional[List[str]] = None
                    ) -> pd.DataFrame:
    members = members or find_hel1os_members(zip_path)
    if not members:
        raise ValueError(f"No HEL1OS FITS member found in {zip_path}")
    frames = []
    with zipfile.ZipFile(zip_path) as z:
        for m in members:
            try:
                frames.append(parse_hel1os_fits_bytes(z.read(m), m, zip_path))
            except Exception as e:
                print(f"[hel1os_reader] skipping {m}: {type(e).__name__}: {e}")
    if not frames:
        raise ValueError(f"All members unreadable in {zip_path}")
    return pd.concat(frames, ignore_index=True)


def read_hel1os_directory(directory: str) -> pd.DataFrame:
    frames = []
    for path in sorted(Path(directory).rglob("*")):
        if path.suffix.lower() == ".zip" and "HLD" in path.name.upper():
            try:
                frames.append(read_hel1os_zip(str(path)))
            except Exception as e:
                print(f"[hel1os_reader] WARN {path.name}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collapse_bands(df: pd.DataFrame, bands: Optional[List[str]] = None
                   ) -> pd.DataFrame:
    """Sum selected energy bands into a single hard-band stream per timestamp."""
    use = df if bands is None else df[df["energy_band"].isin(bands)]
    g = (use.groupby("timestamp", as_index=False)["counts"]
            .sum()
            .sort_values("timestamp")
            .reset_index(drop=True))
    g["instrument"] = int(Instrument.HEL1OS_CDTE)
    g["energy_band"] = "collapsed"
    g["qc_flag"] = int(QCFlag.GOOD)
    g["source_id"] = "HEL1OS_collapsed"
    return g
