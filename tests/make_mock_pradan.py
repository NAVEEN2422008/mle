"""Generate mock PRADAN-format Aditya-L1 archives for offline dress rehearsal.

Creates data/raw/:
  AL1_SLX_L1_YYYYMMDD_v1.0.zip   -> AL1_SLX_L1_YYYYMMDD_v1.0/SDD2/AL1_SOLEXS_YYYYMMDD_SDD2_L1.lc.gz
                                  -> .../SDD1/AL1_SOLEXS_YYYYMMDD_SDD1_L1.lc.gz
      FITS: primary + BINTABLE 'LIGHTCURVE' (TIME s-since-midnight, COUNTS, FRACEXP),
            header DATE-OBS.
  AL1_HLD_L1_YYYYMMDD_v1.0.zip   -> .../HEL1OS_L1_YYYYMMDD_lc.fits.gz
      FITS: BINTABLEs EXTNAME = CDTE_BAND1 / CZT_TOTAL (TIME, RATE)
  truth_mock.json                -> injected flare peaks/classes for validation

Usage: python tests/make_mock_pradan.py [--days 2] [--start 20240515]
"""
import gzip
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from astropy.io import fits

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def _solexs_fits_bytes(day: datetime, times: np.ndarray, counts: np.ndarray) -> bytes:
    cols = [
        fits.Column(name="TIME", format="D", unit="s", array=times),
        fits.Column(name="COUNTS", format="D", unit="count/s", array=counts),
        fits.Column(name="FRACEXP", format="E", array=np.ones_like(times)),
    ]
    t = fits.BinTableHDU.from_columns(cols, name="LIGHTCURVE")
    t.header["DATE-OBS"] = day.strftime("%Y-%m-%dT00:00:00")
    t.header["INSTRUME"] = "SoLEXS"
    t.header["TELESCOP"] = "Aditya-L1"
    prim = fits.PrimaryHDU()
    prim.header["DATE-OBS"] = t.header["DATE-OBS"]
    buf = io.BytesIO()
    fits.HDUList([prim, t]).writeto(buf)
    return buf.getvalue()


def _hel1os_fits_bytes(day: datetime, times: np.ndarray,
                       cdte: np.ndarray, czt: np.ndarray) -> bytes:
    e1 = fits.BinTableHDU.from_columns([
        fits.Column(name="TIME", format="D", unit="s", array=times),
        fits.Column(name="RATE", format="D", unit="count/s", array=cdte),
    ], name="CDTE_BAND1")
    e2 = fits.BinTableHDU.from_columns([
        fits.Column(name="TIME", format="D", unit="s", array=times),
        fits.Column(name="RATE", format="D", unit="count/s", array=czt),
    ], name="CZT_TOTAL")
    for h in (e1, e2):
        h.header["DATE-OBS"] = day.strftime("%Y-%m-%dT00:00:00")
    prim = fits.PrimaryHDU()
    prim.header["DATE-OBS"] = day.strftime("%Y-%m-%dT00:00:00")
    buf = io.BytesIO()
    fits.HDUList([prim, e1, e2]).writeto(buf)
    return buf.getvalue()


def make_day(seed: int, n_s: int, flares: list) -> dict:
    """One day of Neupert-consistent streams. Returns arrays + truth rows."""
    rng = np.random.default_rng(seed)
    soft = 900.0 + np.abs(rng.normal(0, 10, n_s))
    hard = 45.0 + np.abs(rng.normal(0, 2.0, n_s))
    truth = []
    for k, (start, rise, decay, amp) in enumerate(flares):
        peak_t = start + rise // 2
        cls = ("X" if amp > 4000 else "M" if amp > 1500 else
               "C" if amp > 700 else "B")
        truth.append({"peak_sec": peak_t, "class": cls})
        for i in range(start, min(start + rise + decay, n_s)):
            t = i - start
            if 0 <= t < rise:
                soft[i] += amp * float(np.interp(t, [0, rise], [0.15, 1.0]))
                hard[i] += amp * 0.19 * float(
                    np.exp(-((t - rise * .5) ** 2) / (2 * (rise / 4) ** 2)))
            elif t >= rise:
                soft[i] += amp * float(np.exp(-(t - rise) / (decay / 3)))
                hard[i] += amp * .19 * .15 * float(np.exp(-(t - rise) / 40))
    return {"soft": soft, "hard": hard, "truth": truth}


def main(days: int = 2, start_yyyymmdd: str = "20240515") -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    d0 = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    all_truth = []

    for d in range(days):
        day = d0 + timedelta(days=d)
        ymd = day.strftime("%Y%m%d")
        n_s = 86400

        # schedule: one B, one C, one M per day at staggered times
        flares = [(3600 * (2 + d), 60, 300, 500),
                  (3600 * (8 + d), 90, 600, 1200),
                  (3600 * (17 - d % 3), 120, 900, 2600)]
        dat = make_day(100 + d, n_s, flares)
        for tr in dat["truth"]:
            all_truth.append({"date": ymd, **tr})

        # ---- SoLEXS zip (SDD2 primary + SDD1 low-rate variant) ----
        sdd2 = _solexs_fits_bytes(day, np.arange(n_s, dtype=float), dat["soft"])
        sdd1_counts = dat["soft"] * 0.02 + np.abs(
            np.random.default_rng(d).normal(0, 4, n_s))
        sdd1 = _solexs_fits_bytes(day, np.arange(n_s, dtype=float), sdd1_counts)
        zpath = RAW / f"AL1_SLX_L1_{ymd}_v1.0.zip"
        root = f"AL1_SLX_L1_{ymd}_v1.0"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{root}/SDD2/AL1_SOLEXS_{ymd}_SDD2_L1.lc.gz",
                       gzip.compress(sdd2))
            z.writestr(f"{root}/SDD1/AL1_SOLEXS_{ymd}_SDD1_L1.lc.gz",
                       gzip.compress(sdd1))
        print(f"wrote {zpath.name}  ({zpath.stat().st_size//1024} KB)")

        # ---- HEL1OS zip ----
        hfits = _hel1os_fits_bytes(day,
                                   np.arange(n_s, dtype=float),
                                   dat["hard"], dat["hard"] * 0.6)
        hpath = RAW / f"AL1_HLD_L1_{ymd}_v1.0.zip"
        hroot = f"AL1_HLD_L1_{ymd}_v1.0"
        with zipfile.ZipFile(hpath, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{hroot}/data/HEL1OS_L1_{ymd}_lc.fits.gz",
                       gzip.compress(hfits))
        print(f"wrote {hpath.name}")

    truth_path = RAW / "truth_mock.json"
    truth_path.write_text(json.dumps(all_truth, indent=1))
    print(f"wrote {truth_path.name} ({len(all_truth)} events)")


if __name__ == "__main__":
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 2
    start = sys.argv[sys.argv.index("--start") + 1] if "--start" in sys.argv else "20240515"
    main(days, start)
