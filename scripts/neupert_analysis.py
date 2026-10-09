"""Ingest GENUINE Aditya-L1 L1 data and measure the Neupert effect.

Handles the real PRADAN L1 product layout, which differs from the synthetic
fixtures previously in data/raw/:

  AL1_SLX_L1_YYYYMMDD_vM.n.zip
      SDD1/AL1_SOLEXS_YYYYMMDD_SDD1_L1.lc.gz     (soft, 2-22 keV)
      SDD1/AL1_SOLEXS_YYYYMMDD_SDD1_L1.gti.gz    (good time intervals)
      SDD2/...                                    (second aperture)

  AL1_HLD_L1_YYYYMMDD_vM.n.zip
      .../HEL1OS_L1_YYYYMMDD_lc.fits.gz           (hard, 10-150 keV, one
                                                   table extension per band)

Science performed: the Neupert effect predicts that soft X-ray flux follows the
TIME INTEGRAL of hard X-ray flux, not the hard flux itself. For each impulsive
HXR event this script fits both hypotheses and reports which wins, the lead
time, the goodness of fit, and whether the flare is Neupert-consistent.

Only intervals covered by BOTH instruments' GTIs are used, so spacecraft
night-side passes and downlink gaps cannot masquerade as flare decay.

Usage:
    python scripts/neupert_analysis.py --raw data/raw
    python scripts/neupert_analysis.py --raw data/raw --event 20241003:12:18
"""
from __future__ import annotations

import argparse
import glob
import gzip
import io
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
try:
    from astropy.io import fits
except Exception:
    fits = None

# --------------------------------------------------------------------------- #
# Band selection
# --------------------------------------------------------------------------- #
# Real HEL1OS L1 EXTNAMEs look like:
#   CDTE1_LC_BAND_5.00KEV_TO_20.00KEV
#   CZT1_LC_BAND_18.00KEV_TO_160.00KEV
# so the energy bounds must be PARSED, not pattern-matched. The previous
# substring hints ("5_20", "20_30", ...) never matched this format, and the
# "CDT" hint matched every CDTE extension, so each band silently overwrote the
# previous one and the last band written won. That made the selected "HXR"
# channel an accident of file ordering.
_BAND_RE = re.compile(r"BAND_(\d+(?:\.\d+)?)KEV_TO_(\d+(?:\.\d+)?)KEV")

# SoLEXS measures roughly 2-22 keV. A channel whose response starts BELOW that
# overlaps the soft band almost entirely, so calling it "hard X-ray" in a
# Neupert test is circular. Only channels whose lower edge sits above the
# SoLEXS ceiling are eligible as genuine HXR.
SOLEXS_HIGH_KEV = 22.0

# Quality floors. A channel with no spread is dead or off-source for the whole
# interval and cannot support a correlation.
MIN_CHANNEL_STD = 1e-6
MIN_FINITE_FRAC = 0.5
# If more than this fraction of GTI-valid samples are exactly zero, the detector
# is off-source for most of the interval and a plain median collapses to 0.
ZERO_INFLATION_ALERT = 0.5


# --------------------------------------------------------------------------- #
# FITS plumbing
# --------------------------------------------------------------------------- #
def _open(z: zipfile.ZipFile, member: str):
    raw = z.read(member)
    if member.endswith(".gz"):
        raw = gzip.decompress(raw)
    return fits.open(io.BytesIO(raw))


def _rate_series(hdu):
    """Pull (time_seconds, rate) out of a light-curve HDU, whatever it is named."""
    cols = [c.upper() for c in hdu.columns.names] if hasattr(hdu, "columns") else []
    data = hdu.data
    # Real HEL1OS uses MJD/ISOT for time, CTR for counts
    tcol = next((c for c in ("MJD", "TIME", "T", "SEC") if c in cols), None)
    rcol = next((c for c in ("CTR", "RATE", "COUNTS", "COUNT_RATE", "RATE_COUNTS",
                             "COUNTS_CORR", "CORR_RATE", "FLUX")
                 if c in cols), None)
    if rcol is None:
        return None
    if tcol == "MJD":
        # MJD 40587.0 IS the Unix epoch (1970-01-01), so this yields Unix
        # seconds directly - identical to the ISOT branch below.
        t = (np.asarray(data[tcol], float) - 40587.0) * 86400.0
    elif tcol == "ISOT":
        # ISOT format: parse as datetime
        isot = np.asarray(data[tcol])
        t = np.array([pd.Timestamp(s).timestamp() for s in isot], dtype=float)
    else:
        t = np.asarray(data[tcol], float) if tcol else np.arange(len(data[rcol]), dtype=float)
    return t, np.asarray(data[rcol], float), rcol


def _gti_intervals(z: zipfile.ZipFile, members):
    """Return good-time intervals as [(start_s, end_s), ...] merged and sorted."""
    spans = []
    for m in members:
        # Real HEL1OS GTI files: aux/gticdte*.fits, aux/gticzt*.fits
        if not (m.lower().endswith(".gti.gz") or
                ("aux/gtic" in m.lower() and m.lower().endswith(".fits"))):
            continue
        with _open(z, m) as h:
            for hdu in h[1:]:
                cols = [c.upper() for c in hdu.columns.names] if hasattr(hdu, "columns") else []
                s = next((c for c in ("TSTART", "START", "GSTART") if c in cols), None)
                e = next((c for c in ("TSTOP", "STOP", "GSTOP", "END") if c in cols), None)
                if s and e:
                    spans += list(zip(np.asarray(hdu.data[s], float),
                                      np.asarray(hdu.data[e], float)))
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


# --------------------------------------------------------------------------- #
# Container records
# --------------------------------------------------------------------------- #
@dataclass
class DayData:
    date: str
    date_obs: str | None
    soft: dict = field(default_factory=dict)      # {"SDD1": (t, rate), ...}
    hard: dict = field(default_factory=dict)      # {"CDTE": (t, rate), ...}
    soft_gti: list = field(default_factory=list)
    hard_gti: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def has_both(self) -> bool:
        return bool(self.soft) and bool(self.hard)


def read_slx_zip(path: str) -> DayData:
    date = re.search(r"_L1_(\d{8})_", os.path.basename(path)).group(1)
    rec = DayData(date=date, date_obs=None)
    z = zipfile.ZipFile(path)
    lcs = [m for m in z.namelist() if ".lc." in m or m.endswith("lc.fits.gz")]
    for m in lcs:
        det = "SDD2" if "SDD2" in m.upper() else ("SDD1" if "SDD1" in m.upper() else "SDD?")
        try:
            with _open(z, m) as h:
                rec.date_obs = rec.date_obs or h[0].header.get("DATE-OBS")
                for hdu in h[1:]:
                    got = _rate_series(hdu)
                    if got:
                        rec.soft[det] = (got[0], got[1], got[2])
        except Exception as e:  # noqa: BLE001
            rec.problems.append(f"SoLEXS {det} {type(e).__name__}: {e}")
    rec.soft_gti = _gti_intervals(z, z.namelist())
    return rec


def read_hld_zip(path: str) -> DayData:
    base = os.path.basename(path)
    # Support both AL1_HLD_L1_YYYYMMDD_ and HLS_YYYYMMDD_ naming
    m = re.search(r"_L1_(\d{8})_", base) or re.search(r"HLS_(\d{8})_", base)
    if not m:
        raise ValueError(f"Cannot extract date from {base}")
    date = m.group(1)
    rec = DayData(date=date, date_obs=None)
    z = zipfile.ZipFile(path)
    # Real PRADAN HEL1OS: light curves in cdte/lightcurve_cdte*.fits and czt/lightcurve_czt*.fits
    lcs = [m for m in z.namelist()
           if ("lightcurve_cdte" in m.lower() or "lightcurve_czt" in m.lower())
           and m.lower().endswith(".fits")]
    for m in lcs:
        try:
            with _open(z, m) as h:
                rec.date_obs = rec.date_obs or h[0].header.get("DATE-OBS")
                for hdu in h[1:]:
                    got = _rate_series(hdu)
                    if not got:
                        continue
                    t, rate, col = got
                    ext = hdu.name or ""
                    bm = _BAND_RE.search(ext)
                    if bm:
                        lo, hi = float(bm.group(1)), float(bm.group(2))
                    else:
                        # No parseable bounds: keep it, but mark unknown so it is
                        # only used if nothing better exists.
                        lo, hi = float("nan"), float("nan")
                    # Key on the full EXTNAME so distinct bands never collide.
                    rec.hard[ext.upper()] = (t, rate, col, lo, hi)
        except Exception as e:  # noqa: BLE001
            rec.problems.append(f"HEL1OS {type(e).__name__}: {e}")
    rec.hard_gti = _gti_intervals(z, z.namelist())
    return rec


# --------------------------------------------------------------------------- #
# Quality control
# --------------------------------------------------------------------------- #
def channel_quality(rate, mask) -> dict:
    """Basic health metrics for one light-curve channel."""
    v = np.asarray(rate, dtype=float)
    ok = np.isfinite(v)
    if mask is not None and len(mask) == len(v):
        ok &= mask
    vf = v[ok]
    n = int(vf.size)
    nzero = int((vf == 0).sum()) if n else 0
    return {
        "n_valid": n,
        "std": float(np.std(vf)) if n else 0.0,
        "max": float(np.max(vf)) if n else 0.0,
        "zero_fraction": (nzero / n) if n else 1.0,
        "finite_frac": (n / len(v)) if len(v) else 0.0,
    }


def robust_baseline(x, mask, q: float = 0.5) -> float:
    """Background level for a zero-inflated count-rate series.

    The plain median is unusable here: HEL1OS reports exact zeros for a large
    fraction of every interval (detector off-source between pointings), so the
    median of the full sample collapses to exactly 0.0 and every downstream
    enhancement ratio degenerates. Use a quantile of the NONZERO samples, which
    is the in-source background the detector actually sees.

    `q` is that quantile: 0.5 for a whole-interval background, lower (e.g. 0.25)
    for a local fit window, where a median can sit above the window's own quiet
    level and clip the whole window to zero.

    Whenever zeros are present the quantile MUST be taken over the nonzero
    subset. Taking a low quantile of the full array returns exactly 0 as soon
    as the zero fraction exceeds q, which is precisely the situation this
    function exists to handle.
    """
    v = np.asarray(x, dtype=float)
    if mask is not None and len(mask) == len(v):
        v = v[mask]
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    nz = v[v > 0]
    if nz.size == 0:
        return 0.0
    if nz.size < v.size:
        return float(np.quantile(nz, q))
    return float(np.quantile(v, q))


def select_hxr_band(rec: DayData, mask_ignored=None, min_keV: float = SOLEXS_HIGH_KEV,
                    want: str | None = None):
    """Choose the HXR channel to test.

    If `want` is given (e.g. "CZT2_40.00KEV_TO_60.00KEV" or just "40-60") the
    match is pinned, so every date in a run uses the SAME band. Auto-selection
    otherwise picks a different band per date (highest std among eligible),
    which makes cross-event comparison invalid.

    Preference order when not pinned:
      1. genuine HXR: lower energy edge at or above `min_keV` (above SoLEXS);
      2. anything parseable;
      3. unparseable EXTNAMEs as a last resort.
    """
    pool, qc = [], {}
    for ext, (t, rate, col, lo, hi) in rec.hard.items():
        q = channel_quality(rate, None)
        qc[ext] = q
        healthy = (q["finite_frac"] >= MIN_FINITE_FRAC
                   and q["std"] > MIN_CHANNEL_STD
                   and q["max"] > 0)
        if not healthy:
            continue
        genuine = bool(np.isfinite(lo)) and lo >= min_keV
        pool.append((genuine, q["std"], ext, lo, hi))

    if want:
        key = want.upper().replace(" ", "").replace("KEV", "")
        # An energy-range request such as "40-60" must match EXTNAMEs spelled
        # "CZT2_LC_BAND_40.00KEV_TO_60.00KEV", which does not contain the literal
        # substring "40-60". Compare numerically instead.
        want_lo = want_hi = None
        m = re.match(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$", key)
        if m:
            want_lo, want_hi = float(m.group(1)), float(m.group(2))
        matches = []
        for p in pool:
            if key in p[2]:
                matches.append(p)
            elif want_lo is not None and np.isfinite(p[3]) and np.isfinite(p[4]):
                if abs(p[3] - want_lo) < 1e-6 and abs(p[4] - want_hi) < 1e-6:
                    matches.append(p)
        if not matches:
            return None, qc, f"pinned band {want!r} not present or not healthy"
        # An energy range like "40-60" (or a detector name) may match several
        # extensions. Prefer one that also clears the genuine-HXR floor rather
        # than blindly taking the first, which would silently pick a band that
        # overlaps the SoLEXS soft range.
        elig = [p for p in matches
                if np.isfinite(p[3]) and p[3] >= min_keV]
        if elig:
            chosen = max(elig, key=lambda p: p[1])
            return (chosen[2], qc,
                    f"pinned by --band ({chosen[2]}, {chosen[3]:g} keV edge, "
                    f"genuine HXR)")
        chosen = matches[0]
        return None, qc, (f"pinned band {chosen[2]} has lower edge "
                          f"{chosen[3]:g} keV < {min_keV:g} keV; it overlaps "
                          f"SoLEXS and is not a clean HXR proxy")

    if not pool:
        return None, qc, "no healthy HEL1OS channel (all dead or non-finite)"

    genuine = [p for p in pool if p[0]]
    if genuine:
        chosen = max(genuine, key=lambda p: p[1])
        why = (f"genuine HXR (lo={chosen[3]:g} keV > {min_keV:g} keV), "
               f"most sensitive of {len(genuine)} eligible bands")
    else:
        parsed = [p for p in pool if np.isfinite(p[3])]
        chosen = max(parsed, key=lambda p: p[1]) if parsed else max(pool, key=lambda p: p[1])
        why = (f"WARNING: no band sits above {min_keV:g} keV; fell back to "
               f"{chosen[2]} - this overlaps the SoLEXS soft band and is NOT "
               f"a clean HXR proxy")
    return chosen[2], qc, why


# --------------------------------------------------------------------------- #
# Alignment
# --------------------------------------------------------------------------- #
def in_gti(t, gti):
    if not gti:
        return np.ones(len(t), bool)
    ok = np.zeros(len(t), bool)
    for a, b in gti:
        ok |= (t >= a) & (t < b)
    return ok


def resample_to(t, rate, tgrid):
    """Nearest-sample resample onto tgrid (1 Hz).

    Non-finite source samples (NaN / fill values, which the real SoLEXS product
    does contain) are bridged by linear interpolation over the finite samples
    only. Leaving them in place would propagate NaN across the whole gap, and a
    single NaN makes np.std/np.corrcoef return NaN, which previously caused a
    perfectly good flare (2024-10-03 X9.0) to be silently discarded.
    """
    t = np.asarray(t, dtype=float)
    rate = np.asarray(rate, dtype=float)
    good = np.isfinite(t) & np.isfinite(rate)
    if not good.any():
        return np.full(len(tgrid), np.nan)
    if not good.all() and good.sum() >= 2:
        rate = np.interp(t, t[good], rate[good])
    elif not good.all():
        rate = np.where(good, rate, np.nanmedian(rate[good]))
    idx = np.searchsorted(t, tgrid)
    idx = np.clip(idx, 1, len(t) - 1)
    lo, hi = t[idx - 1], t[idx]
    w = np.where(hi > lo, (tgrid - lo) / np.maximum(hi - lo, 1e-9), 0.0)
    return rate[idx - 1] * (1 - w) + rate[idx] * w


def common_stream(rec: DayData, hxr_ext: str):
    """Return (tgrid, hxr, sxr, mask, skey) on a shared 1 Hz grid, GTI-intersected."""
    if hxr_ext not in rec.hard:
        return None
    skey = "SDD2" if "SDD2" in rec.soft else next(iter(rec.soft), None)
    if skey is None:
        return None
    th, rh = rec.hard[hxr_ext][0], rec.hard[hxr_ext][1]
    ts, rs = rec.soft[skey][0], rec.soft[skey][1]
    # Both light curves are in Unix seconds. MJD 40587.0 is the Unix epoch, so
    # the MJD branch of _rate_series already yields Unix seconds, as does the
    # GTI conversion below.
    lo = int(max(th.min(), ts.min()))
    hi = int(min(th.max(), ts.max()))
    if hi - lo < 600:
        return None
    tgrid = np.arange(lo, hi + 1, dtype=float)
    hxr = resample_to(th, rh, tgrid)
    sxr = resample_to(ts, rs, tgrid)
    # HEL1OS GTI is MJD -> Unix seconds.
    hard_gti_unix = [((a - 40587.0) * 86400.0, (b - 40587.0) * 86400.0)
                     for a, b in rec.hard_gti]
    soft_gti_unix = rec.soft_gti  # already Unix
    ok = in_gti(tgrid, hard_gti_unix) & in_gti(tgrid, soft_gti_unix)
    # Belt-and-braces: never let a non-finite sample into the statistics.
    ok &= np.isfinite(hxr) & np.isfinite(sxr)
    if ok.sum() < 600:
        return None
    return tgrid, hxr, sxr, ok, skey


# --------------------------------------------------------------------------- #
# Neupert test
# --------------------------------------------------------------------------- #
def find_hxr_events(t, hxr, mask, min_gap=1800, min_enh=3.0):
    """Locate impulsive HXR episodes on the GTI-valid samples.

    Baseline uses robust_baseline (nonzero-median) because these count rates are
    zero-inflated; the plain median returns 0.0 and made the old
    `max < 3*base` enhancement gate a no-op that could never reject anything.
    """
    base = robust_baseline(hxr, mask)
    if base <= 0:
        return [], base
    k = np.ones(15) / 15
    sm = np.convolve(hxr, k, mode="same")
    v = sm[mask]
    if v.size == 0:
        return [], base
    thr = base + 0.3 * (np.percentile(v, 99.5) - base)
    hi = (sm > thr) & mask
    d = np.diff(hi.astype(int))
    starts = list(np.where(d == 1)[0] + 1)
    ends = list(np.where(d == -1)[0] + 1)
    if starts and hi[0]:
        starts = [0] + starts
    if ends and hi[-1]:
        ends = ends + [len(hi) - 1]
    evs = []
    for a, b in zip(starts, ends):
        if b - a < 60:
            continue
        # Enhancement gate, now meaningful because base > 0 is enforced.
        if hxr[a:b + 1].max() < min_enh * base:
            continue
        if evs and a - evs[-1][1] < min_gap:
            evs[-1] = (evs[-1][0], b)
        else:
            evs.append((a, b))
    return evs, base


# Below this |r| neither model is considered to describe the event. Without it
# an event where BOTH correlations are ~0 (e.g. 20240510, where r_dir=0.17 and
# r_int=-0.87) was scored "DIRECT" purely because a larger number won, which
# reports a coupling that does not exist.
MIN_COUPLING_R = 0.3

# Sentinel for "this model could not be fitted", kept far outside the valid
# correlation range so it can never win a comparison. The previous code used
# -1.0, which is inside [-1, 1]; when BOTH models hit it, the tie-break
# `ri > rd` evaluated False and the event was reported as DIRECT, i.e. a failed
# measurement was published as a physical result.
FIT_FAILED = -9.0


def neupert_fit(t, hxr, sxr, mask, a, b, pad=1800, max_lag=900, step=10):
    """Compare SXR ~ HXR vs SXR ~ integral(HXR) over a lag search.

    Returns (best, h, s, m, diag). `best` maps to (r, r2, lag) and holds
    FIT_FAILED for any model that could not be evaluated. `diag` carries the
    quality counters the caller needs to decide whether to trust the result.
    """
    lo, hi = max(0, a - pad), min(len(t), b + pad)
    diag = {"n_window": 0, "n_hxr_nonzero": 0, "zf_hxr": None, "zf_sxr": None,
            "ok": False, "reason": ""}
    if hi - lo < 300:
        diag["reason"] = "window too short"
        return None, None, None, None, diag
    tt = t[lo:hi]
    h = hxr[lo:hi].astype(float).copy()
    s = sxr[lo:hi].astype(float).copy()
    m = mask[lo:hi].copy()
    if not m.any():
        diag["reason"] = "no GTI-valid samples in window"
        return None, None, None, None, diag

    # Zero-inflation audit. Both instruments are off-source in the same
    # intervals (eclipse, downlink, pointing), so correlating two zero-inflated
    # series can return a high r driven purely by the SHARED pattern of zeros
    # rather than by any flare. If the window is mostly zeros the fit is not
    # trustworthy and is refused outright.
    hv, sv = h[m], s[m]
    zf_h = float((hv == 0).mean())
    zf_s = float((sv == 0).mean())
    diag["n_window"] = int(m.sum())
    diag["n_hxr_nonzero"] = int((hv != 0).sum())
    diag["zf_hxr"] = zf_h
    diag["zf_sxr"] = zf_s
    if zf_h > 0.9:
        diag["reason"] = f"HXR window {zf_h:.0%} zeros (detector off-source)"
        return None, None, None, None, diag

    # Baseline-subtract with a LOCAL zero-robust quantile. A whole-interval
    # median can sit above the quiet level inside a short event window, which
    # clips the entire window to zero and makes both models unfittable.
    hb = robust_baseline(h, m, q=0.25)
    sb = robust_baseline(s, m, q=0.25)
    if hb <= 0:
        diag["reason"] = "HXR baseline is zero even after nonzero-quantile"
        return None, None, None, None, diag
    h = np.clip(h - hb, 0, None)
    s = np.clip(s - sb, 0, None)
    if h[m].std() <= 0:
        diag["reason"] = (f"HXR window degenerate after local baseline "
                          f"(hb={hb:.4g}, zero_fraction={zf_h:.0%})")
        return None, None, None, None, diag
    dt = float(np.median(np.diff(tt))) if len(tt) > 1 else 1.0
    h_int = np.cumsum(h) * dt

    def score(x, y, mm):
        if not (mm.any() and x[mm].std() > 0):
            return FIT_FAILED, float("nan")
        r = float(np.corrcoef(x[mm], y[mm])[0, 1])
        if not np.isfinite(r):
            return FIT_FAILED, float("nan")
        A = np.vstack([x[mm], np.ones(int(mm.sum()))]).T
        coef, *_ = np.linalg.lstsq(A, y[mm], rcond=None)
        pred = A @ coef
        ss = float(((y[mm] - pred) ** 2).sum())
        tot = float(((y[mm] - y[mm].mean()) ** 2).sum())
        return r, (1 - ss / tot if tot > 0 else float("nan"))

    best = {"direct": (FIT_FAILED, float("nan"), 0),
            "integral": (FIT_FAILED, float("nan"), 0)}
    for lag in range(0, max_lag + 1, step):
        if lag + 5 >= len(s):
            break
        # SXR delayed by `lag` seconds
        ss_ = np.empty_like(s)
        ss_[:lag] = s[:lag]
        ss_[lag:] = s[:len(s) - lag]
        # ss_[:lag] is padding, not data. score() used to close over the
        # unmasked `m` and therefore correlated against those zeros, which
        # inflated r. Pass the lag-aware mask explicitly.
        mm = m.copy()
        mm[:lag] = False
        r1, q1 = score(h, ss_, mm)
        r2, q2 = score(h_int, ss_, mm)
        if r1 > best["direct"][0]:
            best["direct"] = (r1, q1, lag)
        if r2 > best["integral"][0]:
            best["integral"] = (r2, q2, lag)

    if best["direct"][0] <= FIT_FAILED / 2 and best["integral"][0] <= FIT_FAILED / 2:
        diag["reason"] = "both models unfittable (zero variance after baseline)"
        return None, None, None, None, diag

    diag["ok"] = True
    return best, h, s, m, diag


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _utc(t_seconds: float) -> str:
    """Format Unix seconds as UTC. The old code did int(t)//3600, which printed
    the hour-of-day counter (e.g. 476478) instead of a clock time."""
    return datetime.fromtimestamp(float(t_seconds), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%SZ")


def _r(v: float) -> str:
    return "  n/a" if (v is None or not np.isfinite(v) or v <= FIT_FAILED / 2) \
        else f"{v:.3f}"


def decide_verdict(rd: float, ri: float) -> str:
    """Single source of truth for the DIRECT/INTEGRAL call.

    A model only counts as the winner if it shows a POSITIVE correlation at or
    above MIN_COUPLING_R. Three guards, in order:

      - a model that could not be fitted is never a winner;
      - a large NEGATIVE correlation is not a win either. SXR flux and the HXR
        integral are physically expected to be positively related, so a strong
        negative r indicates an artifact or a polarity error, not a coupling.
        (2024-05-10 produced r_integral = -0.886, which the previous tie-break
        would have treated as a losing score while DIRECT "won" on r=0.199.)
      - only then is the larger valid correlation named the winner.
    """
    fit_d = np.isfinite(rd) and rd > FIT_FAILED / 2
    fit_i = np.isfinite(ri) and ri > FIT_FAILED / 2
    if not (fit_d or fit_i):
        return "INDETERMINATE"
    good_d = fit_d and rd >= MIN_COUPLING_R
    good_i = fit_i and ri >= MIN_COUPLING_R
    if good_d and good_i:
        return "INTEGRAL" if ri > rd else "DIRECT"
    if good_i:
        return "INTEGRAL"
    if good_d:
        return "DIRECT"
    return "NO_COUPLING"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--event", action="append", default=[],
                    help="YYYYMMDD:HH:MM known flare time (UTC), repeatable")
    ap.add_argument("--min-hxr-enh", type=float, default=3.0,
                    help="minimum HXR enhancement over baseline to count an event")
    ap.add_argument("--min-hxr-kev", type=float, default=SOLEXS_HIGH_KEV,
                    help="lower energy edge required for a genuine HXR band "
                         "(default: SoLEXS high edge, 22 keV)")
    ap.add_argument("--band", default=None,
                    help="pin the HXR band, e.g. '40-60' or "
                         "'CZT2'. Use the SAME band for every date in a study.")
    ap.add_argument("--sweep-bands", action="store_true",
                    help="repeat the analysis across every healthy genuine-HXR "
                         "band and print a sensitivity table")
    ap.add_argument("--csv", default=None, help="write per-event results to CSV")
    a = ap.parse_args()

    slx = sorted(glob.glob(os.path.join(a.raw, "AL1_SLX_L1_*.zip")))
    hld = sorted(glob.glob(os.path.join(a.raw, "AL1_HLD_L1_*.zip")))
    # Also support real PRADAN HEL1OS naming: HLS_YYYYMMDD_HHMMSS_XXXXsec_lev1_V111.zip
    hld += sorted(glob.glob(os.path.join(a.raw, "HLS_*.zip")))
    print(f"SoLEXS archives: {len(slx)}   HEL1OS archives: {len(hld)}")

    # authenticity tripwire: fixtures correlate at 1.0 across different dates
    if slx and hld:
        probe = read_hld_zip(hld[0])
        pk = next((v for v in probe.hard.values()), None)
        if pk is not None and len(hld) > 1:
            p2 = read_hld_zip(hld[1])
            q2 = next((v for v in p2.hard.values()), None)
            if q2 is not None and len(pk[1]) == len(q2[1]):
                c = float(np.corrcoef(pk[1], q2[1])[0, 1])
                print(f"cross-day HXR correlation ({probe.date} vs {p2.date}): "
                      f"{c:.6f}")
                if abs(c) > 0.9999:
                    print("!! WARNING: distinct dates near-identical -> SYNTHETIC "
                          "FIXTURES. Abort; do not publish from these files.")
                    return 2

    days = {}
    for p in slx:
        r = read_slx_zip(p)
        days.setdefault(r.date, DayData(r.date, r.date_obs))
        days[r.date].soft = r.soft
        days[r.date].soft_gti = r.soft_gti
        days[r.date].problems += r.problems
    for p in hld:
        r = read_hld_zip(p)
        days.setdefault(r.date, DayData(r.date, r.date_obs))
        days[r.date].hard = r.hard
        days[r.date].hard_gti = r.hard_gti
        days[r.date].problems += r.problems

    wanted = {s.replace("-", "")[:8] for s in a.event} if a.event else None
    results = []
    excluded = []
    for date in sorted(days):
        rec = days[date]
        if wanted and date not in wanted:
            continue
        if not rec.has_both:
            print(f"{date}: need both instruments "
                  f"(soft={list(rec.soft)} hard={list(rec.hard)})")
            excluded.append((date, "missing instrument"))
            continue

        hxr_ext, qc, why = select_hxr_band(rec, min_keV=a.min_hxr_kev,
                                           want=a.band)
        if hxr_ext is None:
            print(f"{date}: {why}")
            excluded.append((date, why))
            continue

        got = common_stream(rec, hxr_ext)
        if got is None:
            print(f"{date}: no usable GTI-overlapping interval")
            excluded.append((date, "no GTI overlap"))
            continue
        t, hxr, sxr, mask, skey = got

        q = channel_quality(hxr, mask)
        lo_ke = rec.hard[hxr_ext][3]
        hi_ke = rec.hard[hxr_ext][4]
        bandtxt = (f"{lo_ke:g}-{hi_ke:g} keV" if np.isfinite(lo_ke)
                   else "energy unknown")
        print(f"\n{date}  DATE-OBS={rec.date_obs}")
        print(f"    HXR band: {hxr_ext}  ({bandtxt})")
        print(f"    selection: {why}")
        print(f"    SXR det: {skey}   GTI overlap: {mask.sum()/len(t):.0%}")
        print(f"    HXR QC: std={q['std']:.4g} max={q['max']:.4g} "
              f"zeros={q['zero_fraction']:.0%}")

        evs, base = find_hxr_events(t, hxr, mask, min_enh=a.min_hxr_enh)
        print(f"    baseline={base:.4g}  candidate events={len(evs)}")
        if rec.problems:
            for p in rec.problems:
                print(f"    ! {p}")

        for (i, j) in evs:
            fit = neupert_fit(t, hxr, sxr, mask, i, j)
            if not fit or fit[0] is None:
                reason = fit[4]["reason"] if fit else "fit returned nothing"
                print(f"    event {_utc(t[i])}  EXCLUDED: {reason}")
                excluded.append((f"{date}@{_utc(t[i])}", reason))
                continue
            best, _, _, _, diag = fit
            rd, qd, ld = best["direct"]
            ri, qi, li = best["integral"]
            enh = hxr[i:j + 1].max() / base if base > 0 else float("nan")

            verdict = decide_verdict(rd, ri)
            if verdict in ("INDETERMINATE", "NO_COUPLING"):
                excluded.append((f"{date}@{_utc(t[i])}", verdict.lower()))

            tstr = _utc(t[i])
            print(f"    event t={tstr}  HXR x{enh:7.1f}  "
                  f"zf_hxr={diag['zf_hxr']:.0%}  "
                  f"SXR~HXR r={_r(rd)} lag={ld:4d}s | "
                  f"SXR~intHXR r={_r(ri)} lag={li:4d}s -> {verdict}")
            results.append({
                "date": date, "t_utc": tstr, "hxr_band": hxr_ext,
                "band_kev": bandtxt, "sxr_det": skey,
                "baseline": base, "enh": enh,
                "zf_hxr": diag["zf_hxr"], "zf_sxr": diag["zf_sxr"],
                "r_direct": rd, "r_integral": ri,
                "lag_direct": ld, "lag_integral": li,
                "verdict": verdict,
            })

    if results:
        df = pd.DataFrame(results)
        n = len(df)
        nint = int((df.verdict == "INTEGRAL").sum())
        ndir = int((df.verdict == "DIRECT").sum())
        nind = int(df.verdict.isin(["INDETERMINATE", "NO_COUPLING"]).sum())
        print("\n" + "=" * 78)
        print("NEUPERT SUMMARY  (QC-passing events only)")
        print("=" * 78)
        print(f"  events analysed              : {n}")
        print(f"  SXR tracks integral(HXR)     : {nint}/{n} ({nint/n:.0%})")
        print(f"  SXR tracks HXR directly       : {ndir}/{n} ({ndir/n:.0%})")
        if nind:
            print(f"  no usable coupling           : {nind}/{n}")
        sub = df[df.verdict.isin(["INTEGRAL", "DIRECT"])]
        if len(sub):
            print(f"  median lead (integral model) : "
                  f"{sub.lag_integral.median():.0f} s "
                  f"({sub.lag_integral.median()/60:.1f} min)")
            print(f"  median r, integral model     : "
                  f"{sub.r_integral.median():.3f}")
            print(f"  median r, direct model       : "
                  f"{sub.r_direct.median():.3f}")
            consistent = int((sub.r_integral >= 0.7).sum())
            print(f"  Neupert-consistent (r>=0.7)  : {consistent}/{len(sub)} "
                  f"({consistent/len(sub):.0%})")
        if excluded:
            print(f"\n  EXCLUDED by QC: {len(excluded)}")
            for k, why in excluded:
                print(f"    - {k}: {why}")
        print("\n  The Neupert effect predicts the INTEGRAL model should win.")
        if n and nint / n < 0.5:
            print("  -> NOT supported by these data.")
        else:
            print("  -> supported.")
        if a.csv:
            df.to_csv(a.csv, index=False)
            print(f"\n  wrote {a.csv}")
    else:
        print("\nno events passed QC.")
        if excluded:
            print(f"  {len(excluded)} candidate(s) excluded:")
            for k, why in excluded:
                print(f"    - {k}: {why}")

    if a.sweep_bands:
        sweep(days, wanted, a)


def sweep(days, wanted, a):
    """Repeat the per-event test across every healthy genuine-HXR band.

    Needed for the paper: a single-band result cannot be claimed as robust
    until we show the DIRECT/INTEGRAL outcome does not flip with band choice.
    """
    print("\n" + "=" * 78)
    print("BAND SENSITIVITY SWEEP")
    print("=" * 78)
    print(f"{'date':<10} {'det':<6} {'band keV':<12} {'r_dir':>7} {'r_int':>7} "
          f"{'lag_int':>8}  verdict")
    for date in sorted(days):
        rec = days[date]
        if wanted and date not in wanted:
            continue
        if not rec.has_both:
            continue
        cands = []
        for ext, (_t, _rate, _c, lo, hi) in rec.hard.items():
            if np.isfinite(lo) and lo >= a.min_hxr_kev:
                det = "CDTE" if "CDTE" in ext.upper() else (
                    "CZT" if "CZT" in ext.upper() else "OTHER")
                cands.append((lo, hi, ext, det))
        seen = set()
        for lo, hi, ext, det in sorted(cands):
            if (lo, hi, det) in seen:
                continue
            seen.add((lo, hi, det))
            got = common_stream(rec, ext)
            if got is None:
                continue
            t, hxr, sxr, mask, _sk = got
            evs, base = find_hxr_events(t, hxr, mask, min_enh=a.min_hxr_enh)
            if not evs:
                print(f"{date:<10} {det:<6} {f'{lo:g}-{hi:g}':<12} {'-':>7} "
                      f"{'-':>7} {'-':>8}  no event")
                continue
            i, j = evs[0]
            fit = neupert_fit(t, hxr, sxr, mask, i, j)
            if not fit or fit[0] is None:
                print(f"{date:<10} {det:<6} {f'{lo:g}-{hi:g}':<12} {'-':>7} "
                      f"{'-':>7} {'-':>8}  excluded")
                continue
            best = fit[0]
            rd, _qd, _ld = best["direct"]
            ri, _qi, li = best["integral"]
            print(f"{date:<10} {det:<6} {f'{lo:g}-{hi:g}':<12} {_r(rd):>7} "
                  f"{_r(ri):>7} {li:>7}s  {decide_verdict(rd, ri)}")


if __name__ == "__main__":
    sys.exit(main())
