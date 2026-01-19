"""
====================

Copyright 2025 MET Norway

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
"""Interactive map demo used by the ADC NC-CF Data Visualization project.

This module builds a simple ipyleaflet map wrapped in a Panel template and
provides UI widgets for:

- Loading WMS layers by providing a GetCapabilities URL.
- Adding draggable markers to the map and editing marker properties.
- Managing removable layers (markers and WMS layers) via a layer manager.

The UI is assembled using Panel and ipyleaflet and expects the following
optional external dependencies at runtime: `owslib`, `ipywidgets`, and
`ipyleaflet`.

This file is intended for exploratory/demo use and is kept small and
imperative; functions are documented with docstrings to aid maintenance.
"""

from turtle import title
from ipywidgets import HTML

from ipyleaflet import Map, Marker, Popup, LayersControl, GeoJSON

import panel as pn
import param
from pydantic import BaseModel, HttpUrl, ValidationError
import xarray as xr 

from ipywidgets import HTML

from ipyleaflet import Map, Marker, Popup, LayersControl, GeoJSON

pn.extension("ipywidgets", sizing_mode="stretch_width")

class URLModel(BaseModel):
    website_url: HttpUrl
    
class Javascript(pn.reactive.ReactiveHTML):
    value = param.String(
        default="",
        allow_None=False,
        doc="""Javascript code. When the value is set it will be evaluated in the browser.
        Afterwards the value will be set to ''""",
    )

    def __init__(self):
        super().__init__(height=0, width=0, margin=0)

    def eval(self, value: str):
        self.value = value

    _template = "<div id='pn-container'></div>"
    _scripts = {
        "value": """
        console.log(data.value)
        
        if (data.value!=''){
            eval(data.value)
            data.value=""
        }"""
    }
    
def valid_url_input(url: str) -> bool:
    """use pydantic to validate URL string input"""
    # Valid usage
    try:
        data = URLModel(website_url=url)
        print(f"Valid URL: {data.website_url}")
        return True
    except ValidationError as e:
        print(f"Validation Error: {e}")
        return False


def url_points_to_xarray(url: str) -> bool:
    """check if the provided url points to a valid xarray dataset"""
    try:
        ds = xr.open_dataset(url)
        ds.close()
        return True
    except Exception as e:
        print(f"Error opening dataset from URL: {e}")
        return False




def build_line_from_xarray(ds: xr.Dataset, var_name: str) -> GeoJSON:
    """build a GeoJSON line from an xarray dataset variable"""
    lons = ds['longitude'].values
    lats = ds['latitude'].values
    coords = [[float(lon), float(lat)] for lon, lat in zip(lons, lats)]
    
    geojson_dict = {
        "type": "Feature",
        "properties": {
            "variable": var_name
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        }
    }
    
    return GeoJSON(data=geojson_dict, name=f"Line for {var_name}")


Resources = {
    "a": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc",
    "b": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/SIMBA/simba-510_air-temperature2022.nc",
    "c": "https://thredds.niva.no/thredds/dodsC/datasets/norsoop/color_fantasy/merged_acdd_color_fantasy.nc",
    "d": "https://thredds.niva.no/thredds/dodsC/datasets/nrt/color_fantasy.nc",
}

if 'url' not in pn.state.session_args:
    javascript = Javascript()
    # add a line editing widget for the url input
    test_urls = Resources['a']
    url_input = pn.widgets.TextInput(
        name="Data URL",
        placeholder="Enter data URL...",
        width=600
    )

    url_button = pn.widgets.Button(name="Load Data", button_type="primary")
    


    # connect the load Data button to append a new entry into the javascript widget
    @pn.depends(url_button.param.clicks, watch=True)
    def load_data_button(clicks):
        url = url_input.value
        code = f"window.location.href='/mapdap?url={url}'"
        javascript.eval(code)
    


    pn.Column(
        # menu_button,
        javascript,
        url_input,
        url_button,
    ).servable()
else:
    print("Loading mapdap with url:", pn.state.session_args['url'])
    url = pn.state.session_args['url']
    url_is_valid = valid_url_input(url[0].decode())
    url_points_to_xarray_flag = url_points_to_xarray(url[0].decode())
    if not url_is_valid:
        div_placeholder = pn.pane.HTML(f"<div> <b>Invalid URL provided:</b> <br> <br> {url[0].decode()} </div>", width=800, height=600)     
        div_placeholder.servable()
    else:
        if url_points_to_xarray_flag:
            # check if the featureType attribute is of type trajectory
            ds = xr.open_dataset(url[0].decode())
            if 'featureType' in ds.attrs:
                if ds.attrs['featureType'].lower() != 'trajectory':
                    div_placeholder = pn.pane.HTML(f"<div> <b>The provided XARRAY dataset is not of featureType 'trajectory':</b> <br> <br> {url[0].decode()} <br> <br> Detected featureType: {ds.attrs['featureType']} </div>")     
                    div_placeholder.servable()
                    ds.close()
                    exit()
                else:
                    if set(['latitude', 'longitude']).issubset(ds.coords):
                        build_geojson = build_line_from_xarray(ds, 'trajectory')
                        # add a map widget and load the geojson line into it
                        m = Map(center=(ds['latitude'].values[0], ds['longitude'].values[0]), zoom=4)
                        m.add_layer(build_geojson)
                        m.add_control(LayersControl())
                        ds.close()
                        pn.Column(m).servable()
                    else:
                        div_placeholder = pn.pane.HTML(f"<div> <b>The provided XARRAY trajectory dataset does not contain 'latitude' and 'longitude' coordinates:</b> <br> <br> {url[0].decode()}  <br> Detected coordinates: {list(ds.coords.keys())} </div>")     
                        div_placeholder.servable()
                        ds.close()
                        exit()
            else:
                    div_placeholder = pn.pane.HTML(f"<div> <b>Loading XARRAY trajectory dataset from URL:</b> <br>  <br> {url[0].decode()}  <br> Detected featureType: {ds.attrs['featureType']} </div>")     
                    div_placeholder.servable()
            
            ds_attributes = xr.open_dataset(url[0].decode()).attrs
            print("Dataset metadata:", ds_attributes)
            # conver python dict to json string
            import json
            json_widget = pn.pane.JSON({}, height=75)
            extract_ds_attributes = json.dumps(ds_attributes, indent=4)   
            json_widget.object = extract_ds_attributes
            div_placeholder = pn.pane.HTML(f"<div> <b>Successfully loaded xarray dataset from URL:</b> <br>  <br> {url[0].decode()} </div>", width=800, height=600)     
            output = pn.Column(div_placeholder, json_widget, sizing_mode="stretch_both")
            output.servable()
        else:
            div_placeholder = pn.pane.HTML(f"<div> <b>Provided URL is not pointing to a valid XARRAY dataset:</b> <br> <br> {url[0].decode()} </div>", width=800, height=600)     
            div_placeholder.servable()