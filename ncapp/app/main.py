"""METAPI — a thin FastAPI front-end that embeds the metviz Panel apps.

This service does not render plots itself. For a given OPeNDAP ``url`` it asks
Bokeh for a ``server_document`` script tag pointing at the appropriate Panel
backend (TSP or TRJ), and returns it either as raw HTML (for iframe/Drupal
embedding) or wrapped in a page template.

Backend URLs are supplied via environment variables with no defaults, so a
misconfigured deployment fails loudly (HTTP 503) instead of silently routing to
the wrong server.
"""

import os
import sys

sys.path.append("/app")

import uvicorn
from bokeh.embed import server_document
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import AnyHttpUrl
from starlette.middleware.cors import CORSMiddleware
from utility import FeatureType, FeatureTypeEnum, guess_feature_type_from_data

PANEL_TSP_URL: str = os.environ.get("PANEL_TSP_URL", "")
PANEL_TRJ_URL: str = os.environ.get("PANEL_TRJ_URL", "")

app = FastAPI(
    title="METAPI",
    description="Prototype API to render NetCDF Data [TS, TSP, TRJ] using Panel and Bokeh",
    version="0.0.1",
)
templates = Jinja2Templates(directory="templates")

# Public embedding API: allow any origin. Credentials are intentionally
# disabled — a wildcard origin with credentials is rejected by browsers and is
# not needed here (the embed script connects to the Panel server directly).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _embed_response(panel_url: str, url: str, render: bool, request: Request):
    """Return the embed script for *panel_url*, raw or wrapped in the template."""
    if not panel_url:
        raise HTTPException(status_code=503, detail="Panel URL environment variable is not set")
    script = server_document(url=panel_url, arguments={"url": url})
    if not render:
        return HTMLResponse(content=script, status_code=200)
    return templates.TemplateResponse("index.html", {"request": request, "script": script})


@app.get("/TSP")
async def tsp(url: str, request: Request, render: bool = False):
    """Embed the TSP (timeSeries / profile / timeSeriesProfile) Panel app."""
    return _embed_response(PANEL_TSP_URL, url, render, request)


@app.get("/TRJ")
async def trj(url: str, request: Request, render: bool = False):
    """Embed the trajectory Panel app."""
    return _embed_response(PANEL_TRJ_URL, url, render, request)


@app.get("/bokehplot")
async def bokehplot(
    feature_type: FeatureTypeEnum,
    request: Request,
    render: bool = False,
    url: AnyHttpUrl = Query(..., description="Enter a valid OPeNDAP url"),
):
    """Embed the Panel app matching an explicitly-supplied featureType."""
    if feature_type in (
        FeatureTypeEnum.TIMESERIES,
        FeatureTypeEnum.TIMESERIESPROFILE,
        FeatureTypeEnum.PROFILE,
    ):
        panel_url = PANEL_TSP_URL
    elif feature_type == FeatureTypeEnum.TRAJECTORY:
        panel_url = PANEL_TRJ_URL
    else:
        return HTMLResponse(
            content=f"Plotting not implemented yet for featureType: {feature_type}",
            status_code=422,
        )
    return _embed_response(panel_url, str(url), render, request)


@app.get("/getFeatureType")
async def get_feature_type(url: AnyHttpUrl = Query(..., description="Enter a valid OPeNDAP url")):
    """Return the CF ``featureType`` advertised by the dataset at *url*."""
    try:
        return {"feature_type": guess_feature_type_from_data(url)}
    except ValueError as exc:
        return HTMLResponse(status_code=423, content=str(exc))


@app.get("/metviz")
async def metviz(
    url: str,
    request: Request,
    feature_type: str,
    guess_featuretype: bool,
    render: bool = False,
):
    """Embed a Panel app, optionally guessing the featureType from the data.

    When ``guess_featuretype`` is false, ``feature_type`` is validated against
    the allowed set; trajectory data routes to the TRJ app, everything else to
    the TSP app.
    """
    resolved_type = None
    if not guess_featuretype:
        try:
            resolved_type = FeatureType(value=feature_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if resolved_type is not None and resolved_type.value == FeatureTypeEnum.TRAJECTORY:
        panel_url = PANEL_TRJ_URL
    else:
        panel_url = PANEL_TSP_URL
    return _embed_response(panel_url, url, render, request)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
