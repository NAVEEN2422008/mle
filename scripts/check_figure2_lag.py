"""Confirm the Figure 2 scatter panels plot the same data that produced r.

For each event, recompute the correlation directly from the arrays that the
scatter actually draws. Before the lag-alignment fix these disagreed with the
reported r, because the panel drew the unlagged SXR series.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paper"))
import generate_figures as G  # noqa: E402

PAIRS = [
    ("20240511", "HLS_20240511_000005_22291sec_lev1_V111.zip"),
    ("20240514", "HLS_20240514_120751_42723sec_lev1_V111.zip"),
    ("20241001", "HLS_20241001_120001_43189sec_lev1_V111.zip"),
    ("20241003", "HLS_20241003_120003_43190sec_lev1_V111.zip"),
]

print(f"{'date':<10} {'model':<10} {'reported r':>11} {'plot r':>9}  verdict")
all_ok = True
for date, hf in PAIRS:
    slx = next(G.RAW_DIR.glob(f"AL1_SLX_L1_{date}*")).name
    ts, rs, _ = G.read_slx_zip(G.RAW_DIR / slx)
    th, rh, hg = G.read_hel1os_zip(G.RAW_DIR / hf, "40-60 keV")

    lo, hi = int(max(ts.min(), th.min())), int(min(ts.max(), th.max()))
    g = np.arange(lo, hi + 1, dtype=float)
    sxr = G._resample_to(ts, rs, g)
    hxr = G._resample_to(th, rh, g)

    hgu = [((a - 40587.0) * 86400.0, (b - 40587.0) * 86400.0) for a, b in hg]
    z = zipfile.ZipFile(G.RAW_DIR / slx)
    sgu = G._gti_intervals(z, z.namelist())
    ok = G._in_gti(g, hgu) & G._in_gti(g, sgu)

    evs, _ = G.find_hxr_events(g, hxr, ok)
    a, b = evs[0]
    best, h, h_int, s, m, lagged = G.neupert_fit(g, hxr, sxr, ok, a, b)

    for tag in ("direct", "integral"):
        r, _q, lag = best[tag]
        sh, mm = lagged(lag)
        x, y = (h, sh) if tag == "direct" else (h_int, sh)
        rc = float(np.corrcoef(x[mm], y[mm])[0, 1])
        ok_flag = abs(r - rc) < 1e-9
        all_ok &= ok_flag
        print(f"{date:<10} {tag:<10} {r:>11.4f} {rc:>9.4f}  {'OK' if ok_flag else 'MISMATCH'}")

print("\nALL PANELS MATCH REPORTED r" if all_ok else "\nSTILL MISMATCHED")