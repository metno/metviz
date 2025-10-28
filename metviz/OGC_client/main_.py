from bokeh.plotting import curdoc
from ipywidgets_bokeh import IPyWidget
from bokeh.layouts import column, row

#
from csw_search import *
from datetime import datetime
from ipyleaflet import Map, basemaps, basemap_to_tiles, DrawControl, GeoJSON

global box
# from ipydatetime import DatetimePicker

# watercolor = basemap_to_tiles(basemaps.Stamen.Watercolor)
watercolor = basemap_to_tiles(basemaps.OpenStreetMap.Mapnik) 

# from sidecar import Sidecar
from IPython.display import display, HTML
import ipyleaflet as L
from ipywidgets import widgets as w
from datetime import datetime
import pandas as pd

import dateutil
import dateutil.parser

curdoc_element = curdoc()


lat_label = w.Label()
lon_label = w.Label()

out = w.Textarea(
    value="",
    placeholder="OK",
    description="",
    layout=w.Layout(height="auto", width="auto"),
)


lc = L.LayersControl(position="topright")

endpoint_entry = w.Text(
    value="https://nbs.csw.met.no/csw",
    placeholder="CSW Catalogue endpoint",
    description="",
    disabled=False,
)

datetime_picker_start = w.DatetimePicker()
datetime_picker_end = w.DatetimePicker()

# out = w.Output(layout=w.Layout(width='50%',
#                               height='400px',
#                               overflow_y='scroll'))

m = L.Map(layers=(watercolor,), center=(74, 378), zoom=5)

draw = L.DrawControl(
    edit=True,
    remove=True,
    circlemarker={},
    marker={},
    circle={},
    polyline={},
    polygon={},
    rectangle={"shapeOptions": {}},
)


feature_collection = {"type": "FeatureCollection", "features": []}


def mk_clear_button(target, action_name):
    b = w.Button(description=action_name.replace("_", " "))
    action = getattr(target, action_name)
    b.on_click(lambda *a: action())
    return b


def clear_text(target, value):
    target.value = value


def mk_clear_button2(target, value):
    b = w.Button(description="clear output")
    b.on_click(lambda *a: clear_text(target, value))
    return b


def handle_interaction(**kwargs):
    if kwargs.get("type") == "mousemove":
        coords = kwargs.get("coordinates")
        # lon = coords[1]-360
        # lat = coords[0]
        lat_label.value = str(coords[0])
        lon_label.value = str(coords[1] - 360)
        # print(coords[0], coords[1]-360)


def handle_click(**kwargs):
    out.value = str(kwargs) + str(type(kwargs))
    # with out:
    #    print(kwargs)
    #    print(type(kwargs))
    # kwargs['feature']['properties'][foobar] = 10


def on_draw_handler(draw, action, geo_json):

    # m.remove_layer(draw.last_drawn)
    # with out:
    # out.clear_output()
    for i in m.layers:
        if type(i) == L.GeoJSON:
            print("ok")
            m.remove_layer(i)
    bounds = geo_json["geometry"]["coordinates"][0]
    bounds = [[i[0] - 360, i[1]] for i in bounds if i[0] >= 180]
    ll = bounds[0]
    ur = bounds[2]
    print(ll, ur)
    corners = [ll, ur]
    bbox = [item for sublist in corners for item in sublist]
    start = dateutil.parser.parse(str(datetime_picker_start.value))
    end = dateutil.parser.parse(str(datetime_picker_end.value))
    records = csw_query(
        endpoint=endpoint_entry.value,
        bbox=bbox,
        start=start,
        stop=end,
        kw_names=None,
        crs="urn:ogc:def:crs:OGC:1.3:CRS84",
    )
    # geo_json['records'] = records
    searchbox = GeoJSON(data=geo_json)
    searchbox.on_click(handle_click)
    m.add_layer(searchbox)
    draw.clear_rectangles()
    # features = geojson['features']
    # display(pd.json_normalize(geo_json))
    out.value = records


clear_output = mk_clear_button2(out, " ")
draw.on_draw(on_draw_handler)
m.add_control(draw)
m.add_control(lc)
m.on_interaction(handle_interaction)

dashboard = w.VBox(
    [
        w.HBox([w.Label(value="CSW Endpoint:"), endpoint_entry]),
        w.HBox([datetime_picker_start, datetime_picker_end]),
        w.VBox([clear_output]),
        w.HBox([m]),
        w.HBox([lon_label, lat_label]),
    ]
)


wrap_dashboard = IPyWidget(widget=dashboard, sizing_mode="scale_both", height=900)
wrap_labels = IPyWidget(widget=w.HBox([lon_label, lat_label]), sizing_mode="scale_both")
wrap_out = IPyWidget(widget=w.HBox([out]), sizing_mode="scale_both")

layout = row([wrap_dashboard, wrap_out], height_policy="fit", sizing_mode="scale_both")

curdoc_element.add_root(layout)