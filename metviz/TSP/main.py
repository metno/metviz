"""
====================

Copyright 2022 MET Norway

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
# This file is part of ncmet.
#
# https://github.com/metno/ncmet
#
# ncmet is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ncmet is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ncmet.  If not, see <http://www.gnu.org/licenses/>.

import time
import traceback
import functools
import hvplot.xarray
import xarray as xr
import panel as pn
import numpy as np
import holoviews as hv
from utility import (
    ModelURL, pandas_frequency_offsets, get_download_link, load_data,
    validate_url, build_metadata_widget, build_download_widget, show_hide_widget,
    on_server_loaded, on_session_destroyed, validate_opendap,
    get_plottable_vars, get_axis_candidates, safe_check_var, AXIS_BLACKLIST,
)
from js_util import Redirector

from starlette.templating import Jinja2Templates
import json
import sys
from bokeh.models import Button, Div
from bokeh.layouts import column, Spacer
import pandas as pd
# from bokeh.models.formatters import DatetimeTickFormatter
from jinja2 import Environment, FileSystemLoader
import gc
import param

# pn.extension(sizing_mode="scale_both", loading_indicator=True)

env = Environment(loader=FileSystemLoader('/assets'))
pn.param.ParamMethod.loading_indicator = True
hv.extension('bokeh')
ds = None

# NetCDF standard missing/fill value used by many CF-convention datasets
FILL_VALUE = 9.96921e36


def _is_time_like(name: str) -> bool:
    """Return True if *name* refers to a datetime-like axis in the current dataset."""
    try:
        idx = ds.indexes.get(name)
        if idx is not None:
            return idx.dtype.kind in 'Mm' or isinstance(idx, xr.CFTimeIndex)
        return np.issubdtype(ds[name].dtype, np.datetime64)
    except Exception:
        return False

# CREATE LOGGER
import logging

def create_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)   
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)  
    return logger
logger = create_logger()



# USE logger to log messages instead of print statements
logger.info("Starting the application...")






def plot_quadmesh(variable_name, dataset, title=None):
    print(f"""plotting quadmesh for var: {variable_name}, 
          with dataset dims: {dataset[variable_name].dims}, 
          and indexes: {dataset[variable_name].indexes}""")
    da = dataset[variable_name]
    result = {
        'time' if pd.api.types.is_datetime64_any_dtype(ds[variable_name][i].values) else 'value': i
        for i in list(dataset[variable_name].indexes)
    }
    if not title:
        try:
            title = f"{dataset[variable_name].attrs['long_name']}"
        except KeyError:
            title = f"{variable_name}"
    else:
        title=title
    # Ensure 'time' and 'depth' dimensions exist
    if result['time'] in da.dims and result['value'] in da.dims:
        # Get the coordinate centers
        time = da[result['time']] # da["time_release_sonde"].values
        second_dimension = da[result['value']] #da["hgt_sonde"].values
        values = da.values
        
        # Directly use time values for edges
        time_edges = np.append(time[:-1] - (time[1] - time[0]) / 2, time[-1] + (time[-1] - time[-2]) / 2)
        second_dimension_edges = np.linspace(second_dimension[0], second_dimension[-1], len(second_dimension) + 1)
        
        # Create a QuadMesh plot
        hv_obj = hv.QuadMesh(
            (time_edges, second_dimension_edges, values.T),  # Transpose values to match expected shape
            kdims=list(dataset[variable_name].indexes),
            vdims=[variable_name]
        ).opts(
            cmap="viridis",
            colorbar=True,
            xlabel=ds[result['time']].long_name, #  result['time'],
            ylabel=ds[result['value']].long_name, # result['value'],
            title=f"QuadMesh Plot for {title}",
            responsive=True,
            # width=600,
            tools=['hover'],
            #xformatter=DatetimeTickFormatter(
            #    days="%m/%d",   # Month/Day format for daily ticks
            #    months="%m/%d", # Month/Day format for monthly ticks
            #    years="%m/%d"   # Month/Day format for yearly ticks
            #),
            # xticks=5,
            # xticks= time,  # Set the exact timestamps as ticks
            xrotation=45,  # Rotate the tick labels by 45 degrees
        )
        return hv_obj
    else:
        print(f"Variable {variable_name} does not have 'time' and 'depth' dimensions.")
        return None


def plot(var, ds, dimension=None, title=None, frequency=None, monotonic=None, featureType=None, invert_yaxis: bool = False, swap_axes: bool = False):
    # frequency selector should be handled outside the plot method
    # which should take as input an optional resampling frequency instead of the frequency selector widget

    # do not change 'widget_location': 'top' - the code uses indexes to detect plot canvas and slider 
    axis_arguments = {'grid':True, 
                      'x': dimension, 
                      'title': title, 
                      'responsive': True, 
                      'widget_location': 'top'}
    if type(var) == list:
        var = var[0]
    logger.info(f'plotting var: {var}')
    if not dimension:
        dimension = dimension_group.value
    if not title:
        try:
            title = f"{ds[var].attrs['long_name']}"
        except KeyError:
            title = f"{var}"
    else:
        title=title
    if 'featureType' in ds.attrs:
        featureType = ds.attrs['featureType'].lower()
    elif 'cdm_data_type' in ds[var].attrs:
        featureType = ds[var].attrs['cdm_data_type'].lower()
    else:
        featureType = None
    #is_monotonic = False

    if featureType == 'timeseries':
        var_coord = [i for i in ds.coords if ds.coords.dtypes[i] == np.dtype('<M8[ns]')]
        time_coord = True
    else:
        time_coord = False
        var_coord = list(ds.coords)

    if featureType == 'timeseries':
        if monotonic:
            frequency_selector.visible = True
        else:
            frequency_selector.visible = False
        # removing 'y': ds[var], from the axis_arguments dictionary
        # to bypass the error described in the following github issue
        # https://github.com/holoviz/hvplot/issues/1325
        axis_arguments = {'grid':True, 
                          'x': dimension, 
                          'title': title, 
                          'responsive': True, 
                          'widget_location': 'top',
                          'min_height': 600}
        if monotonic and frequency != "--":
            resampling_freq = {var_coord[0]: pandas_frequency_offsets[frequency]}
            # .where(ds_raw != FILL_VALUE)
            plot_widget = ds[var].where(ds[var] != FILL_VALUE).resample(**resampling_freq).mean().hvplot.line(**axis_arguments)
        else:
            # .where(ds_raw != FILL_VALUE)
            plot_widget =  ds[var].where(ds[var] != FILL_VALUE).hvplot.line(**axis_arguments)
        if len(list(plot_widget)) >= 2:
            plot_widget[0].height = 90
        logger.info(f"Plotting plot_widget with size: {len(list(plot_widget))} ,  with height {plot_widget[0].height} and width {plot_widget[0].width} ")
        # plot_widget[0].width = 400
        return plot_widget
    if featureType != "timeseries":
        frequency_selector.visible = False

        # Decide whether to invert the y-axis.
        # Classic profile view: depth/pressure increases downward.
        invert_yaxes = False
        if any(kw in dimension.lower() for kw in ('depth', 'pressure', 'pres')):
            invert_yaxes = True
        # Honour the CF 'positive' attribute when the dimension is a real variable.
        if dimension in ds:
            if ds[dimension].attrs.get('positive', '') == 'down':
                invert_yaxes = True
        if ds[var].attrs.get('positive', '') == 'down':
            invert_yaxes = True
        # User override: checkbox can force inversion regardless of auto-detection.
        invert_yaxes = invert_yaxes or invert_yaxis

        # Always put the selected dimension on the x-axis.
        # hvplot uses the DataArray values as the y-axis automatically.
        # Remove any stale 'y' key so it does not override hvplot's default.
        axis_arguments['x'] = dimension
        axis_arguments.pop('y', None)

        # For DSG-style datasets (e.g. profile), the selected dimension may be
        # a separate 1-D variable (depth, pressure) that shares the observation
        # dimension with `var` but is NOT registered as a coordinate of `var`.
        # In that case `ds[var].hvplot.line(x=dimension)` would raise a KeyError;
        # use a Dataset-level call instead so both arrays are accessible.
        dim_on_var = (
            dimension in ds[var].dims or dimension in ds[var].coords
        )
        try:
            if dim_on_var:
                plot_widget = ds[var].where(ds[var] != FILL_VALUE).hvplot.line(**axis_arguments)
            else:
                # Build a minimal sub-dataset containing only what hvplot needs.
                ds_sub = ds[[v for v in (var, dimension) if v in ds.data_vars]]
                plot_widget = ds_sub.hvplot.line(
                    x=dimension, y=var,
                    **{k: v for k, v in axis_arguments.items() if k != 'x'},
                )
            if invert_yaxes:
                plot_widget[-1].object.opts(invert_yaxis=True)
            if swap_axes:
                plot_widget[-1].object.opts(invert_axes=True)
        except Exception as exc:
            logger.warning(
                f"plot() failed (var={var!r}, dimension={dimension!r}): {exc} — "
                "falling back to default axis"
            )
            axis_arguments.pop('x', None)
            plot_widget = ds[var].where(ds[var] != FILL_VALUE).hvplot.line(**axis_arguments)

        # set the height of the slider widget to 60
        plot_widget[0].height = 60
        return plot_widget


# method to update the plot when a new variable is selected    
def on_var_select(event):
    var = event.obj.value
    result = [key for key, value in mapping_var_names.items() if value == var]
    if not result:
        return
    # Rebuild axis candidates for the newly selected variable
    new_options = get_axis_candidates(ds, result[0])
    new_options = sorted(new_options, key=lambda n: (0 if _is_time_like(n) else 1, n))
    dimension_group.options = new_options or ['obs']
    dimension_group.value = dimension_group.options[0]

    if featureType == 'timeseriesprofile' and quadmesh_checkbox:
        quadmesh_checkbox.visible = len(new_options) >= 2
    with pn.param.set_values(main_app, loading=True):
        plot_container[-2] = plot(var=result, ds=ds, dimension=dimension_group.value, frequency=frequency_selector.value, title=var, monotonic=monotonic, featureType=featureType, invert_yaxis=invert_yaxis_checkbox.value, swap_axes=swap_axes_checkbox.value)
        logger.info(f'selected variable: {result}')

        if quadmesh_checkbox:
            if quadmesh_checkbox.value:
                if len(quadmesh_plot) >= 1:
                    quadmesh_plot.pop(-1)
                # else:
                quadmesh_plot.insert(-1, plot_quadmesh(result[0], ds))
        

def on_dimension_select(event):
    dimension = event.obj.value
    with pn.param.set_values(main_app, loading=True):
        selected_var = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
        plot_container[-2] = plot(var=selected_var, ds=ds, dimension=dimension, title=variables_selector.value, frequency=frequency_selector.value, monotonic=monotonic, featureType=featureType, invert_yaxis=invert_yaxis_checkbox.value, swap_axes=swap_axes_checkbox.value)
        logger.info(f'dimension selected: {dimension}')
        # print(dir(plot_container[-2]))
        # print(plot_container[-2].height, plot_container[-2].height_policy)
        # plot_container.height_policy='max'
        # print(dir(plot_container))
        
        
def on_frequency_select(event):
    # frequency selector should be handled outside the plot method
    # which should take as input an optional resampling frequency instead of the frequency selector widget
    # this method should just trigger a re-plot with the new frequency
    frequency = event.obj.value
    var = variables_selector.value
    result = [key for key, value in mapping_var_names.items() if value == var]
    with pn.param.set_values(main_app, loading=True):
        plot_container[-2] = plot(var=result, ds=ds, title=var, dimension=dimension_group.value, frequency=frequency, monotonic=monotonic, featureType=featureType, invert_yaxis=invert_yaxis_checkbox.value, swap_axes=swap_axes_checkbox.value)
        logger.info(f'selected variable: {result}, frequency: {frequency}')


def on_quadmesh_select(event):
    with pn.param.set_values(main_app, loading=True):
        if event.obj.value:
            # plot_container.insert(-2, Div(text=f'<font size = "2" color = "darkslategray" >QUADMESHPLOT ADDED</font>'))
            quadmesh_plot.visible = True
            #quadmesh_plot.insert(-1, Div(text=f'<font size = "2" color = "darkslategray" >QUADMESHPLOT PLOT</font>'))
            if len(quadmesh_plot) >= 1:
                quadmesh_plot.pop(-1)
            var = variables_selector.value
            result = [key for key, value in mapping_var_names.items() if value == var]
            quadmesh_plot.insert(-1, plot_quadmesh(result[0], ds))
        else:
            # plot_container.pop(-2)
            quadmesh_plot.visible = False
            quadmesh_plot.pop(-1)
        print(f'quadmesh: {event.obj.value}')


def on_invert_yaxis_select(event):
    with pn.param.set_values(main_app, loading=True):
        selected_var = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
        plot_container[-2] = plot(
            var=selected_var, ds=ds, dimension=dimension_group.value,
            title=variables_selector.value, frequency=frequency_selector.value,
            monotonic=monotonic, featureType=featureType,
            invert_yaxis=invert_yaxis_checkbox.value,
            swap_axes=swap_axes_checkbox.value,
        )


def on_swap_axes_select(event):
    with pn.param.set_values(main_app, loading=True):
        selected_var = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
        plot_container[-2] = plot(
            var=selected_var, ds=ds, dimension=dimension_group.value,
            title=variables_selector.value, frequency=frequency_selector.value,
            monotonic=monotonic, featureType=featureType,
            invert_yaxis=invert_yaxis_checkbox.value,
            swap_axes=swap_axes_checkbox.value,
        )   




        
def export_selection(event):
    """docstring"""
    select_output_format_mapping = {'NetCDF':'nc', 'CSV':'csv', 'Parquet':'pq'}
    with pn.param.set_values(main_app, loading=True):
        export_format = select_output_format_mapping[select_output_format.value]
        fs_active = frequency_selector is not None and frequency_selector.visible
        if fs_active and frequency_selector.value not in ("--", "Raw"):
            resampler = True
            resampler_frequency = frequency_selector.value
        else:
            resampler = False
            resampler_frequency = 'raw'
        if not frequency_selector or not frequency_selector.visible or frequency_selector.value == "--":
            time_range = []
        else:
            # time_range = date_time_range_slider.value
            time_range = [str(i) for i in date_time_range_slider.value]
        selected_variables = [i.name for i in wbx if i.value == True]
        # event_log.text = f"{str(selected_variables)} <br> {time_range} <br> {export_format} <br> {resampler}"
        
        export_dataspec = {
            "url": str(url),
            "variables": selected_variables,
            "decoded_time": decoded_time,
            "time_range": time_range,
            "is_resampled": resampler,
            "resampling_frequency": resampler_frequency,
            "output_format": export_format,
        }
        json_object = json.dumps(export_dataspec)
        print(json_object)
        download_link = get_download_link(json_object)
        # event_log.text = f"{str(export_dataspec)}"
        event_log.text = str(
            f'<marquee behavior="scroll" direction="left"><b>. . .  processing . . .</b></marquee>'
        )
        pn.state.curdoc.add_next_tick_callback(
            functools.partial(
                compress_selection, download_link=download_link, output_log_widget=event_log))
        


def compress_selection(download_link, output_log_widget):
    time.sleep(2)
    output_log_widget.text = str(
                f'<a href="{download_link}">Download</a>'
            )
    print(download_link)
    
    



pn.state.onload(callback=on_server_loaded)
# pn.state.on_session_created(callback=on_session_created)
pn.state.on_session_destroyed(callback=on_session_destroyed)

templates = Jinja2Templates(directory="/app/templates")

if 'url' not in pn.state.session_args:
    redirector = Redirector()
    # add a list of example urls below the input box
    Resources = {
        "Time Series 1": "https://thredds.met.no/thredds/dodsC/arcticdata/infranor/UiO-Kongsvegen-AWS/UiO-Kongsvegen-AWS-sw200-agg.ncml",
        "Time Series 2": "https://thredds.met.no/thredds/dodsC/arcticdata/obsSynop/01008",
        "Profile 1": "https://opendap1.nodc.no/thredds/dodsC/chemistry/StationM/StationM_2008_2019_v2.nc",
        "Profile 2": "https://opendap1.nodc.no/thredds/dodsC/chemistry/StationM/StationM_2008_2019_v1.nc",
        "Time Series Profile 1": "https://thredds.met.no/thredds/dodsC/arcticdata/frost2netcdf-permafrost/SN99868/SN99868-aggregated.ncml",
        "Time Series Profile 2": "https://thredds.met.no/thredds/dodsC/arcticdata/met.no/obs-temp/obs-temp_20892.nc",
        "Trajectory 1": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc",
        "Trajectory 2": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/SIMBA/simba-510_air-temperature2022.nc",
    }
    
    # add the resources to a table widget
    # AttributeError: 'dict' object has no attribute 'index'
    resources_df = pd.DataFrame.from_dict(Resources, orient='index', columns=['URL'])
    resources_table = pn.widgets.DataFrame(
        resources_df,
        name="Example URLs",
        # width=600,
        # height=200
    )
    # add a button to add selected row url to the input box
    add_button = pn.widgets.Button(name="Add URL", button_type="primary")
    # method to add the selected row url to the input box
    def add_url(event):
        selected = resources_table.selection
        if selected:
            url_input.value = resources_df.iloc[selected[0]]['URL']

    add_button.on_click(add_url)

    # add a line editing widget for the url input
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
        ds, decoded_time, error_log, monotonic, featureType = load_data(url)
        # featureType = get_featuretype(url)
        feature_type_mapping = {
            "timeseries": "TSP",
            "trajectory": "TRJ",
            "profile": "TSP",
        }
        
        print("------------------------- LOADING ++++++++++++++++++++++++++++++++++++")
        print("FeatureType detected:", featureType)

        target = f"/{feature_type_mapping.get(featureType, 'TSP')}?url={url}"
        redirector.redirect(target)
    
    
    # @pn.depends(menu_button.param.clicked, watch=True)
    # def handle_selection(value):
    #     code = f"window.location.href='{value}'"
    #     javascript.eval(code)

    pn.Column(
        redirector,
        url_input,
        url_button,
        resources_table,
        add_button, sizing_mode='stretch_height'
    ).servable()
else:
    url = pn.state.session_args.get('url')[0].decode("utf8")

    valid_url = validate_url(url)

    # check if the url points to a valid dataset
    valid_url = validate_opendap(url)

    if not valid_url:
        error_log = Div(text=f"""<br><b>Invalid URL:</b><br>   {url}  <br><br> Please provide a valid OPeNDAP URL.""")
        bokeh_pane = pn.pane.Bokeh(
                column(error_log),
                loading_indicator = True
            ).servable()
    else:
        print("++++++++++++++++++++++++ LOADING ++++++++++++++++++++++++++++++++++++")
        print(str(url))
        print("++++++++++++++++++++++++ +++++++ ++++++++++++++++++++++++++++++++++++")
        ds, decoded_time, error_log, monotonic, featureType = load_data(url)
        if not ds:
            raw_data = Div(text=f"""<b>ValueError</b><br><br> Can't load dataset from {url} """)
            newhtml = templates.get_template("error.html").render(
                {"error_traceback": error_log}
            )
            error_log = Div(text=f"""<br><br> Can't load dataset from {url} """)
            error_log.text = newhtml
            error_log.visible = False
            error_log_button = Button(
                label="",
                height=50,
                width=50,
            )  # , width_policy='fixed'
            # error_log_button.on_click(show_hide_error)
            error_log_button.on_click(functools.partial(show_hide_widget, widget=error_log))

            print(newhtml)
            bokeh_pane = pn.pane.Bokeh(
                column(raw_data, error_log_button, error_log),
                loading_indicator = True
            ).servable()
            


    frequency_selector = pn.widgets.Select(options=[
            "--",
            "Hourly",
            "Calendar day",
            "Weekly",
            "Month end",
            "Quarter end",
            "Yearly",
        ], name='Resampling Frequency')

    if frequency_selector is not None:
        frequency_selector.param.watch(on_frequency_select, parameter_names=['value'])
        
        
    if ds:
        # Identify plottable variables using the featureType-agnostic helper.
        # get_plottable_vars() uses ds.data_vars (not ds which includes coords),
        # filters to numeric dtypes, skips coordinate-like names, and applies
        # a safe access check. This correctly handles DSG datasets where the
        # obs dimension has no registered coordinate.
        plottable_vars = get_plottable_vars(ds)
        logger.info(f"Identified plottable variables: {plottable_vars}")

        # Build a dict mapping internal name → display label (long_name [name])
        mapping_var_names = {}
        for i in plottable_vars:
            try:
                title = f"{ds[i].attrs['long_name']} [{i}]"
            except KeyError:
                title = f"{i}"
            mapping_var_names[i] = title

        # Variable selector dropdown uses the display labels
        variables_selector = pn.widgets.Select(options=list(mapping_var_names.values()), name='Data Variable')

        result = [key for key, value in mapping_var_names.items() if value == variables_selector.value]

        # Axis candidates: named indexes first, then any 1-D variable sharing
        # the same dimension (picks up depth/pressure for DSG profile data).
        axis_options = get_axis_candidates(ds, result[0]) if result else []
        # Sort: put time-like candidates first so the default is sensible.
        axis_options = sorted(axis_options, key=lambda n: (0 if _is_time_like(n) else 1, n))
        dimension_group = pn.widgets.RadioBoxGroup(
            name='Dimension', options=axis_options or ['obs'], inline=False
        )
        dimension_group.value = dimension_group.options[0]

        if featureType == 'timeseriesprofile':
            quadmesh_checkbox = pn.widgets.Checkbox(name='Quadmesh', value=False)
            quadmesh_checkbox.param.watch(on_quadmesh_select, parameter_names=['value'])
            quadmesh_checkbox.visible = len(axis_options) >= 2
        else:
            quadmesh_checkbox = None

        invert_yaxis_checkbox = pn.widgets.Checkbox(name='Invert Y-axis', value=False)
        swap_axes_checkbox = pn.widgets.Checkbox(name='Swap axes', value=False)

    if ds:
        # Export Widgets
        export_button, wbx, date_time_range_slider, export_options_button, event_log, select_output_format, export_resampling = build_download_widget(ds, mapping_var_names, frequency_selector)
        export_options_button.on_click(export_selection)
        

        download_header = Div(text='<font size = "2" color = "darkslategray" ><b>Data Export<b></font> <br> Variable Selection')
        # download_header.visible = False
        # Metadata Widgets
        metadata_layout, metadata_button = build_metadata_widget(ds.attrs)
        # downloader = pn.Column(download_header, wbx, date_time_range_slider, select_output_format, export_resampling, export_options_button, event_log, width=400, sizing_mode='fixed')
        downloader = pn.Row(Spacer(width=10), pn.Column(Spacer(height=120),
                                                        download_header, 
                                                        wbx, 
                                                        date_time_range_slider, 
                                                        select_output_format, 
                                                        export_resampling, 
                                                        export_options_button, 
                                                        event_log, width=400, sizing_mode='fixed'))
        metadata_button.on_click(functools.partial(show_hide_widget, widget=metadata_layout, hide=downloader))
        export_button.on_click(functools.partial(show_hide_widget, widget=downloader, hide=metadata_layout))
        downloader.visible = False

        variables_selector.param.watch(on_var_select, parameter_names=['value'])
        dimension_group.param.watch(on_dimension_select, parameter_names=['value'])
        invert_yaxis_checkbox.param.watch(on_invert_yaxis_select, parameter_names=['value'])
        swap_axes_checkbox.param.watch(on_swap_axes_select, parameter_names=['value'])
        #if quadmesh_checkbox:
        #    quadmesh_checkbox.param.watch(on_quadmesh_select, parameter_names=['value'])
        selected_var = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
        dimension = dimension_group.value
        logger.info(f"Initial variable selected: {selected_var}, with dimension: {dimension}")
        buttons = pn.Column(export_button, metadata_button)
        plot_plot = plot(selected_var, ds, dimension, title=variables_selector.value, frequency=frequency_selector.value, monotonic=monotonic, featureType=featureType)
        # print(dir(plot_plot))
        # quadmesh_plot = pn.Row(Div(text=f'<font size = "2" color = "darkslategray" >QUADMESHPLOT PLACEHOLDER</font>'))
        quadmesh_plot = pn.Row(sizing_mode='scale_both')
        quadmesh_plot.visible = False
        plot_container = pn.Column(pn.Row(variables_selector,
                                          pn.Row(Div(text=f'<font size = "2" color = "darkslategray" >Dimension</font>'),
                                                 dimension_group),
                                          frequency_selector,
                                          pn.Column(invert_yaxis_checkbox, swap_axes_checkbox),
                                          buttons),
                                   quadmesh_checkbox,
                                   quadmesh_plot,
                                   plot_plot,
                                   Spacer(height=10),
                                   sizing_mode='scale_both')

        main_app = pn.Row(plot_container, 
                        Spacer(width=10), 
                        downloader, 
                        metadata_layout, height_policy='max')


        main_app.servable()
        
