"""Pydantic models for the async download/export pipeline.

``DatasetConfig`` is the export specification sent by the Panel TSP app
(``metviz/common/download.py:get_download_link`` POSTs it to ``/process_data``).
``TaskResponse`` is what ``/process_data`` returns: enough for the client to
build a ``/results/{download_token}`` link.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DatasetConfig(BaseModel):
    """Export selection produced by the TSP download widget."""

    url: str = Field("", description="OPeNDAP URL of the source dataset")
    variables: list[str] = Field(default_factory=list, description="Variables to export")
    decoded_time: bool = Field(True, description="Whether the dataset's time axis decodes")
    time_range: list[datetime] = Field(default_factory=list, description="[start, end] time slice")
    is_resampled: bool = Field(False, description="Whether to resample before export")
    resampling_frequency: str = Field("raw", description="Pandas resampling frequency label")
    output_format: str = Field("nc", description="Output format: nc | csv | pq")

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://thredds.met.no/thredds/dodsC/alertness/YOPP_supersite/obs/utqiagvik/utqiagvik_obs_timeSeriesProfileSonde_20180201_20180331.nc",
                "variables": ["ta", "hur", "wdir_refmt"],
                "decoded_time": True,
                "time_range": ["2018-07-01T00:00:00", "2018-09-30T23:59:00"],
                "is_resampled": False,
                "resampling_frequency": "raw",
                "output_format": "nc",
            }
        }
    }


class TaskResponse(BaseModel):
    """Result of enqueuing an export job."""

    task_id: str
    download_token: str
    filename: str
    task_status: str
