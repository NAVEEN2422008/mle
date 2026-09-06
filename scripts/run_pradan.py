"""One-command PRADAN ingest day.

    python scripts/run_pradan.py --raw data/raw [--mock-days 0]

Pipeline:
  1. Read every AL1_SLX_* / AL1_HLD_* zip via hardened readers
  2. Collapse HEL1OS bands; arbitrate SoLEXS SDD1/SDD2
  3. Cache parquet to data/processed/
  4. Detect -> master catalogue -> dedupe -> CSV
  5. Forecast CV vs baselines (if enough events)
  6. If truth_mock.json present (mock mode): recovery validation
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--horizon", type=int, default=15, help="minutes")
    args = ap.parse_args()

    t_start = time.time()
    raw = Path(args.raw)
    proc = Path(args.processed)
    proc.mkdir(parents=True, exist_ok=True)

    zips = sorted(raw.glob("*.zip"))
    n_slx = sum(1 for z in zips if "SLX" in z.name.upper())
    n_hld = sum(1 for z in zips if "HLD" in z.name.upper())
    print("=" * 68)
    print("PRADAN INGEST RUN")
    print("=" * 68)
    print(f"[scan] {len(zips)} zip(s) in {raw}  (SoLEXS={n_slx}, HEL1OS={n_hld})")
    if not zips:
        print("\nNo archives found.")
        print("Option A (real): download from https://pradan1.issdc.gov.in/al1/")
        print("  and drop AL1_SLX_L1_*.zip / AL1_HLD_L1_*.zip into data/raw/.")
        print("Option B (rehearsal): python tests/make_mock_pradan.py --days 2")
        return 1

    # ---------- 1-2. read ----------
    from src.ingest.solexs_reader import read_solexs_directory, arbitrate_sdd_rows
    from src.ingest.hel1os_reader import read_hel1os_directory, collapse_bands

    slx = read_solexs_directory(str(raw))
    hld = read_hel1os_directory(str(raw))
    if slx.empty or hld.empty:
        print(f"[read] solexs rows={len(slx)} hel1os rows={len(hld)} -> cannot proceed")
        return 1
    slx = arbitrate_sdd_rows(slx)
    hld_c = collapse_bands(hld)
    print(f"[read] SoLEXS {len(slx)} rows after SDD arbitration | "
          f"HEL1OS {len(hld)} rows across {hld['energy_band'].nunique()} band(s) "
          f"-> collapsed {len(hld_c)}")

    span = (slx["timestamp"].max() - slx["timestamp"].min())
    print(f"[span] {slx['timestamp'].min()} .. {slx['timestamp'].max()} ({span})")

    # ---------- 3. cache ----------
    def _save(df_in: pd.DataFrame, base_name: str) -> None:
        try:
            df_in.to_parquet(proc / f"{base_name}.parquet", index=False)
        except Exception:
            df_in.to_csv(proc / f"{base_name}.csv.gz", index=False, compression="gzip")

    _save(slx, "solexs")
    _save(hld, "hel1os_bands")
    _save(hld_c, "hel1os")

    # align to SoLEXS grid for the fused stream
    df = pd.DataFrame({
        "timestamp": slx["timestamp"],
        "soft": slx["counts"].to_numpy(),
        "hard": hld_c.set_index("timestamp")["counts"]
                 .reindex(pd.DatetimeIndex(slx["timestamp"]))
                 .ffill(limit=60).bfill(limit=60).fillna(0.0)
                 .to_numpy(),
    })
    _save(df, "fused")
    n = len(df)
    print(f"[fuse] aligned stream: {n} samples")

    # ---------- 4. detect + catalogue ----------
    from src.forecast.pipeline import FlareForecastPipeline
    pipe = FlareForecastPipeline(
        horizon_min=args.horizon,
        use_lightgbm=True,
        min_class_flux=0.0,
        det_h_c_sigma=10.0,
        feat_short_s=max(10, int(600 / max(cadence_s(df), 1e-9))),   # ~10-min
        feat_long_s=max(30, int(7200 / max(cadence_s(df), 1e-9))),   # ~2-h
        neupert_win_s=max(5, int(900 / max(cadence_s(df), 1e-9))),
    )
    rep = pipe.run(df)

    # catalogue straight from detectors:
    t0 = pd.Timestamp(df['timestamp'].iloc[0])
    dpeaks, dflux = pipe._detect_catalogue_peaks(df)
    cat = pd.DataFrame({
        "peak_utc": [str(t0 + pd.Timedelta(seconds=float(p))) for p in dpeaks],
        "peak_counts": np.round(dflux, 1),
    })
    cat["class_like"] = pd.cut(cat["peak_counts"],
                               [0, 1500, 5000, 20000, np.inf],
                               labels=["B/A", "C", "M", "X"]).astype(str)
    out_csv = proc / "flare_catalogue.csv"
    cat.to_csv(out_csv, index=False)
    print(f"[catalogue] {len(cat)} events -> {out_csv}")

    # ---------- 5. forecast (guarded) ----------
    n_pos = rep.n_positives
    if "error" not in rep.oof and n_pos >= 200 and rep.n_catalogue_peaks >= 10:
        o, bc = rep.oof, rep.baseline_compare
        print(f"[forecast] base-rate={n_pos/max(rep.n_labelled,1):.3f} "
              f"usable={rep.n_labelled} coverage={bc.get('oof_coverage_frac')}")
        print(f"           model TSS={o['tss']:+.3f} POD={o['pod']:.3f} FAR={o['far']:.3f} "
              f"PR-AUC={o['pr_auc']:.3f} @theta={o['threshold']}")
        print(f"           climatology TSS={bc['climatology']['tss']:+.3f} | "
              f"persistence TSS={bc['persistence']['tss']:+.3f} | beats_both={rep.beats_baselines}")
    else:
        need_days = max(1, int(np.ceil(30 / max(rep.n_catalogue_peaks / max(
            (pd.Timestamp(df['timestamp'].iloc[-1])
             - pd.Timestamp(df['timestamp'].iloc[0])).total_seconds() / 86400, 0.5), 1))))
        print("[forecast] SKIPPED - insufficient independent flare episodes "
              f"({rep.n_catalogue_peaks} detected, {n_pos} positive labels).")
        print("           CV training needs ~>=10 episodes; download more days.")
        print(f"           At this rate, ~{need_days}+ day(s) of data recommended.")

    # ---------- 6. truth validation (mock mode) ----------
    truth_path = raw / "truth_mock.json"
    if truth_path.exists():
        truth = json.loads(truth_path.read_text())
        tpeaks = [float(t["peak_sec"]) +
                  (pd.Timestamp(str(t["date"])).value - t0.value) / 1e9
                  for t in truth]
        tol = 900.0
        used, hits = set(), 0
        for tp in tpeaks:
            cands = [(abs(p - tp), j) for j, p in enumerate(dpeaks)
                     if j not in used]
            if cands and min(cands)[0] <= tol:
                used.add(min(cands)[1])
                hits += 1
        frac = hits / len(tpeaks) if tpeaks else float("nan")
        print(f"[truth] injected events recovered within 15min: "
              f"{hits}/{len(tpeaks)} ({frac:.0%})")

    print(f"\n[done] in {time.time()-t_start:.1f}s")
    return 0


def cadence_s(df: pd.DataFrame) -> float:
    ts = pd.to_datetime(df["timestamp"])
    if len(ts) < 2:
        return 1.0
    return max((ts.iloc[1] - ts.iloc[0]).total_seconds(), 0.5)


if __name__ == "__main__":
    raise SystemExit(main())
