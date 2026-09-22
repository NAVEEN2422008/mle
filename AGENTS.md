# AGENTS.md

Aditya-L1 Solar Flare Early Warning & Nowcasting System (`aditya-flarecast`).
FastAPI + PyTorch space-weather nowcasting platform replaying real ISRO Aditya-L1
SoLEXS/HEL1OS FITS archives. Single package, no monorepo.

## Commands

- Run tests: `python -m pytest tests/ -q` — 31 tests, self-contained (TestClient, no server/network needed)
- Start server: `python run_server.py --port 8000` → http://127.0.0.1:8000/
- Reproducible research pipeline: `python scripts/run_reproducible_pipeline.py`
- Train deep models: `python scripts/train_deep_models.py`
- Verify real data + models: `python scripts/verify_real_system.py`

## Critical: pyarrow DLL block (this machine)

Windows Application Control policy blocks the `pyarrow._compute` DLL. pandas 3.x
imports `pyarrow.compute` at module load, so ANY pandas import crashes with
`ImportError: DLL load failed ... Application Control policy has blocked this file`.

- `conftest.py` (repo root) and `run_server.py` install a Python-level `pyarrow.compute`
  stub BEFORE pandas import and set `pd.options.future.infer_string = False`.
- NEVER start the server with `python -m uvicorn src.api.main:app` or
  `python -m src.api.main` — both crash. Always use `python run_server.py`.
- `sitecustomize.py` in the repo root is DEAD CODE (sitecustomize only loads from
  site-packages, not CWD). Do not rely on it; candidate for deletion.
- The stub is a no-op fallback: real pyarrow compute kernels are unavailable.
  Do not add code that calls `pyarrow.compute.*` functions.

## Architecture

Pipeline: `ingest → preprocess(fusion) → nowcast(detectors) → catalog(master) → forecast → api → dashboard`

- `src/api/main.py` — FastAPI app (single file, ~1100 lines). `LiveEngine` background
  thread replays FITS data; `Broadcaster` fans out SSE. Dashboard served from
  `dashboard/index.html` (single-file, zero-dependency vanilla JS).
- Dashboard URL is root `/`. `/dashboard` 404s without trailing slash; `/dashboard/` works.
- Dashboard connects via WebSocket `/api/ws` first, falls back to SSE `/api/stream`.
- `src/ingest/solexs_reader.py` — `arbitrate_sdd_rows()` implements SDD1/SDD2 switching
  (SDD1 saturates above ~1e5 cps; never read SDD1 turnover as a flux dip).
- `src/forecast/deep_models.py` — SpatioTemporalGraphTransformer + BinaryFocalLoss + Neupert PINN.
- `src/forecast/metrics.py` — TSS/HSS/BSS/POD/FAR per arXiv:2511.20465 conventions.

## Data & models

- `data/raw/` — 54 real FITS ZIP archives: `AL1_SLX_L1_*.zip` (SoLEXS), `AL1_HLD_L1_*.zip` (HEL1OS).
- `data/processed/` — parquet/csv.gz (gitignored); `data/master_flare_catalog.db` — SQLite catalogue.
- `models/spatiotemporal_graph_transformer.pt` — real trained checkpoint (887,917 bytes,
  78 layers, learned α=0.008074237, β=0.002625430).
- `models/cnn_lstm_solar.pt` — 820,229 bytes.

## API routes

`/api/health`, `/api/model/info`, `/api/model/load`, `/api/inference` (POST),
`/api/forecast`, `/api/alert/active`, `/api/statistics`, `/api/catalogue`,
`/api/speed` (GET/POST), `/api/source` (GET/POST), `/api/stream` (SSE), `/api/ws` (WebSocket).

Source modes (`/api/source?mode=`): `g5_superstorm` (default), `may_2024`, `x87`,
`oct_x9`, `october_2024`, `x90`, `unseen_test`, `holdout`, `august_2026`.

## Honesty conventions (do not regress)

- The README integrity note is load-bearing: "+0.990 / POD 100%" figures were
  benchmark-demo values NOT reproducible from training code. The verified TSS is
  **+0.218** (live NOAA stream 2026-09-15→22, 9,973 samples, 33 events, θ=0.275)
  and **+0.296** (GOES validation window, θ=0.5). The value 0.282 matches NO run —
  it was hardcoded in the API layer and has been removed. Never re-add inflated
  metrics; the PINN ST-GT "+0.990" row was removed because no checkpoint
  artifact reproduces it.
- TSS is THE primary metric; accuracy/ROC-AUC are banned from reports (PLAN.md).
- Dashboard must label data provenance honestly: "REPLAY"/"FITS" badges, latency
  disclosure banner (24–48h), and `"synthetic": true` on attention-node weights
  (visualization weights are illustrative, not model attention).
- `SCALE_FACTORS` in `src/api/main.py` are empirical cross-calibration values
  (Sarwade et al. 2025), NOT universal physical constants.

## Gotchas

- Dockerfile healthcheck hits `/health` but the app only exposes `/api/health` → healthcheck always fails. Docker CMD `uvicorn src.api.main:app` is fine on Linux (no policy block).
- `PROJECT_REPORT.md` is another agent's untracked file — leave it uncommitted.
- pyproject.toml: pytest `pythonpath=["."]`, testpaths `["tests"]`; ruff line-length 88, target py39.
- Only Python 3.14.6 on this machine (C:\Python314), no conda/venv. pandas 3.0.3, pyarrow 25.0.1, PyTorch 2.11.0+cu128.