# Timestamped download + async export pipeline (ncapp)

Ported from `metno/ncmet` (the `ncprocess` service) into the metviz `ncapp`
FastAPI service. This is the **server side** of a contract the Panel TSP app
already speaks via `metviz/common/download.py`.

> **Context for the next session:** this was built by isolating the download API
> + Celery async export pipeline from `ncmet` and grafting it onto the
> `codereview-refactor` branch. Branch: `feat/download-export-pipeline`. The
> intent is to run it on the machine where `ncapp`/`ncview` actually run.

## What it does

A user selects variables/time/format in the TSP Panel app → the app POSTs an
export spec to the API → the API signs a random filename with a **timestamp**
and enqueues a Celery job → the worker writes the subset file → the user gets a
**time-limited** download link. After the TTL the signature no longer verifies
(link refused, file deleted) and a background sweeper removes anything that
expired without being fetched.

## The contract (fixed by the existing Panel client)

`metviz/common/download.py:get_download_link()` POSTs to
`{PROCESSING_ENDPOINT}/process_data` and builds `{DOWNLOAD_ENDPOINT}/results/{token}`.
`metviz/TSP/main.py:export_selection()` produces the spec. So the endpoints are:

| Method & path | Purpose |
|---|---|
| `POST /process_data` | Accept the export spec, sign a filename, enqueue the job, return `{task_id, download_token, filename, task_status}`. |
| `GET /results/{download_token}` | Landing page (`download.html`) with a live countdown + a link to the file; or `expired.html` once the token is too old. |
| `GET /file_results/{download_token}` | The actual bytes (`FileResponse`), refused + deleted once expired. **No static mount** — expiry is always enforced. |

Export spec (`DatasetConfig` in `ncapp/app/models.py`):
```json
{
  "url": "https://.../dataset.nc",
  "variables": ["ta", "hur"],
  "decoded_time": true,
  "time_range": ["2018-07-01T00:00:00", "2018-09-30T23:59:00"],
  "is_resampled": false,
  "resampling_frequency": "raw",
  "output_format": "nc"
}
```
`output_format` ∈ `nc` | `csv` | `pq`.

## Files added

```
ncapp/app/signing.py        # signer + config: key, TTL, download dir, token helpers
ncapp/app/models.py         # DatasetConfig + TaskResponse (pydantic v2)
ncapp/app/worker.py         # Celery app, process_data task, sweep_expired_downloads (beat)
ncapp/app/download_api.py   # FastAPI router: /process_data, /results, /file_results
ncapp/app/templates/download.html   # landing page + JS countdown
ncapp/app/templates/expired.html
ncapp/app/templates/error.html
tests/test_download_api.py  # offline tests (signing/expiry, sweeper, /process_data)
```
Edited: `ncapp/app/main.py` (include router + lifespan dir-create),
`ncapp/requirements.txt`, `requirements-test.txt`, `docker-compose.yml`.

## How expiry works

`itsdangerous.TimestampSigner(DOWNLOAD_SIGNING_KEY)` signs the filename; the
signature embeds the issue time. Every `/results` and `/file_results` access
calls `unsign(token, max_age=DOWNLOAD_TTL_SECONDS)`:
- valid → serve;
- `SignatureExpired` → delete the file, show the expired page;
- `BadSignature` → show the error page.

`sweep_expired_downloads` (Celery-beat periodic task) deletes files older than
the TTL so links nobody clicks don't linger. Interval =
`SWEEP_INTERVAL_SECONDS` (default `max(60, TTL/2)`).

## Configuration (environment variables)

| Var | Used by | Notes |
|---|---|---|
| `DOWNLOAD_SIGNING_KEY` | ncapp, worker, ncview | **Must be identical across all three.** Set a real secret in prod. |
| `TSPLOT_DOWNLOAD` | ncapp, worker | Shared download directory (same volume for both). |
| `DOWNLOAD_TTL_SECONDS` | ncapp, worker | Link lifetime (default 600). |
| `SWEEP_INTERVAL_SECONDS` | worker | Sweeper cadence (optional). |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | ncapp, worker | Redis URL. |
| `PROCESSING_ENDPOINT` | ncview (Panel) | Server-side call → can be internal, e.g. `http://ncapp:8000`. |
| `DOWNLOAD_ENDPOINT` | ncview (Panel) | Put in a link shown in the **browser** → must be browser-reachable (public host in prod). |

## Run it (docker compose)

```bash
docker compose up --build ncapp worker redis
# Panel UI:
docker compose up --build ncview
```
`docker-compose.yml` defines `ncapp` (uvicorn :8000), `worker` (celery worker
`--beat`), `redis`, and a shared `download-data` volume.

Quick manual check:
```bash
curl -s -X POST localhost:8000/process_data \
  -H 'content-type: application/json' \
  -d '{"url":"<OPeNDAP url>","variables":["ta"],"output_format":"csv"}'
# -> {"task_id":...,"download_token":"<tok>",...}
# then open  http://localhost:8000/results/<tok>
```

## Tests

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest tests/test_download_api.py -q
```
Offline (no broker/Redis/network): token round-trip, expiry, tamper detection,
sweeper deletion, and `POST /process_data` (Celery/Redis mocked). All green.

## Deliberate improvements over the ncmet original

- Signing key from `DOWNLOAD_SIGNING_KEY` env (was hardcoded `'secret-key'`).
- TTL from `DOWNLOAD_TTL_SECONDS` (was hardcoded `600`).
- File served **only** through the signed endpoint (the ncmet static `/download`
  mount silently bypassed expiry — the original template even warned about it).
- Real background sweeper (ncmet only deleted lazily on an expired hit).
- Parquet output added to match the TSP export options.

## Open items / next-session candidates

- **Wire the worker's Redis status into `/results`** (optional): currently
  `/results` only checks the token; it does not block until the Celery job
  finishes. If the user opens the link before the file is written,
  `/file_results` returns the "still processing" error page. Consider a task
  -status check (the worker already records `{download_token, filename, status}`
  in Redis by task id) or a small poll on the landing page.
- **Secrets**: replace `change-me-in-production` in `docker-compose.yml`.
- **`ncapp/Dockerfile`** is `FROM epinux/ncprocess` and does not COPY the app
  (it is volume-mounted in compose). Confirm that base image still exists / has
  the heavy deps (xarray, netcdf4); otherwise switch to a `python:3.13` base and
  rely on `ncapp/requirements.txt`.
- **CORS / auth**: the API is open (matches the embedding design). Add auth if
  downloads must be restricted.
