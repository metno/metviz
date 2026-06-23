# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MetViz visualizes CF-compliant meteorological data served over OPeNDAP (and OGC
WMS/CSW services). It renders timeSeries / profile / timeSeriesProfile and
trajectory datasets, and lets users export time-sliced/resampled subsets as
NetCDF/CSV/Parquet via time-limited download links.

## Commands

Tests (offline by default — network/live-OPeNDAP tests are deselected via the
`network` marker in `pytest.ini`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/pytest                              # all offline tests
.venv/bin/pytest tests/test_dataprep.py       # one file
.venv/bin/pytest tests/test_dataprep.py::test_is_monotonic_increasing  # one test
.venv/bin/pytest -m network                   # only the live-endpoint tests
```

Lint: `ruff check .` (config in `ruff.toml`; `E501`/`B008` ignored, `E402`
allowed in the directory-app `main.py` files that bootstrap `sys.path` before
importing).

Run the full stack locally: `docker compose up --build` (see Services below).

## Architecture

Two cooperating runtimes, plus Redis. They share the `common` package and a
`DOWNLOAD_SIGNING_KEY` so download tokens verify across process boundaries.

- **`ncview`** (port 7000) — `panel serve` of four *directory apps*:
  `metviz/TSP` (timeSeries/profile/timeSeriesProfile plots), `metviz/trj`
  (trajectory), `metviz/catalog` (dataset picker), `metviz/OGC_client` (WMS/CSW
  map demo, legacy/pending refactor). The serve command lives in
  `docker/entrypoint.sh`.
- **`ncapp`** (port 8000) — FastAPI "METAPI" (`ncapp/app/main.py`). Does **not**
  render plots; it returns Bokeh `server_document` embed scripts pointing at the
  Panel backends, and hosts the async download API (`ncapp/app/download_api.py`).
- **`worker`** — Celery worker (+embedded beat) running the export task and a
  periodic sweeper that deletes expired download files (`ncapp/app/worker.py`).
- **`redis`** — Celery broker/result backend + per-task download metadata.

### The `common` package is shared by both runtimes

`metviz/common/` is mounted at `/opt/metviz/common` and imported as
`from common... import ...` by the Panel apps **and** by the Celery export
worker. Each app `main.py` (and `conftest.py`) bootstraps `sys.path` to make
`common` importable (`METVIZ_COMMON_ROOT`, default `/opt/metviz`). When changing
a `common` module, remember a regression can break either the GUI or the export.

Critical constraint: **`common/dataprep.py` is the single source of truth for
how a dataset is opened and cleaned**, so a downloaded file reproduces exactly
what was plotted. It deliberately imports only `numpy`/`xarray` (no
`panel`/`holoviews`) so the worker can reuse it without the GUI stack. Anything
Panel-aware (the session cache, feature-type/monotonic summary) lives in the
thin wrapper `common/data.py` (`load_data`). Plotting (`common/plotting.py`) is
pure functions of `(ds, choices)` — no global/UI state; widget wiring lives in
each app's `main.py`.

### Feature-type routing

CF `featureType` decides which app handles a dataset.
`common/urls.py:detect_feature_type` reads it (falling back to `cdm_data_type`),
and `common/routing.py:target_app_for` maps it to `TSP` or `TRJ` (unknown →
`TSP`). The Catalog/OGC apps use this to redirect after dataset selection; the
ncapp `/getFeatureType`/`/metviz` endpoints mirror it server-side. ERDDAP
datasets that expose no coordinates are repaired in
`dataprep.fix_erddap_dataset` (de-prefixes `s.<var>` names) so the variable
names the UI offers match what the export worker selects.

### Download / export pipeline (the tricky part)

1. The TSP/TRJ download panel (`common/data_access.py`) assembles an export spec
   and POSTs it via `common/download.py:get_download_link` to
   `POST /process_data`.
2. `download_api.py` signs a random filename with `itsdangerous.TimestampSigner`
   into a **download token**, enqueues the Celery `process_data` task (writing to
   that exact filename), and returns the token.
3. `worker.process_data` re-opens the source with `dataprep.open_decoded`
   (same path as the plot), subsets variables, masks `FILL_VALUE` (9.96921e36) →
   NaN, time-slices, optionally resamples, and writes NetCDF/CSV/Parquet.
4. `GET /results/{token}` serves a landing page with a live countdown;
   `GET /file_results/{token}` returns the bytes. Both re-check the token age
   against `DOWNLOAD_TTL_SECONDS`; expiry raises `SignatureExpired` and deletes
   the file. There is **no static file mount** — an expired link cannot fetch
   the file. The beat sweeper removes files that expire un-downloaded.

Token signing/config is duplicated on both sides intentionally:
`ncapp/app/signing.py` (server) and `common/download.py` (Panel client) must
keep key/dir/filename conventions identical. `DOWNLOAD_SIGNING_KEY` **must be
stable across redeploys** or in-flight links break (`update_service.sh`
persists a generated key in `$HOME/.metviz_download_signing_key`).

### Endpoint vs. browser URLs

In `docker-compose.yml`, `PROCESSING_ENDPOINT` is called server-side by the
Panel app (internal service address OK), but `DOWNLOAD_ENDPOINT` is put into a
link shown in the user's browser, so it must be browser-reachable (the public
host in production).

## Conventions

- Apps are **directory-served Panel apps**: code at module top level runs at
  import/session time; `sys.path` bootstrap blocks at the top of `main.py` are
  load-bearing (hence the `E402` exemptions).
- Mutating Panel/Bokeh widget state from a background thread must go through
  `doc.add_next_tick_callback` (see the empty-variable scan in `TSP/main.py`).
- Tests use small in-memory xarray datasets (`tests/conftest.py`) as stand-ins
  for real OPeNDAP feature types, so they run offline. Keep new tests offline
  unless they genuinely need a live endpoint (then mark them `network`).
