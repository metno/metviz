import logging
import sys
sys.path.append('/app')
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.cors import CORSMiddleware

import os
from fastapi.templating import Jinja2Templates
from bokeh.embed import server_document
from utility import URLStr, FeatureType, FeatureTypeEnum, guess_feature_type_from_data
from pydantic import AnyHttpUrl

# Panel / Bokeh backend URLs — must be set via environment variables.
# No defaults are provided so a misconfigured deployment fails loudly at
# request time rather than silently routing to the wrong server.
PANEL_TSP_URL: str = os.environ.get("PANEL_TSP_URL", "")
PANEL_TRJ_URL: str = os.environ.get("PANEL_TRJ_URL", "")
BOKEH_URL: str = os.environ.get("BOKEH_URL", "")

app = FastAPI(
    title="METAPI",
    description="Prototype API to render NetCDF Data [TS, TSP, TRJ] using Panel and Bokeh",
    version="0.0.1",
)
templates = Jinja2Templates(directory="templates")




app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# take a url parameter as input
@app.get("/TSP")
async def tsp(url: str, render: bool, request: Request):
    if not PANEL_TSP_URL:
        raise HTTPException(status_code=503, detail="PANEL_TSP_URL environment variable is not set")
    script = server_document(url=PANEL_TSP_URL, arguments={"url": url})
    # return as htmlresponse
    if not render:
        return HTMLResponse(content=script, status_code=200)
    else:
        # return as template response
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "script": script}
        )

@app.get("/TRJ")
async def trj(url: str, render: bool, request: Request):
    if not PANEL_TRJ_URL:
        raise HTTPException(status_code=503, detail="PANEL_TRJ_URL environment variable is not set")
    script = server_document(url=PANEL_TRJ_URL, arguments={"url": url})
    # return as htmlresponse
    if not render:
        return HTMLResponse(content=script, status_code=200)
    else:
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "script": script}
        )
    
@app.get("/bokehapp")
async def bokeh(url: str, render: bool, request: Request):
    if not BOKEH_URL:
        raise HTTPException(status_code=503, detail="BOKEH_URL environment variable is not set")
    script = server_document(url=BOKEH_URL, arguments={"url": url})
    # return as htmlresponse
    if not render:
        return HTMLResponse(content=script, status_code=200)
    else:
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "script": script}
        )
    
@app.get("/bokehplot")
async def bokehplot(feature_type: FeatureTypeEnum, request: Request, render: bool = False, url: AnyHttpUrl = Query(..., description="Enter a valid OPeNDAP url")):

    if feature_type in ['timeSeries', 'timeSeriesProfile', 'profile']:
        panel_url = PANEL_TSP_URL
    elif feature_type == 'trajectory':
        panel_url = PANEL_TRJ_URL
    else:
        return HTMLResponse(content=f"Plotting not implemented yet for featureType: {feature_type}", status_code=422)
    if not panel_url:
        raise HTTPException(status_code=503, detail=f"Panel URL environment variable is not set for featureType: {feature_type}")
    script = server_document(url=panel_url, arguments={"url": url})
    # return as htmlresponse
    if not render:
        return HTMLResponse(content=script, status_code=200)
    else:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "script": script}
        )

    
@app.get("/getFeatureType")
async def getFeatureType(url: AnyHttpUrl = Query(..., description="Enter a valid OPeNDAP url")):
    try:
        feature_type = guess_feature_type_from_data(url)
        return {"feature_type": feature_type} 
    except ValueError as e:
        return HTMLResponse(status_code=423, content=str(e))

    
@app.get("/metviz")
async def metviz(url: str, render: bool, feature_type: str, guess_featuretype: bool, request: Request):
    # This generates the script tag that tells the browser 
    # to connect to the Panel server
    # validate feature_type using pydantic model
    # perform the validation only if guess_featuretype is False, otherwise ignore the feature_type parameter and guess it from the data
    if not guess_featuretype:
        try:
            feature_type = FeatureType(value=feature_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        feature_type = None
    if feature_type and feature_type.value == 'trajectory':
        panel_url = PANEL_TRJ_URL
    else:
        panel_url = PANEL_TSP_URL
    if not panel_url:
        raise HTTPException(status_code=503, detail="Panel URL environment variable is not set")
    script = server_document(url=panel_url, arguments={"url": url})
    # return as htmlresponse
    if not render:
        return HTMLResponse(content=script, status_code=200)
    else:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "script": script}
        )    
    
    
if __name__ == "__main__":
    uvicorn.run(app, port=8000, host="0.0.0.0", reload=True, debug=True)
