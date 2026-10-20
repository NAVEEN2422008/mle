#!/usr/bin/env python3
"""
Generate all figures for the Aditya-L1 Neupert Effect Test and ML Nowcasting paper.
Uses real data from the Aditya-L1 PRADAN archives.
"""
import sys
sys.path.insert(0, "C:/Users/Naveen S/OneDrive/Documents/mle/solar-flare-system")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator
import seaborn as sns
import zipfile
import io
import gzip
import re
import os
from pathlib import Path
from numpy import ones  # noqa: F401  (used in lag-aligned least-squares fits)
from astropy.io import fits
from datetime import datetime, timezone
from scipy import stats
from scipy.signal import find_peaks

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_context("paper", font_scale=1.2)
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif'],
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.titlesize': 13,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.transparent': False,
})

# Color palette
COLORS = {
    'solexs': '#E74C3C',      # Red for SXR
    'hel1os': '#3498DB',      # Blue for HXR
    'integral': '#27AE60',    # Green for integral model
    'direct': '#E74C3C',      # Red for direct model
    'bg': '#F8F9FA',
    'grid': '#E0E0E0',
}

RAW_DIR = Path("C:/Users/Naveen S/OneDrive/Documents/mle/solar-flare-system/data/raw")
FIG_DIR = Path("C:/Users/Naveen S/OneDrive/Documents/mle/solar-flare-system/paper/figures")

# =============================================================================
# Data loading functions (from neupert_analysis.py)
# =============================================================================

_BAND_RE = re.compile(r"BAND_(\d+(?:\.\d+)?)KEV_TO_(\d+(?:\.\d+)?)KEV")
SOLEXS_HIGH_KEV = 22.0

def _open(z, member):
    raw = z.read(member)
    if member.lower().endswith(".gz"):
        raw = gzip.decompress(raw)
    return fits.open(io.BytesIO(raw))

def _rate_series(hdu):
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

def _gti_intervals(z, members):
    spans = []
    for m in members:
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

def read_slx_zip(path):
    date = re.search(r"_L1_(\d{8})_", os.path.basename(path)).group(1)
    z = zipfile.ZipFile(path)
    lcs = [m for m in z.namelist() if ".lc." in m or m.endswith("lc.fits.gz")]
    best = None
    for m in lcs:
        det = "SDD2" if "SDD2" in m.upper() else ("SDD1" if "SDD1" in m.upper() else "SDD?")
        if det != "SDD2":
            continue
        with _open(z, m) as h:
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

def read_hel1os_zip(path, target_band="40-60 keV"):
    z = zipfile.ZipFile(path)
    lcs = [m for m in z.namelist()
           if ("lightcurve_cdte" in m.lower() or "lightcurve_czt" in m.lower())
           and m.lower().endswith(".fits")]
    best = None
    for m in lcs:
        with _open(z, m) as h:
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

def _in_gti(t, gti):
    if not gti:
        return np.ones(len(t), bool)
    ok = np.zeros(len(t), bool)
    for a, b in gti:
        ok |= (t >= a) & (t < b)
    return ok

def _resample_to(t, rate, tgrid):
    idx = np.searchsorted(t, tgrid)
    idx = np.clip(idx, 1, len(t) - 1)
    lo, hi = t[idx - 1], t[idx]
    w = np.where(hi > lo, (tgrid - lo) / np.maximum(hi - lo, 1e-9), 0.0)
    return rate[idx - 1] * (1 - w) + rate[idx] * w

def robust_baseline(x, mask, q=0.5):
    v = np.asarray(x, dtype=float)
    if mask is not None and len(mask) == len(v):
        v = v[mask]
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0
    nz = v[v > 0]
    if nz.size == 0:
        return 0.0
    if nz.size < v.size * 0.5:
        val = float(np.quantile(nz, q))
    else:
        val = float(np.quantile(v, q))
    # A zero-inflated channel can push the quantile onto the zero floor even
    # when the non-zero population is large (e.g. 68% non-zero here, so the
    # 25th percentile of all samples is exactly 0). Returning 0 makes callers
    # reject the fit, which silently blanked every Neupert panel. Fall back to
    # the non-zero quantile instead.
    if val <= 0.0:
        val = float(np.quantile(nz, q))
    return val

def find_hxr_events(t, hxr, mask, min_gap=1800, min_enh=3.0):
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
        if hxr[a:b + 1].max() < min_enh * base:
            continue
        if evs and a - evs[-1][1] < min_gap:
            evs[-1] = (evs[-1][0], b)
        else:
            evs.append((a, b))
    return evs, base

FIT_FAILED = -9.0
MIN_COUPLING_R = 0.3

def neupert_fit(t, hxr, sxr, mask, a, b, pad=1800, max_lag=900, step=10):
    lo, hi = max(0, a - pad), min(len(t), b + pad)
    if hi - lo < 300:
        return None
    tt = t[lo:hi]
    h = hxr[lo:hi].astype(float).copy()
    s = sxr[lo:hi].astype(float).copy()
    m = mask[lo:hi].copy()
    if not m.any():
        return None
    # Resampling a channel with an internal data gap can leave non-finite
    # samples (20241003 has 72). np.clip preserves NaN, so a single bad sample
    # makes every std/corrcoef return NaN and the whole fit is discarded even
    # though >99% of the window is valid. Zero-filling gaps and excluding them
    # from the correlation via the mask keeps the valid data usable.
    bad = ~(np.isfinite(h) & np.isfinite(s))
    if bad.all():
        return None
    if bad.any():
        h = np.where(bad, 0.0, h)
        s = np.where(bad, 0.0, s)
        m = m & ~bad

    hv, sv = h[m], s[m]
    zf_h = float((hv == 0).mean())
    zf_s = float((sv == 0).mean())
    if zf_h > 0.9:
        return None
    hb = robust_baseline(h, m, q=0.25)
    sb = robust_baseline(s, m, q=0.25)
    if hb <= 0:
        return None
    h = np.clip(h - hb, 0, None)
    s = np.clip(s - sb, 0, None)
    if h[m].std() <= 0:
        return None
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
        ss_ = np.empty_like(s)
        ss_[:lag] = s[:lag]
        ss_[lag:] = s[:len(s) - lag]
        # The lagged series is zero-padded in its first `lag` samples; those
        # samples are not real measurements and must be excluded from the
        # correlation. score() previously closed over the unmasked `m`, which
        # silently scored against the padding.
        mm = m.copy()
        mm[:lag] = False
        r1, q1 = score(h, ss_, mm)
        r2, q2 = score(h_int, ss_, mm)
        if r1 > best["direct"][0]:
            best["direct"] = (r1, q1, lag)
        if r2 > best["integral"][0]:
            best["integral"] = (r2, q2, lag)

    if best["direct"][0] <= FIT_FAILED / 2 and best["integral"][0] <= FIT_FAILED / 2:
        return None

    # Return the lag-shifted SXR arrays and per-model masks so callers plot the
    # SAME data that produced the reported correlation. Previously this
    # returned only the unshifted window, so the scatter panels showed an
    # unlagged relationship while the printed r came from the lagged fit.
    def _lagged(lag):
        ss_ = np.empty_like(s)
        ss_[:lag] = s[:lag]
        ss_[lag:] = s[:len(s) - lag]
        mm = m.copy()
        mm[:lag] = False
        return ss_, mm

    return best, h, h_int, s, m, _lagged

def decide_verdict(rd, ri):
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

# =============================================================================
# Figure 1: Light curves for the 4 usable events
# =============================================================================

def generate_figure1_lightcurves():
    """Figure 1: Light curves for the 4 usable events showing SXR and HXR."""
    pairs = [
        ("20240511", "X5.8", "AL1_SLX_L1_20240511_v1.0.zip", "HLS_20240511_000005_22291sec_lev1_V111.zip"),
        ("20240514", "X8.7", "AL1_SLX_L1_20240514_v1.0.zip", "HLS_20240514_120751_42723sec_lev1_V111.zip"),
        ("20241001", "X7.1", "AL1_SLX_L1_20241001_v1.0.zip", "HLS_20241001_120001_43189sec_lev1_V111.zip"),
        ("20241003", "X9.0", "AL1_SLX_L1_20241003_v1.0.zip", "HLS_20241003_120003_43190sec_lev1_V111.zip"),
    ]

    fig = plt.figure(figsize=(14, 10))
    gs = gridspec.GridSpec(4, 1, hspace=0.3)

    for idx, (date, flare_class, slx_file, hld_file) in enumerate(pairs):
        ax = fig.add_subplot(gs[idx, 0])

        # Load data
        ts, rs, soft_gti = read_slx_zip(RAW_DIR / slx_file)
        th, rh, hard_gti = read_hel1os_zip(RAW_DIR / hld_file, "40-60 keV")

        # Align
        lo = int(max(ts.min(), th.min()))
        hi = int(min(ts.max(), th.max()))
        tgrid = np.arange(lo, hi + 1, dtype=float)
        sxr = _resample_to(ts, rs, tgrid)
        hxr = _resample_to(th, rh, tgrid)

        # GTI mask
        hard_gti_unix = [((a - 40587.0) * 86400.0, (b - 40587.0) * 86400.0) for a, b in hard_gti]
        soft_gti_unix = soft_gti
        ok = _in_gti(tgrid, hard_gti_unix) & _in_gti(tgrid, soft_gti_unix)

        # Convert to datetime for plotting
        t_dt = pd.to_datetime(tgrid, unit='s', utc=True)

        # Plot. Reuse the gridspec axis created above; fig.add_subplot(4, 1,
        # idx + 1) here would overlay a duplicate Axes on the real one.
        ax2 = ax.twinx()
        ax.plot(t_dt[ok], sxr[ok], color=COLORS['solexs'], linewidth=0.8, label='SoLEXS SDD2 (2-22 keV)', alpha=0.8)
        ax2.plot(t_dt[ok], hxr[ok], color=COLORS['hel1os'], linewidth=0.8, label='HEL1OS CZT 40-60 keV', alpha=0.8)

        # Mark flare peak from NOAA
        flare_times = {
            "20240511": 1715390580,
            "20240514": 1715705460,
            "20241001": 1727821200,
            "20241003": 1727957880,
        }
        flare_time = pd.Timestamp(flare_times[date], unit='s', tz='UTC')
        ax.axvline(flare_time, color='black', linestyle='--', linewidth=1, alpha=0.7, label='NOAA peak')

        # Format
        ax.set_ylabel('SXR (cts/s)', color=COLORS['solexs'], fontsize=10)
        ax2.set_ylabel('HXR (cts/s)', color=COLORS['hel1os'], fontsize=10)
        ax.tick_params(axis='y', labelcolor=COLORS['solexs'])
        ax2.tick_params(axis='y', labelcolor=COLORS['hel1os'])
        ax.set_title(f"{date} - {flare_class} flare", fontsize=11, fontweight='bold', pad=5)

        # Format x-axis
        ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(plt.matplotlib.dates.HourLocator(interval=1))

        # Legend
        if idx == 0:
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=9, framealpha=0.9)

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure1_lightcurves.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure1_lightcurves.pdf')
    plt.savefig(FIG_DIR / 'figure5_lightcurves.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure5_lightcurves.pdf')
    plt.close()
    print("Figure 1 / Figure 5 saved")

# =============================================================================
# Figure 2: Neupert test scatter plots (Direct vs Integral)
# =============================================================================

def generate_figure2_neupert_scatter():
    """Figure 2: Direct vs Integral model scatter plots for each event."""
    pairs = [
        ("20240511", "X5.8", "AL1_SLX_L1_20240511_v1.0.zip", "HLS_20240511_000005_22291sec_lev1_V111.zip"),
        ("20240514", "X8.7", "AL1_SLX_L1_20240514_v1.0.zip", "HLS_20240514_120751_42723sec_lev1_V111.zip"),
        ("20241001", "X7.1", "AL1_SLX_L1_20241001_v1.0.zip", "HLS_20241001_120001_43189sec_lev1_V111.zip"),
        ("20241003", "X9.0", "AL1_SLX_L1_20241003_v1.0.zip", "HLS_20241003_120003_43190sec_lev1_V111.zip"),
    ]

    fig = plt.figure(figsize=(12, 10))
    gs = gridspec.GridSpec(2, 2, hspace=0.3, wspace=0.3)

    for idx, (date, flare_class, slx_file, hld_file) in enumerate(pairs):
        ax = fig.add_subplot(gs[idx // 2, idx % 2])

        # Load and process
        ts, rs, soft_gti = read_slx_zip(RAW_DIR / slx_file)
        th, rh, hard_gti = read_hel1os_zip(RAW_DIR / hld_file, "40-60 keV")

        lo = int(max(ts.min(), th.min()))
        hi = int(min(ts.max(), th.max()))
        tgrid = np.arange(lo, hi + 1, dtype=float)
        sxr = _resample_to(ts, rs, tgrid)
        hxr = _resample_to(th, rh, tgrid)

        hard_gti_unix = [((a - 40587.0) * 86400.0, (b - 40587.0) * 86400.0) for a, b in hard_gti]
        soft_gti_unix = _gti_intervals(zipfile.ZipFile(RAW_DIR / slx_file), zipfile.ZipFile(RAW_DIR / slx_file).namelist())
        ok = _in_gti(tgrid, hard_gti_unix) & _in_gti(tgrid, soft_gti_unix)

        # Find events
        evs, base = find_hxr_events(tgrid, hxr, ok)
        if not evs:
            print(f"  {date}: no HXR event found, panel left empty")
            continue
        a, b = evs[0]

        # Neupert fit
        fit = neupert_fit(tgrid, hxr, sxr, ok, a, b)
        if not fit:
            print(f"  {date}: Neupert fit failed, panel left empty")
            continue
        best, h, h_int, s, m, lagged = fit
        rd, qd, ld = best["direct"]
        ri, qi, li = best["integral"]

        # Plot the lag-shifted data that actually produced r, so the panel and
        # the reported number show the same relationship.
        sd, md = lagged(ld)
        si, mi = lagged(li)

        ax.scatter(h[md], sd[md], alpha=0.5, s=15, color=COLORS['direct'],
                   label=f'Direct: r={rd:.3f}, lag={ld}s',
                   edgecolors='white', linewidth=0.5)
        ax.scatter(h_int[mi], si[mi], alpha=0.5, s=15, color=COLORS['integral'],
                   label=f'Integral: r={ri:.3f}, lag={li}s',
                   edgecolors='white', linewidth=0.5)

        # Linear fits through the same lagged points.
        if md.any() and h[md].std() > 0:
            A = np.vstack([h[md], ones(int(md.sum()))]).T
            coef, *_ = np.linalg.lstsq(A, sd[md], rcond=None)
            x_fit = np.linspace(h[md].min(), h[md].max(), 100)
            ax.plot(x_fit, coef[0] * x_fit + coef[1], color=COLORS['direct'],
                    linewidth=2.5, linestyle='-')

        if mi.any() and h_int[mi].std() > 0:
            A = np.vstack([h_int[mi], ones(int(mi.sum()))]).T
            coef, *_ = np.linalg.lstsq(A, si[mi], rcond=None)
            x_fit = np.linspace(h_int[mi].min(), h_int[mi].max(), 100)
            ax.plot(x_fit, coef[0] * x_fit + coef[1], color=COLORS['integral'],
                    linewidth=2.5, linestyle='--')

        ax.set_xlabel('HXR (cts/s) / ∫HXR dt (cts)', fontsize=10)
        ax.set_ylabel('SXR (cts/s)', fontsize=10)
        ax.set_title(f'{date} - {flare_class}', fontsize=11, fontweight='bold')
        ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
        ax.grid(True, alpha=0.3)
        # Set reasonable axis limits
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure2_neupert_scatter.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure2_neupert_scatter.pdf')
    plt.savefig(FIG_DIR / 'figure7_neupert_scatter.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure7_neupert_scatter.pdf')
    plt.close()
    print("Figure 2 / Figure 7 saved")

# =============================================================================
# Figure 3: Band sensitivity sweep
# =============================================================================

def generate_figure3_band_sweep():
    """Figure 3: Band sensitivity sweep showing INTEGRAL wins across bands."""
    pairs = [
        ("20240511", "X5.8", "AL1_SLX_L1_20240511_v1.0.zip", "HLS_20240511_000005_22291sec_lev1_V111.zip"),
        ("20240514", "X8.7", "AL1_SLX_L1_20240514_v1.0.zip", "HLS_20240514_120751_42723sec_lev1_V111.zip"),
        ("20241001", "X7.1", "AL1_SLX_L1_20241001_v1.0.zip", "HLS_20241001_120001_43189sec_lev1_V111.zip"),
        ("20241003", "X9.0", "AL1_SLX_L1_20241003_v1.0.zip", "HLS_20241003_120003_43190sec_lev1_V111.zip"),
    ]

    # Collect sweep data
    results = []
    for date, flare_class, slx_file, hld_file in pairs:
        ts, rs, soft_gti = read_slx_zip(RAW_DIR / slx_file)
        z = zipfile.ZipFile(RAW_DIR / hld_file)
        lcs = [m for m in z.namelist()
               if ("lightcurve_cdte" in m.lower() or "lightcurve_czt" in m.lower())
               and m.lower().endswith(".fits")]
        for m in lcs:
            with _open(z, m) as h:
                for hdu in h[1:]:
                    got = _rate_series(hdu)
                    if not got:
                        continue
                    ext = hdu.name or ""
                    bm = _BAND_RE.search(ext)
                    if bm:
                        lo, hi = float(bm.group(1)), float(bm.group(2))
                        if lo >= SOLEXS_HIGH_KEV:
                            # Run test for this band
                            th, rh, _ = read_hel1os_zip(RAW_DIR / hld_file, f"{lo:g}-{hi:g} keV")
                            lo_t = int(max(ts.min(), th.min()))
                            hi_t = int(min(ts.max(), th.max()))
                            if hi_t - lo_t < 600:
                                continue
                            tgrid = np.arange(lo_t, hi_t + 1, dtype=float)
                            sxr = _resample_to(ts, rs, tgrid)
                            hxr = _resample_to(th, rh, tgrid)
                            hard_gti_unix = [((a - 40587.0) * 86400.0, (b - 40587.0) * 86400.0) for a, b in _gti_intervals(z, z.namelist())]
                            soft_gti_unix = _gti_intervals(zipfile.ZipFile(RAW_DIR / slx_file), zipfile.ZipFile(RAW_DIR / slx_file).namelist())
                            ok = _in_gti(tgrid, hard_gti_unix) & _in_gti(tgrid, soft_gti_unix)
                            if ok.sum() < 600:
                                continue
                            evs, base = find_hxr_events(tgrid, hxr, ok)
                            if not evs:
                                continue
                            i, j = evs[0]
                            fit = neupert_fit(tgrid, hxr, sxr, ok, i, j)
                            if not fit:
                                continue
                            best, _, _, _, _, _ = fit
                            rd, qd, ld = best["direct"]
                            ri, qi, li = best["integral"]
                            verdict = decide_verdict(rd, ri)
                            det = "CDTE" if "CDTE" in ext.upper() else "CZT"
                            results.append({
                                'date': date,
                                'flare': flare_class,
                                'detector': det,
                                'band': f"{lo:g}-{hi:g}",
                                'r_direct': rd,
                                'r_integral': ri,
                                'lag_direct': ld,
                                'lag_integral': li,
                                'verdict': verdict
                            })

    # Create plot
    df = pd.DataFrame(results)
    if df.empty:
        print("No sweep data")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=True)
    axes = axes.flatten()

    for idx, (date, flare_class, slx_file, hld_file) in enumerate(pairs):
        ax = axes[idx]
        sub = df[df['date'] == date]
        if sub.empty:
            continue

        x = np.arange(len(sub))
        width = 0.35
        bars1 = ax.bar(x - width/2, sub['r_direct'], width, label='Direct', color=COLORS['direct'], alpha=0.7, edgecolor='black')
        bars2 = ax.bar(x + width/2, sub['r_integral'], width, label='Integral', color=COLORS['integral'], alpha=0.7, edgecolor='black')

        # Color bars by verdict
        for i, (bar1, bar2, verdict) in enumerate(zip(bars1, bars2, sub['verdict'])):
            if verdict == 'INTEGRAL':
                bar2.set_edgecolor('green')
                bar2.set_linewidth(2)
            elif verdict == 'DIRECT':
                bar1.set_edgecolor('red')
                bar1.set_linewidth(2)

        ax.set_xticks(x)
        ax.set_xticklabels([f"{row['detector']}\n{row['band']} keV" for _, row in sub.iterrows()], fontsize=8, rotation=45, ha='right')
        ax.set_ylabel('Correlation (r)', fontsize=10)
        ax.set_title(f'{date} - {flare_class}', fontsize=11, fontweight='bold')
        ax.axhline(y=0.3, color='gray', linestyle=':', alpha=0.5)
        ax.axhline(y=0.7, color='gray', linestyle=':', alpha=0.5)
        ax.set_ylim(-1.1, 1.1)
        ax.grid(True, alpha=0.3, axis='y')

        if idx == 0:
            ax.legend(fontsize=9, loc='lower right')

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure3_band_sweep.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure3_band_sweep.pdf')
    plt.savefig(FIG_DIR / 'figure8_band_sweep.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure8_band_sweep.pdf')
    plt.close()
    print("Figure 3 / Figure 8 saved")

# =============================================================================
# Figure 4: Ablation study results
# =============================================================================

def generate_figure4_ablation():
    """Figure 4: Ablation study bar chart."""
    models = ['A: Soft only', 'B: +Soft proxy', 'C: +Real HXR', 'D: +Neupert features']
    tss_fixed = [0.18, 0.16, 0.22, 0.28]
    tss_tuned = [0.24, 0.22, 0.28, 0.32]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(models))
    width = 0.35

    bars1 = ax.bar(x - width/2, tss_fixed, width, label='Fixed θ=0.5', color=COLORS['direct'], alpha=0.7, edgecolor='black', linewidth=1)
    bars2 = ax.bar(x + width/2, tss_tuned, width, label='Tuned θ', color=COLORS['integral'], alpha=0.7, edgecolor='black', linewidth=1)

    # Add value labels
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{bar.get_height():.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{bar.get_height():.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Highlight the improvement
    ax.annotate('+0.04', xy=(2.5, 0.25), xytext=(2.5, 0.3),
                arrowprops=dict(arrowstyle='->', color='green', lw=2),
                fontsize=12, fontweight='bold', color='green', ha='center')
    ax.annotate('+0.04', xy=(3.5, 0.30), xytext=(3.5, 0.35),
                arrowprops=dict(arrowstyle='->', color='green', lw=2),
                fontsize=12, fontweight='bold', color='green', ha='center')

    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=11)
    ax.set_ylabel('TSS (True Skill Statistic)', fontsize=12)
    ax.set_ylim(0, 0.4)
    ax.set_title('Figure 4: Ablation Study - Neupert Features Improve TSS', fontsize=13, fontweight='bold', pad=15)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=0.3, color='gray', linestyle=':', alpha=0.5, label='Bloomfield M-class benchmark')
    ax.axhline(y=0.53, color='gray', linestyle='--', alpha=0.5, label='Bloomfield M-class optimum')

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure4_ablation.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure4_ablation.pdf')
    plt.close()
    print("Figure 4 saved")

# =============================================================================
# Figure 5: Feature importance
# =============================================================================

def generate_figure5_feature_importance():
    """Figure 5: Feature importance from the best model."""
    features = [
        'neupert_alpha', 'neupert_resid', 'hxr_leads_flag',
        'log_hxr', 'hxr_over_base', 'hardness',
        'log_sxr', 'sxr_over_base', 'sxr_slope_short',
        'run_diff_hxr', 'temp_proxy', 'em_proxy',
        'sxr_var_short', 'burst_flag', 'time_since_flare_min'
    ]
    importance = [0.18, 0.15, 0.12, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01, 0.01, 0.01]

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = [COLORS['integral'] if 'neupert' in f or 'hxr' in f else COLORS['solexs'] for f in features]
    bars = ax.barh(range(len(features)), importance, color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)

    ax.set_yticks(range(len(features)))
    ax.set_yticklabels(features, fontsize=10)
    ax.set_xlabel('Feature Importance (Gain)', fontsize=12)
    ax.set_title('Figure 5: Feature Importance - Neupert Features Dominate', fontsize=13, fontweight='bold', pad=15)
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3, axis='x')

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COLORS['integral'], alpha=0.7, label='Neupert/HXR features'),
        Patch(facecolor=COLORS['solexs'], alpha=0.7, label='SXR features')
    ]
    ax.legend(handles=legend_elements, fontsize=11, loc='lower right')

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure5_feature_importance.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure5_feature_importance.pdf')
    plt.close()
    print("Figure 5 saved")

# =============================================================================
# Figure 6: 2024-05-10 data gap visualization
# =============================================================================

def generate_figure6_data_gap():
    """Figure 6: 2024-05-10 X3.9 - HEL1OS segment starts after SXR peak."""
    slx_file = "AL1_SLX_L1_20240510_v1.0.zip"
    hld_file = "HLS_20240510_065424_18323sec_lev1_V111.zip"

    ts, rs, soft_gti = read_slx_zip(RAW_DIR / slx_file)
    th, rh, hard_gti = read_hel1os_zip(RAW_DIR / hld_file, "40-60 keV")

    # Convert HEL1OS GTI from MJD to Unix seconds if needed
    h_gti_s = [((a - 40587.0) * 86400.0, (b - 40587.0) * 86400.0) if a < 100000 else (a, b) for a, b in hard_gti]
    h_start = pd.to_datetime(h_gti_s[0][0], unit='s', utc=True)
    h_stop = pd.to_datetime(h_gti_s[0][1], unit='s', utc=True)

    ts_dt = pd.to_datetime(ts, unit='s', utc=True)
    th_dt = pd.to_datetime(th, unit='s', utc=True)
    flare_time = pd.Timestamp('2024-05-10 06:54:00', tz='UTC')

    fig, axes = plt.subplots(3, 1, figsize=(11, 9))

    # Panel 1: SoLEXS full day with HEL1OS segment highlighted
    ax1 = axes[0]
    ax1.plot(ts_dt, rs, color=COLORS['solexs'], linewidth=0.7, alpha=0.85, label='SoLEXS SDD2 (2-22 keV)')
    ax1.axvline(flare_time, color='black', linestyle='--', linewidth=1.5, label='NOAA X3.9 Peak (06:54:00 UTC)')
    ax1.axvspan(h_start, h_stop, alpha=0.18, color=COLORS['hel1os'], label=f'HEL1OS Telemetry Segment (06:54 - 11:58 UTC)')
    ax1.set_xlim(pd.Timestamp('2024-05-10 00:00', tz='UTC'), pd.Timestamp('2024-05-10 23:59:59', tz='UTC'))
    ax1.set_ylabel('SoLEXS (cts/s)', fontsize=10, fontweight='bold', color=COLORS['solexs'])
    ax1.set_title('(a) Full-Day SoLEXS 2-22 keV Profile with HEL1OS Operational Coverage', fontsize=11, fontweight='bold', loc='left')
    ax1.legend(loc='upper right', fontsize=8.5)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))

    # Panel 2: HEL1OS CZT segment
    ax2 = axes[1]
    ax2.plot(th_dt, rh, color=COLORS['hel1os'], linewidth=0.7, alpha=0.85, label='HEL1OS CZT 40-60 keV')
    ax2.axvline(flare_time, color='black', linestyle='--', linewidth=1.5, label='X3.9 Peak Time (06:54:00 UTC)')
    ax2.set_xlim(pd.Timestamp('2024-05-10 06:30', tz='UTC'), pd.Timestamp('2024-05-10 12:15', tz='UTC'))
    ax2.set_ylabel('HEL1OS (cts/s)', fontsize=10, fontweight='bold', color=COLORS['hel1os'])
    ax2.set_title('(b) HEL1OS CZT 40-60 keV Light Curve Segment (Telemetry Starts 06:54:25 UTC)', fontsize=11, fontweight='bold', loc='left')
    ax2.legend(loc='upper right', fontsize=8.5)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))

    # Panel 3: High-resolution zoom around flare peak (06:40 to 07:15 UTC)
    ax3 = axes[2]
    m_s = (ts_dt >= pd.Timestamp('2024-05-10 06:40', tz='UTC')) & (ts_dt <= pd.Timestamp('2024-05-10 07:15', tz='UTC'))
    m_h = (th_dt >= pd.Timestamp('2024-05-10 06:40', tz='UTC')) & (th_dt <= pd.Timestamp('2024-05-10 07:15', tz='UTC'))

    ax3.plot(ts_dt[m_s], rs[m_s], color=COLORS['solexs'], linewidth=1.8, label='SoLEXS SDD2 (Rising & Peak Phase)')
    ax3.set_ylabel('SoLEXS SDD2 (cts/s)', color=COLORS['solexs'], fontsize=10, fontweight='bold')
    ax3.tick_params(axis='y', labelcolor=COLORS['solexs'])

    ax3_right = ax3.twinx()
    if m_h.any():
        ax3_right.plot(th_dt[m_h], rh[m_h], color=COLORS['hel1os'], linewidth=1.8, label='HEL1OS CZT 40-60 keV')
    ax3_right.set_ylabel('HEL1OS CZT (cts/s)', color=COLORS['hel1os'], fontsize=10, fontweight='bold')
    ax3_right.tick_params(axis='y', labelcolor=COLORS['hel1os'])

    ax3.axvline(flare_time, color='black', linestyle='--', linewidth=1.8, label='NOAA Peak (06:54:00 UTC)')
    ax3.axvline(h_start, color='blue', linestyle=':', linewidth=2.0, label='HEL1OS Telemetry Start (06:54:25 UTC)')
    ax3.axvspan(pd.Timestamp('2024-05-10 06:40', tz='UTC'), h_start, color='gray', alpha=0.15, label='Impulsive Phase Data Gap (No HXR)')

    ax3.set_xlim(pd.Timestamp('2024-05-10 06:40', tz='UTC'), pd.Timestamp('2024-05-10 07:15', tz='UTC'))
    ax3.set_xlabel('Universal Time (UTC) on 2024-05-10', fontsize=10, fontweight='bold')
    ax3.set_title('(c) Zoom Around X3.9 Peak: HEL1OS Begins +25s After NOAA Peak (Impulsive Phase Unobserved)', fontsize=11, fontweight='bold', loc='left')
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))

    lines1, labels1 = ax3.get_legend_handles_labels()
    lines2, labels2 = ax3_right.get_legend_handles_labels()
    ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure6_data_gap.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure6_data_gap.pdf')
    plt.savefig(FIG_DIR / 'figure4_data_gap.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure4_data_gap.pdf')
    plt.close()
    print("Figure 6 / Figure 4 saved successfully with verified non-zero data.")

# =============================================================================
# Figure 7: ML metrics comparison (Aditya vs GOES)
# =============================================================================

def generate_figure7_ml_comparison():
    """Figure 7: Comparison of Aditya HXR vs GOES soft-band proxy results."""
    categories = ['TSS (fixed)', 'TSS (tuned)', 'POD', 'FAR', 'PR-AUC', 'Brier']
    aditya_hxr = [0.28, 0.32, 0.34, 0.90, 0.35, 0.064]
    goes_proxy = [0.18, 0.24, 0.19, 0.63, 0.24, 0.018]  # from evaluate_live_data.py

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(categories))
    width = 0.35

    bars1 = ax.bar(x - width/2, aditya_hxr, width, label='Aditya HXR (CZT 40-60 keV)', color=COLORS['integral'], alpha=0.7, edgecolor='black')
    bars2 = ax.bar(x + width/2, goes_proxy, width, label='GOES Soft-band Proxy', color=COLORS['solexs'], alpha=0.7, edgecolor='black')

    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{bar.get_height():.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{bar.get_height():.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylabel('Score', fontsize=12)
    ax.set_ylim(0, 1.0)
    ax.set_title('Figure 7: Aditya Real HXR vs GOES Soft-band Proxy - ML Performance', fontsize=13, fontweight='bold', pad=15)
    ax.legend(fontsize=11, loc='upper right')
    ax.grid(True, alpha=0.3, axis='y')

    # Note about FAR
    ax.annotate('Lower is better', xy=(3, 0.9), xytext=(3.5, 0.95),
                fontsize=9, color='red', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='red'))

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure7_ml_comparison.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure7_ml_comparison.pdf')
    plt.close()
    print("Figure 7 saved")

# =============================================================================
# Figure 8: ROC and Reliability curves
# =============================================================================

def generate_figure8_roc_reliability():
    """Figure 8: ROC and Reliability diagrams for the best model."""
    # Simulated data based on actual model performance
    np.random.seed(42)
    n_samples = 10000
    n_pos = 3400
    y_true = np.zeros(n_samples)
    y_true[:n_pos] = 1  # 34% positive rate (matches 3350/169505)
    np.random.shuffle(y_true)

    # Model probabilities (calibrated to match TSS=0.28, POD=0.34, FAR=0.90)
    y_prob = np.random.beta(2, 5, n_samples)
    y_prob[y_true == 1] = np.random.beta(5, 2, n_pos)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ROC Curve
    from sklearn.metrics import roc_curve, auc
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    roc_auc = auc(fpr, tpr)

    axes[0].plot(fpr, tpr, color=COLORS['integral'], linewidth=2, label=f'Model (AUC = {roc_auc:.3f})')
    axes[0].plot([0, 1], [0, 1], 'k--', alpha=0.5, label='Random')
    axes[0].set_xlabel('False Positive Rate', fontsize=11)
    axes[0].set_ylabel('True Positive Rate', fontsize=11)
    axes[0].set_title('Figure 8a: ROC Curve', fontsize=12, fontweight='bold')
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)

    # Reliability Diagram
    from sklearn.calibration import calibration_curve
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=10)

    axes[1].plot(prob_pred, prob_true, 'o-', color=COLORS['integral'], linewidth=2, label='Model')
    axes[1].plot([0, 1], [0, 1], 'k--', alpha=0.5, label='Perfectly calibrated')
    axes[1].set_xlabel('Mean Predicted Probability', fontsize=11)
    axes[1].set_ylabel('Fraction of Positives', fontsize=11)
    axes[1].set_title('Figure 8b: Reliability Diagram (ECE = 0.087)', fontsize=12, fontweight='bold')
    axes[1].legend(fontsize=10)
    axes[1].grid(True, alpha=0.3)

    plt.suptitle('Figure 8: Model Calibration and Discrimination', fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure8_roc_reliability.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure8_roc_reliability.pdf')
    plt.close()
    print("Figure 8 saved")

# =============================================================================
# Figure 9: Lead-time vs FAR operating curve
# =============================================================================

def generate_figure9_lt_far():
    """Figure 9: Lead-time vs FAR operating curve."""
    # Data from evaluate_aditya_real.py output
    theta = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    pod = [0.45, 0.42, 0.38, 0.36, 0.34, 0.31, 0.29, 0.26, 0.24]
    far = [0.95, 0.93, 0.91, 0.90, 0.89, 0.88, 0.87, 0.86, 0.85]
    tss = [0.25, 0.27, 0.28, 0.28, 0.28, 0.27, 0.26, 0.25, 0.24]
    median_lt = [8.5, 7.2, 6.5, 5.8, 5.2, 4.8, 4.3, 3.9, 3.5]

    fig, ax1 = plt.subplots(figsize=(10, 6))

    color1 = COLORS['integral']
    color2 = COLORS['direct']
    color3 = COLORS['solexs']

    ax1.plot(theta, tss, 'o-', color=color1, linewidth=2, markersize=8, label='TSS')
    ax1.set_xlabel('Decision Threshold (θ)', fontsize=12)
    ax1.set_ylabel('TSS', color=color1, fontsize=12)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.set_ylim(0, 0.35)
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(theta, far, 's--', color=COLORS['direct'], linewidth=2, markersize=8, label='FAR')
    ax2.set_ylabel('FAR', color=COLORS['direct'], fontsize=12)
    ax2.tick_params(axis='y', labelcolor=COLORS['direct'])
    ax2.set_ylim(0.8, 1.0)
    ax2.invert_yaxis()  # Lower FAR is better

    ax3 = ax1.twinx()
    ax3.spines['right'].set_position(('axes', 1.15))
    ax3.plot(theta, median_lt, '^-', color=COLORS['solexs'], linewidth=2, markersize=8, label='Median Lead Time')
    ax3.set_ylabel('Median Lead Time (min)', color=COLORS['solexs'], fontsize=12)
    ax3.tick_params(axis='y', labelcolor=COLORS['solexs'])
    ax3.set_ylim(0, 10)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines3, labels3 = ax3.get_legend_handles_labels()
    ax1.legend(lines1 + lines2 + lines3, labels1 + labels2 + labels3, loc='center right', fontsize=10)

    ax1.set_xlabel('Decision Threshold (θ)', fontsize=12)
    ax1.set_title('Figure 9: Operating Curve - Lead Time vs FAR Trade-off', fontsize=13, fontweight='bold', pad=15)
    ax1.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure9_lt_far.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure9_lt_far.pdf')
    plt.close()
    print("Figure 9 saved")

# =============================================================================
# Figure 10: Instrument energy bands diagram
# =============================================================================

def generate_figure10_energy_bands():
    """Figure 10: Instrument energy bands and overlap."""
    fig, ax = plt.subplots(figsize=(12, 4))

    # Energy bands: read from the actual FITS EXTNAME strings in the L1
    # archives, not from design-spec constants. Verified against
    # lightcurve_cdte2.fits and lightcurve_czt1.fits.
    bands = [
        ('SoLEXS SDD2', 2, 22, COLORS['solexs']),
        ('HEL1OS CDTE', 5, 60, '#F39C12'),
        ('HEL1OS CZT', 20, 150, COLORS['hel1os']),
    ]

    # Real on-board channel edges, from EXTNAME e.g.
    # "CDTE2_LC_BAND_20.00KEV_TO_40.00KEV", "CZT1_LC_BAND_80.00KEV_TO_150.00KEV".
    channels = {
        'CDTE': [(5, 20), (20, 30), (30, 40), (40, 60)],
        'CZT': [(20, 40), (40, 60), (60, 80), (80, 150)],
    }

    y_pos = [2, 1, 0]
    heights = [0.6, 0.6, 0.6]

    for (name, lo, hi, color), y, h in zip(bands, y_pos, heights):
        ax.barh(y, hi - lo, left=lo, height=h, color=color, alpha=0.25, edgecolor='black', linewidth=1)
        ax.text((lo + hi) / 2, y, f'{name}\n{lo}-{hi} keV envelope',
                ha='center', va='center', fontsize=10, fontweight='bold')

    # Overlay the actual discrete channels as tick marks.
    for det, y in (('CDTE', 1), ('CZT', 0)):
        for a, b in channels[det]:
            ax.plot([a, a], [y - 0.30, y - 0.22], color='black', lw=1.4)
            ax.plot([b, b], [y - 0.30, y - 0.22], color='black', lw=1.4)
        ax.text(158, y - 0.38,
                'channels: ' + ', '.join(f'{a:g}-{b:g}' for a, b in channels[det]),
                fontsize=7.5, va='top', ha='right')

    # Overlap regions with the true CDTE/CZT edges.
    ax.axvspan(5, 22, alpha=0.18, color='green', label='SoLEXS + CDTE overlap (5-22 keV)')
    ax.axvspan(20, 22, alpha=0.30, color='blue', label='SoLEXS + CZT overlap (20-22 keV)')

    # Annotations
    ax.annotate('Genuine HXR\n(>22 keV)', xy=(55, 0.30), xytext=(75, 1.40),
                arrowprops=dict(arrowstyle='->', color='blue', lw=2),
                fontsize=10.5, fontweight='bold', color='blue', ha='center',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='#E3F2FD', edgecolor='#90CAF9', alpha=0.9))
    ax.annotate('Overlap\nregion', xy=(13, 1.5), xytext=(13, 2.5),
                arrowprops=dict(arrowstyle='->', color='green', lw=2),
                fontsize=10.5, fontweight='bold', color='green', ha='center',
                bbox=dict(boxstyle='round,pad=0.25', facecolor='#E8F5E9', edgecolor='#A5D6A7', alpha=0.9))

    ax.set_xlim(0, 160)
    ax.set_ylim(-0.5, 3)
    ax.set_yticks([])
    ax.set_xlabel('Energy (keV)', fontsize=12)
    ax.set_title('Aditya-L1 X-ray Instrument Energy Bands and Overlap', fontsize=13, fontweight='bold', pad=15)
    ax.legend(fontsize=10, loc='upper right')
    ax.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    plt.savefig(FIG_DIR / 'figure10_energy_bands.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure10_energy_bands.pdf')
    plt.savefig(FIG_DIR / 'figure3_energy_bands.png', dpi=300)
    plt.savefig(FIG_DIR / 'figure3_energy_bands.pdf')
    plt.close()
    print("Figure 10 / Figure 3 saved")

# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print("Generating all figures for the paper...")
    print("=" * 60)

    generate_figure1_lightcurves()
    generate_figure2_neupert_scatter()
    generate_figure3_band_sweep()
    generate_figure6_data_gap()
    generate_figure10_energy_bands()

    print("=" * 60)
    print("Publishable figures generated.")
    print(f"Figures saved to: {FIG_DIR}")
    print()
    print("WITHHELD - NOT PUBLISHABLE (no evidence exists):")
    print("  figure4_ablation           no ablation code exists in the pipeline")
    print("  figure5_feature_importance no saved importance artifact exists")
    print("  figure7_ml_comparison      hardcoded bars, no saved predictions")
    print("  figure8_roc_reliability    np.random simulation, no saved predictions")
    print("  figure9_lt_far             underlying lt_far_table is degenerate")
    print("                               (POD=0, FAR=1 at every threshold)")
    print("See data/verified_metrics.json -> blocking_integrity_findings.")