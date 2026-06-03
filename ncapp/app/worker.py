"""Celery worker: the async NetCDF/xarray export task and the cleanup sweeper.

``process_data`` opens the source dataset over OPeNDAP, slices the requested
variables (and time range, when the data has a decoded time axis), optionally
resamples, and writes the result to the download directory as NetCDF / CSV /
Parquet. The filename it writes to is the one signed by ``/process_data``, so
the timestamped token already points at the eventual file.

``sweep_expired_downloads`` is a Celery-beat periodic task that deletes files
older than the TTL, so links that expire without ever being downloaded do not
linger on disk.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import redis
import xarray as xr
from celery import Celery
from celery.utils.log import get_task_logger
from signing import DOWNLOAD_TTL_SECONDS, download_dir

logger = get_task_logger(__name__)

celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

# Used to record per-task download metadata ({download_token, filename, status}).
redis_client = redis.Redis.from_url(celery.conf.broker_url)

# How often the sweeper runs (seconds). Default: every TTL/2, min 60s.
SWEEP_INTERVAL_SECONDS = int(
    os.environ.get("SWEEP_INTERVAL_SECONDS", str(max(60, DOWNLOAD_TTL_SECONDS // 2)))
)

# UI label -> pandas offset alias (mirrors common.utility.pandas_frequency_offsets).
PANDAS_FREQUENCY_OFFSETS = {
    "Hourly": "h",
    "Calendar day": "D",
    "Weekly": "W",
    "Month end": "ME",
    "Quarter end": "QE",
    "Yearly": "YE",
}

# Common NetCDF sentinel fill value that should be treated as missing.
_FILL_VALUE = 9.96921e36


@celery.on_after_configure.connect
def _register_periodic_tasks(sender, **_kwargs):
    """Schedule the cleanup sweeper when the worker (with beat) starts."""
    sender.add_periodic_task(
        SWEEP_INTERVAL_SECONDS,
        sweep_expired_downloads.s(),
        name="sweep expired downloads",
    )


@celery.task(name="process_data")
def process_data(config: dict) -> bool:
    """Subset the dataset described by *config* and write the export file.

    *config* is a ``DatasetConfig`` dict augmented by the API with ``filename``
    and ``download_token``.
    """
    out_dir = download_dir()
    filename = config["filename"]
    file_path = out_dir / filename
    output_format = (config.get("output_format") or "nc").lower()
    variables = config.get("variables") or None

    logger.info("processing %s -> %s (%s)", config.get("url"), filename, output_format)

    ds = xr.open_dataset(config["url"], decode_times=config.get("decoded_time", True))

    # Select requested variables (fall back to the whole dataset).
    subset = ds[variables] if variables else ds

    # Time-slice only when we have a decoded datetime coordinate and a range.
    time_coords = [c for c in subset.coords if subset.coords.dtypes[c] == np.dtype("<M8[ns]")]
    time_range = config.get("time_range") or []
    if time_coords and len(time_range) == 2:
        selections = {tc: slice(time_range[0], time_range[1]) for tc in time_coords}
        subset = subset.sel(selections)

    # Optional resampling on the (first) time coordinate.
    if config.get("is_resampled") and time_coords:
        freq = PANDAS_FREQUENCY_OFFSETS.get(config.get("resampling_frequency", ""))
        if freq:
            subset = subset.where(subset != _FILL_VALUE).resample({time_coords[0]: freq}).mean()

    _write(subset, file_path, output_format)

    _record_status(process_data.request.id, config, status="SUCCESS")
    logger.info("completed %s", filename)
    return True


def _write(ds: xr.Dataset, file_path: Path, output_format: str) -> None:
    """Write *ds* to *file_path* in the requested format."""
    if output_format == "csv":
        ds.to_dataframe().to_csv(file_path)
    elif output_format in ("pq", "parquet"):
        ds.to_dataframe().to_parquet(file_path)
    else:  # NetCDF (default)
        try:
            ds.to_netcdf(file_path)
        except ValueError:
            # Some datasets need an explicit fill value to serialise.
            encoding = {v: {"_FillValue": np.nan} for v in ds.data_vars}
            ds.to_netcdf(file_path, encoding=encoding)


def _record_status(task_id: str, config: dict, status: str) -> None:
    """Store download metadata in Redis, keyed by task id."""
    redis_client.set(
        task_id,
        json.dumps(
            {
                "download_token": config.get("download_token"),
                "filename": config.get("filename"),
                "status": status,
            }
        ),
    )


@celery.task(name="sweep_expired_downloads")
def sweep_expired_downloads() -> int:
    """Delete files older than the TTL; return how many were removed."""
    out_dir = download_dir()
    now = time.time()
    removed = 0
    for entry in out_dir.iterdir():
        if not entry.is_file():
            continue
        try:
            if now - entry.stat().st_mtime > DOWNLOAD_TTL_SECONDS:
                entry.unlink()
                removed += 1
        except OSError as exc:  # pragma: no cover - filesystem race
            logger.warning("could not remove %s: %s", entry, exc)
    if removed:
        logger.info("sweeper removed %d expired download(s)", removed)
    return removed
