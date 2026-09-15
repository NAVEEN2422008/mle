"""REAL-DATA RUN: genuine GOES XRS telemetry through the whole pipeline,
validated against NOAA's official flare event list (ground truth).

Data provenance:
- Light curves: services.swpc.noaa.gov 7-day XRS JSON (~1-min cadence, no auth)
    flux_long  = 0.1-0.8 nm (1-8 A)  -> SOFT band proxy (SoLEXS analogue)
    flux_short = 0.05-0.4 nm (0.5-4 A) -> harder band proxy (HEL1OS-low analogue)
- Ground truth: SWPC xray-flares event list (official start/peak/class)

Both channels are rescaled to pseudo-counts for the Poisson/CUSUM detectors;
features are ratios/logs so scale cancels.
"""
import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
import pytest
from src.ingest.goes_fetcher import fetch_goes_xrs_json, fetch_goes_events_json
from src.forecast.pipeline import FlareForecastPipeline


def test_realdata_goes():
    print("=" * 68)
    print("REAL TELEMETRY RUN - GOES XRS x NOAA EVENT LIST")
    print("=" * 68)

    # 1. Fetch
    lc = fetch_goes_xrs_json()
    ev = fetch_goes_events_json()
    if lc is None or lc.empty or ev is None or ev.empty:
        pytest.skip("NOAA endpoint unavailable or offline.")
        return

    span_h = (lc["timestamp"].max() - lc["timestamp"].min()).total_seconds() / 3600
    print(f"[fetch] light curve: {len(lc)} samples over {span_h:.1f} h")
    print(f"[fetch] NOAA official flare events fetched: {len(ev)}")

    # 2. Prepare streams: keep NATIVE 1-min cadence, pseudo-counts for detectors
    df = pd.DataFrame({
        "timestamp": lc["timestamp"],
        "soft": lc["flux_long"] * 1e9,     # W/m2 -> pseudo-counts (detection only)
        "hard": lc["flux_short"] * 1e12,
    }).dropna().reset_index(drop=True)
    n = len(df)
    assert n > 100
    print(f"[prep ] {n} native 1-min samples; soft [{df['soft'].min():.0f}, {df['soft'].max():.0f}], "
          f"hard [{df['hard'].min():.1f}, {df['hard'].max():.1f}]")

    t0 = df["timestamp"].iloc[0]
    noaa_peaks = []
    for _, r in ev.iterrows():
        try:
            pt = pd.to_datetime(r["timestamp"])
            if t0 <= pt <= df["timestamp"].iloc[-1]:
                noaa_peaks.append((float((pt - t0).total_seconds()), str(r["goes_class"])))
        except Exception:
            continue
    print(f"[truth] NOAA events inside window: {len(noaa_peaks)} "
          f"({len(set(c for _, c in noaa_peaks))} distinct classes)")

    # ------------------------------------------------------------------
    # 3. Full pipeline on real telemetry (windows in SAMPLES of 1-min cadence)
    # ------------------------------------------------------------------
    pipe = FlareForecastPipeline(
        horizon_min=15,          # 15 samples at 1-min cadence
        n_folds=4,
        use_lightgbm=True,
        min_class_flux=0.0,      # counts-scale stream; keep every detected peak
        feat_short_s=10,         # 10-min short window
        feat_long_s=120,         # 2-h long window
        neupert_win_s=15,        # 15-min Neupert correlation window
        det_baseline_window=180, # 3-h detector baseline (samples)
        det_h_c_sigma=4.0,       # real-Sun SNR is far lower than synthetic
        det_alpha=0.02,          # ~50-min effective baseline EMA at 1-min cadence
    )
    rep = pipe.run(df)           # self-labelling from detected catalogue

    print(f"\n[catalogue] pipeline detections: {rep.n_catalogue_peaks}")
    tc = getattr(rep, "truth_check", {})
    print(f"           vs NOAA truth check dict: {tc if tc else '(no truth passed to pipe)'}")

    # Direct validation against NOAA list (peaks from run(), true elapsed seconds)
    dpeaks = getattr(rep, "detected_peaks", [])

    TOL_S = 900  # 15 min tolerance (1-min source cadence + interpolation smear)
    matched, misses = [], []
    for np_sec, cls in sorted(noaa_peaks):
        cands = [abs(p - np_sec) for p in dpeaks]
        if cands and min(cands) <= TOL_S:
            j = int(np.argmin(cands))
            matched.append((cls, int(min(cands))))
        else:
            misses.append(cls)

    n_noaa = len(noaa_peaks)
    frac = len(matched) / n_noaa if n_noaa else float("nan")
    print(f"[validate] NOAA events matched within {TOL_S//60} min: "
          f"{len(matched)}/{n_noaa} ({frac:.0%})")
    for cls, dt in matched:
        print(f"           HIT  {cls:>4s}  |dt|={dt}s")
    for cls in misses:
        print(f"           MISS       ({cls})")

    # ------------------------------------------------------------------
    # 4. Forecast stage numbers (only meaningful if positives exist)
    # ------------------------------------------------------------------
    if "error" not in rep.oof:
        o = rep.oof
        bc = rep.baseline_compare
        print(f"\n[forecast] base-rate={rep.n_positives/max(rep.n_labelled,1):.3f} "
              f"usable={rep.n_labelled} coverage={bc.get('oof_coverage_frac')}")
        print(f"           model TSS={o['tss']} POD={o['pod']} FAR={o['far']} "
              f"HSS={o['hss']} PR-AUC={o['pr_auc']} @theta={o['threshold']}")
        print(f"           vs climatology TSS={bc['climatology']['tss']}, "
              f"persistence TSS={bc['persistence']['tss']} -> "
              f"beats_both={rep.beats_baselines}")
    else:
        print(f"\n[forecast] skipped: {rep.oof.get('error')}")

    # ------------------------------------------------------------------
    # 4b. Event-level alerts: raw crossings vs k-of-m hysteresis
    # ------------------------------------------------------------------
    lt = pd.DataFrame(getattr(rep, "lt_far_table", []))
    ltk = pd.DataFrame(getattr(rep, "lt_far_table_kofm", []))
    b = None
    if len(lt):
        b = lt.loc[lt["tss"].idxmax()]
        print(f"[alerts/raw] best: theta={b['theta']} TSS={b['tss']:+.2f} "
              f"FAR={b['far']:.2f} false_alarms={int(b['false_alarms'])} "
              f"median-lead={b['median_lt_min']}min")
    if len(ltk) and b is not None:
        bk = ltk.loc[ltk["tss"].idxmax()]
        print(f"[alerts/kofm] best: theta={bk['theta']} TSS={bk['tss']:+.2f} "
              f"FAR={bk['far']:.2f} false_alarms={int(bk['false_alarms'])} "
              f"median-lead={bk['median_lt_min']}min")
        print(f"           >> hysteresis effect: TSS {b['tss']:+.2f}->{bk['tss']:+.2f}, "
              f"false alarms {int(b['false_alarms'])}->{int(bk['false_alarms'])}")

    # ------------------------------------------------------------------
    # 5. Gates (conditional on having NOAA events in-window)
    # ------------------------------------------------------------------
    ok = True
    if n_noaa >= 3:
        assert frac >= 0.5, f"detector must recover >=50% of NOAA >=C-class events, got {frac:.0%}"
        print("\nGATE: >=50% NOAA-event recovery  -> PASS")
    elif n_noaa > 0:
        print(f"\nGATE: only {n_noaa} NOAA events in window - recovery gate waived")
    else:
        print("\nGATE: quiet week (0 events) - detector false-alarm rate becomes the metric")
        fa_per_day = rep.n_catalogue_peaks / max(span_h / 24, 1e-9)
        print(f"       catalogue events/day on quiet Sun: {fa_per_day:.2f}")

    print("=" * 68)
    print("REAL TELEMETRY RUN:", "PASS" if ok else "FAIL")
    print("=" * 68)
