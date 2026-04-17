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
    # This generates the script tag that tells the browser 
    # to connect to the Panel server
    PANEL_URL = "https://ncmet.wps.met.no/TSP"
    # get PANEL_TSP_URL from environment variable
    PANEL_TSP_URL = os.getenv("PANEL_TSP_URL", "https://ncmet.wps.met.no/TSP")
    script = server_document(url=f"{PANEL_TSP_URL}", arguments={"url": url})
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
    # This generates the script tag that tells the browser 
    # to connect to the Panel server
    PANEL_TRJ_URL = os.getenv("PANEL_TRJ_URL", "https://ncmet.wps.met.no/TRJ")
    script = server_document(url=f"{PANEL_TRJ_URL}", arguments={"url": url})
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
    # This generates the script tag that tells the browser 
    # to connect to the Paneli server
    BOKEH_URL = os.getenv("BOKEH_URL", "https://bokeh.wps.met.no/app")
    script = server_document(url=f"{BOKEH_URL}", arguments={"url": url})
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

    # This generates the script tag that tells the browser 
    # to connect to the Panel server
    if feature_type in ['timeSeries', 'timeSeriesProfile', 'profile']:
        BOKEH_URL = 'https://ncmet.wps.met.no/TSP'
    elif feature_type == 'trajectory':
        BOKEH_URL = 'https://ncmet.wps.met.no/TRJ'
    else:
        return HTMLResponse(content=f"Plotting not implemented yet for featureType: {feature_type}", status_code=422)
    script = server_document(url=f"{BOKEH_URL}", arguments={"url": url})
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
    if feature_type and feature_type.value == 'timeSeries':
        BOKEH_URL = 'https://ncmet.wps.met.no/TSP'
    elif feature_type and feature_type.value == 'trajectory':
        BOKEH_URL = 'https://ncmet.wps.met.no/TRJ'
    else:
        BOKEH_URL = 'https://ncmet.wps.met.no/TSP'
    script = server_document(url=f"{BOKEH_URL}", arguments={"url": url})
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
