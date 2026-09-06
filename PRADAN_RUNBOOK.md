# PRADAN DAY RUNBOOK — Aditya-L1 Real-Data Ingest

Goal: go from "I have a PRADAN account" to flare catalogue + forecast numbers
on genuine SoLEXS/HEL1OS Level-1 telemetry in under an hour.

---

## 0. One-time setup (~5 min)

```powershell
cd "C:\Users\Naveen S\OneDrive\Documents\mle\solar-flare-system"
python -m pip install -r requirements.txt        # astropy pyarrow lightgbm fastapi uvicorn ...
```

Register (free): https://pradan1.issdc.gov.in/al1/  → "Register" → email OTP.
Login once in the browser to confirm access to the AL1 section.

## 1. Download the data

**Route A - interactive downloader (primary, verified against live portal):**
Open your OWN PowerShell (not this chat) and run:
```powershell
cd "C:\Users\Naveen S\OneDrive\Documents\mle\solar-flare-system"
python scripts\download_pradan.py
```
- Prompts: username/email, then password (hidden input - never stored or displayed)
- Range prompt: press Enter for last ~14 days, or type `20240515:20240615`
- Instruments: Enter = both SoLEXS + HEL1OS
- Zips land directly in `data\raw\`

Auth flow used (verified 2026-08): PRADAN -> Keycloak (idp.issdc.gov.in,
realm issdc) -> session cookies; script parses the dynamic form action.

**Route B - browser fallback:** pradan1.issdc.gov.in/al1 -> Browse Data ->
SLX/HLD sections -> **Bulk Download** -> drop `AL1_*_L1_*.zip` into `data\raw\`.

> ⚠️ Remove mock files first if present:
> `Remove-Item data\raw\AL1_*_L1_*.zip, data\raw\truth_mock.json`

## 2. Run the stack (one command)

```powershell
python scripts\run_pradan.py --raw data/raw
```

What you'll see: scan counts → rows read after SDD arbitration & band collapse →
fused stream size → **flare catalogue CSV** at `data\processed\flare_catalogue.csv`
→ forecast CV vs climatology/persistence → truth validation (mock mode only).

Cadence note: SoLEXS native = 1 s; HEL1OS L1 LC = 1 s. If you also grabbed GOES
for cross-checks, the real-data suite (`tests/test_realdata_goes.py`) handles its
1-min cadence separately — no mixing required.

## 3. Data-volume guidance (from dress rehearsal)

| Days of data | Detection catalogue | Forecast CV |
|---|---|---|
| 1-3 | works immediately | SKIPPED (<10 independent episodes) |
| ~7 | better sensitivity tuning possible | borderline |
| ≥14 (≈30+ flares) | solid | full TSS/HSS/BSS + lead-time report |

The runner prints this guidance automatically when it skips training.

## 4. Sanity checklist on first REAL run

- [ ] `[read]` row counts ≈ 86,400 × days (SoLEXS) — large drops ⇒ gaps/GTIs (fine)
- [ ] No `date-src=FALLBACK(unknown)` in provenance (means header+filename lacked date)
- [ ] Catalogue peaks visually match obvious bumps: open
      `data/processed/fused.parquet` in a quick matplotlib plot vs `flare_catalogue.csv`
- [ ] Cross-check a few catalogue peaks against the official GOES/SWPC event list
      (same timestamps ±1 min expected — Sun-as-a-star instruments agree well)

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No usable TIME+counts table` | unusual FITS layout | send me the member listing: `python -c "from astropy.io import fits; print(fits.info('FILE'))"` |
| All events on one date | missing DATE-OBS & nonstandard name | keep original PRADAN filenames |
| Detector deaf / too many events | threshold mismatch to real background | tune `--` (edit `det_h_c_sigma` in scripts/run_pradan.py; start 8-15) |
| Forecast skipped | not enough episodes yet | download more days |

---
*Mock rehearsal evidence: see research_report.md Appendix 5.*
