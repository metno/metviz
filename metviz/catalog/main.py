"""Search Catalog — entry point for choosing a dataset to visualize.

For now it presents a table of example OPeNDAP URLs plus a free-text URL box.
On submit it detects the dataset's CF ``featureType`` and redirects to the
matching visualization app (``/TSP`` or ``/TRJ``).

This is the seed for a fuller catalogue search built on the OGC CSW standard:
the static example table will be augmented/replaced by live CSW query results.

Served as a Panel directory app (``panel serve /Catalog``).

Copyright 2022 MET Norway. Licensed under the Apache License, Version 2.0.
"""

from __future__ import annotations

import os
import sys

# The shared `common` package is mounted at /opt/metviz/common in the container.
# Ensure its parent directory is importable regardless of how PYTHONPATH is set
# (mirrors ncapp's sys.path bootstrap). Override with METVIZ_COMMON_ROOT if the
# deployment mounts it elsewhere.
_COMMON_ROOT = os.environ.get("METVIZ_COMMON_ROOT", "/opt/metviz")
if _COMMON_ROOT not in sys.path:
    sys.path.insert(0, _COMMON_ROOT)

import pandas as pd
import panel as pn
from common.data import load_data
from common.logging_utils import create_logger
from common.redirect import Redirector

pn.extension(sizing_mode="stretch_width")

logger = create_logger(__name__)

# Example datasets, grouped by featureType, offered until CSW search lands.
EXAMPLE_RESOURCES = {
    "Time Series 1": "https://thredds.met.no/thredds/dodsC/arcticdata/infranor/UiO-Kongsvegen-AWS/UiO-Kongsvegen-AWS-sw200-agg.ncml",
    "Time Series 2": "https://thredds.met.no/thredds/dodsC/arcticdata/obsSynop/01008",
    "Profile 1": "https://opendap1.nodc.no/thredds/dodsC/chemistry/StationM/StationM_2008_2019_v2.nc",
    "Profile 2": "https://opendap1.nodc.no/thredds/dodsC/chemistry/StationM/StationM_2008_2019_v1.nc",
    "Time Series Profile 1": "https://thredds.met.no/thredds/dodsC/arcticdata/frost2netcdf-permafrost/SN99868/SN99868-aggregated.ncml",
    "Time Series Profile 2": "https://thredds.met.no/thredds/dodsC/arcticdata/met.no/obs-temp/obs-temp_20892.nc",
    "Trajectory 1": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc",
    "Trajectory 2": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/SIMBA/simba-510_air-temperature2022.nc",
}

# Which visualization app handles each detected featureType.
FEATURE_TYPE_APP = {"timeseries": "TSP", "trajectory": "TRJ", "profile": "TSP"}


def target_app(feature_type: str | None) -> str:
    """Map a detected featureType to the visualization app that handles it.

    Unknown / undetected types fall back to TSP, which covers the common
    1-D feature types.
    """
    return FEATURE_TYPE_APP.get(feature_type, "TSP")


redirector = Redirector()
resources_df = pd.DataFrame.from_dict(EXAMPLE_RESOURCES, orient="index", columns=["URL"])
resources_table = pn.widgets.DataFrame(resources_df, name="Example URLs")
url_input = pn.widgets.TextInput(name="Data URL", placeholder="Enter data URL...", width=600)
add_button = pn.widgets.Button(name="Add URL", button_type="primary")
url_button = pn.widgets.Button(name="Load Data", button_type="primary")


def add_url(event) -> None:
    """Copy the selected example URL into the input box."""
    selected = resources_table.selection
    if selected:
        url_input.value = resources_df.iloc[selected[0]]["URL"]


add_button.on_click(add_url)


@pn.depends(url_button.param.clicks, watch=True)
def load_data_button(clicks) -> None:
    """Detect the featureType of the entered URL and redirect to its app."""
    url = url_input.value
    if not url:
        return
    _, _, _, _, feature_type = load_data(url)
    logger.info(f"FeatureType detected: {feature_type}")
    redirector.redirect(f"/{target_app(feature_type)}?url={url}")


pn.Column(
    redirector,
    url_input,
    url_button,
    resources_table,
    add_button,
    sizing_mode="stretch_height",
).servable()
