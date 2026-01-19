import panel as pn
import xarray as xr
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from ipyleaflet import Map, Polyline, Marker

pn.extension('ipywidgets')

ds = xr.open_dataset(
    'https://thredds.met.no/thredds/dodsC/arcticdata/'
    'arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc'
)

ts_plot = figure(x_axis_type='datetime', sizing_mode='stretch_both')
ts_cds = ColumnDataSource(
    {'time': ds.time.values, 'values': ds.temperature.values}
)
ts_plot.line(x='time', y='values', source=ts_cds)
vspan_cds = ColumnDataSource({'time': [ds.time.values[0]]})
ts_plot.vspan(x='time', source=vspan_cds)

length = len(ds.time) - 1
slider = pn.widgets.IntSlider(
    name='Index', start=0, end=length, value=0, sizing_mode='stretch_width'
)

locations = []
for lat, lon in zip(ds.latitude.values, ds.longitude.values):
    locations.append([lat, lon])

line = Polyline(locations=locations, color='green', fill=False)

m = Map()
m.add(line)
m.layout.height = '100%'
m.layout.width = '100%'
marker = Marker(location=locations[0], draggable=False)
m.add(marker)


def update_plot(event):
    vspan_cds.data.update({'time': [ds.time.values[slider.value]]})

    global marker
    m.remove(marker)
    marker = Marker(location=locations[slider.value], draggable=False)
    m.add(marker)


slider.param.watch(update_plot, 'value')

plots = pn.Row(ts_plot, pn.panel(m, sizing_mode='stretch_both'))
layout = pn.Column(plots, slider)

layout.servable()
