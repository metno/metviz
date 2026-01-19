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
from utility import ModelURL, pandas_frequency_offsets, get_download_link, load_data, validate_url, build_metadata_widget, build_download_widget, show_hide_widget, on_server_loaded, on_session_destroyed, validate_opendap
from js_util import Javascript

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

ds = None


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


def plot(var, ds, dimension=None, title=None, frequency=None, monotonic=None, featureType=None):
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
        print('i am getting: ', var)
    else:
        # result = [key for key, value in mapping_var_names.items() if value == var]
        print('i am getting: ', var)
    print(mapping_var_names)
    print(f'plotting var: {var}')
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
        axis_arguments = {'grid':True, 'x': dimension, 'title': title, 'responsive': True, 'widget_location': 'top'}
        print(axis_arguments)
        if monotonic and frequency != "--":
            print('data resampling requested')
            resampling_freq = {var_coord[0]: pandas_frequency_offsets[frequency]}
            # .where(ds_raw != 9.96921e36)
            plot_widget = ds[var].where(ds[var] != 9.96921e36).resample(**resampling_freq).mean().hvplot.line(**axis_arguments)
        else:
            # .where(ds_raw != 9.96921e36)
            plot_widget =  ds[var].where(ds[var] != 9.96921e36).hvplot.line(**axis_arguments)
        return plot_widget
    if featureType != "timeseries":
        frequency_selector.visible = False
        print('got this dimension: ', dimension.lower())
        if 'time' not in dimension.lower():
            if 'depth' in dimension.lower():
                invert_yaxes=True
            else:
                invert_yaxes=False
            y = dimension
            # x = ds[var] 
            x = var
        else:
            invert_yaxes=False
            x = dimension
            # y = ds[var] 
            y = var
        # axis_arguments = {'x': x, 'y': y, 'grid':True, 'title': title, 'widget_location': 'top', 'responsive': True}
        axis_arguments['x'] = x
        axis_arguments['y'] = y
        print(axis_arguments)
        # axis_arguments = {'x': ds[var], 'y': dimension, 'grid':True, 'title': title, 'widget_location': 'bottom', 'responsive': True}
        if ds[var].attrs.get('positive', '') == 'down':
            invert_yaxes = True
        if ds[dimension].attrs.get('positive', '') == 'down':
            invert_yaxes = True
        try:
            plot_widget =  ds[var].where(ds[var] != 9.96921e36).hvplot.line(**axis_arguments)
            if invert_yaxes:
                plot_widget[-1].object.opts(invert_yaxis=True)
        except TypeError:
            print('TypeError')
            axis_arguments['y'] = dimension
            # axis_arguments = {'grid':True, 'y': dimension, 'title': title, 'widget_location': 'top', 'responsive': True}
            plot_widget =  ds[var].where(ds[var] != 9.96921e36).hvplot.line(**axis_arguments)
            if invert_yaxes:
                plot_widget[-1].object.opts(invert_yaxis=True)
        except ValueError:
            print('ValueError')
            if 'time' not in dimension.lower():
                x = var 
            else:
                y = var 
            axis_arguments['x'] = x
            axis_arguments['y'] = y
            # axis_arguments = {'x': x, 'y': y, 'grid':True, 'title': title, 'widget_location': 'top', 'responsive': True}
            plot_widget =  ds[var].where(ds[var] != 9.96921e36).hvplot.line(**axis_arguments)
            if invert_yaxes:
                plot_widget[-1].object.opts(invert_yaxis=True)
        # axis_arguments['responsive'] = False
        # axis_arguments['widget_location'] = "bottom"
        print('axis_arguments:', axis_arguments)
        print('invert_yaxes:', invert_yaxes)
        # set the height of the plot widget (slider to tune the dimension value) to 60 
        plot_widget[0].height = 60
        return plot_widget        


# method to update the plot when a new variable is selected    
def on_var_select(event):
    # quadmesh stopped working
    # need to check
    var = event.obj.value
    result = [key for key, value in mapping_var_names.items() if value == var]
    dimension_group.options = list(ds[result].indexes)
    if len(ds[result].indexes) >= 2 and featureType == 'timeseriesprofile':
        print('activating quadmesh')
        #quadmesh_plot.visible = True
        if quadmesh_checkbox:
            quadmesh_checkbox.visible = True
        #quadmesh_plot.visible = True
    else:
        #quadmesh_plot.visible = False
        if quadmesh_checkbox:
            quadmesh_checkbox.visible = False
        #quadmesh_plot.visible = False
    with pn.param.set_values(main_app, loading=True):
        # print(dir(plot_container[-1]))
        # print(plot_container[-1][1].object.range(dimension_group.value))
        plot_container[-2] = plot(var=result, ds=ds, dimension=dimension_group.value, frequency=frequency_selector.value, title=var, monotonic=monotonic, featureType=featureType)
        print(f'selected {result}')
        # print(dir(plot_container[-1][1].object))
        
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
        plot_container[-2] = plot(var=selected_var, ds=ds, dimension=dimension , title=variables_selector.value, frequency=frequency_selector.value, monotonic=monotonic, featureType=featureType)
        print(f'selected {dimension}')
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
        plot_container[-2] = plot(var=result, ds=ds, title=var, dimension=dimension_group.value, frequency=frequency, monotonic=monotonic, featureType=featureType)
        print(f'selected {result} \n with frequency {frequency}') 


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


def safe_check(var):
    try:
        ds[var].values
        return var
    except Exception as e:
        # Handle the exception (e.g., log it, return False, etc.)
        print(f"Error processing {var}: {e}")
        return False
    

        
def export_selection(event):
    """docstring"""
    # print(box.values)
    # start = ds.index.searchsorted(date_time_range_slider.value[0])
    # end = ds.index.searchsorted(date_time_range_slider.value[1])
    # event_log.text = f"{str(wbx.value)} <br> {str(date_time_range_slider.value)}"
    select_output_format_mapping = {'NetCDF':'nc', 'CSV':'csv', 'Parquet':'pq'}
    with pn.param.set_values(main_app, loading=True):
        export_format = select_output_format_mapping[select_output_format.value]
        # export_format = select_output_format.value.lower()
        if frequency_selector is not None and frequency_selector.visible and frequency_selector.value != 'Raw':
            resampler = False
            resampler_frequency = 'raw '
            #print(export_resampling)
            #print(export_resampling.value)
        else:
            if frequency_selector is not None and frequency_selector.visible and frequency_selector.value != "--":
                resampler = True
                resampler_frequency = frequency_selector.value
                #print(export_resampling)
                #print(export_resampling.value)
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
        

        data = {
            "url": "https://thredds.met.no/thredds/dodsC/alertness/YOPP_supersite/obs/utqiagvik/utqiagvik_obs_timeSeriesProfileSonde_20180201_20180331.nc",
            "variables": [
                "ta",
                "hur",
                "wdir_refmt"
                ],
            "decoded_time": decoded_time,
            "time_range": [
                "2018-07-01T00:00:00.000000000",
                "2018-09-30T23:59:00.000000000"
                ],
            "is_resampled": resampler,
            "resampling_frequency": "raw",
            "output_format": "nc"
            }
        # download_link = get_download_link(data)
        
        # print(download_link)
        
        
        # time_range = [str(i) for i in date_time_range_slider.value]
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
        
        # print(json.dump(export_dataspec))
        #print(export_dataspec)
        #json_object = json.dumps(export_dataspec, indent = 4)
        #print(json_object)
        # slice the ds by selecting the variables fro the checkbox and slicing along the time dimension from the timerange slider (if available)


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
    javascript = Javascript()
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
            "trajectory": "trj",
            "profile": "TSP",
        }
        
        print("------------------------- LOADING ++++++++++++++++++++++++++++++++++++")
        print("FeatureType detected:", featureType)

        code = f"window.location.href='/{feature_type_mapping.get(featureType, 'TSP')}?url={url}'"
        javascript.eval(code)
    
    
    # @pn.depends(menu_button.param.clicked, watch=True)
    # def handle_selection(value):
    #     code = f"window.location.href='{value}'"
    #     javascript.eval(code)

    pn.Column(
        # menu_button,
        javascript,
        url_input,
        url_button,
        resources_table,
        add_button, sizing_mode='stretch_height',
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
            ).servable()
            
    # if ds:
    #     # if 'featureType' in ds.attrs:
    #     #     featureType = ds.attrs['featureType'].lower()
    #     # elif 'cdm_data_type' in ds[var].attrs:
    #     #     featureType = ds[var].attrs['cdm_data_type'].lower()
    #     # else:
    #     #     featureType = None
    #     if featureType == 'timeseries':
    #         var_coord = [i for i in ds.coords if ds.coords.dtypes[i] == np.dtype('<M8[ns]')]
    #         time_coord = True
    #     else:
    #         time_coord = False
    #         var_coord = list(ds.coords)
            



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
        # find plottable variables
        plottable_vars = [j for j in ds if len([value for value in list(ds[j].coords) if value in list(ds.dims)]) >= 1]
        # plottable_vars = [i for i in plottable_vars if len(ds[i].dims) == len(ds.indexes)]
        plottable_vars = [i for i in plottable_vars if safe_check(i)]
        # build a dictionary of variables and their long names
        print("plottable_vars:", plottable_vars )
        mapping_var_names = {}
        for i in plottable_vars:
            if int(len(list(ds[i].coords)) != 0):
                try:
                    title = f"{ds[i].attrs['long_name']} [{i}]"
                except KeyError:
                    title = f"{i}"
                mapping_var_names[i] = title
                
        # add a select widget for variables, uses long names
        variables_selector = pn.widgets.Select(options=list(mapping_var_names.values()), name='Data Variable')

        result = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
        dimension_group = pn.widgets.RadioBoxGroup(name='Dimension', options=list(ds[result].indexes), inline=False)
        if featureType == 'timeseriesprofile':
            quadmesh_checkbox = pn.widgets.Checkbox(name='Quadmesh', value=False)
            quadmesh_checkbox.param.watch(on_quadmesh_select, parameter_names=['value'])  
            if len(ds[result].indexes) >= 2:
                quadmesh_checkbox.visible = True
            else:
                quadmesh_checkbox.visible = False  
        else:
            quadmesh_checkbox = None
        
    if ds:
        # Export Widgets
        export_button, wbx, date_time_range_slider, export_options_button, event_log, select_output_format, export_resampling = build_download_widget(ds, mapping_var_names, frequency_selector)
        export_options_button.on_click(export_selection)
        
        # export_options_button
        # export_options_button.on_click(export_selection)
        download_header = Div(text='<font size = "2" color = "darkslategray" ><b>Data Export<b></font> <br> Variable Selection')
        # download_header.visible = False
        # Metadata Widgets
        metadata_layout, metadata_button = build_metadata_widget(ds.attrs)
        metadata_button.on_click(functools.partial(show_hide_widget, widget=metadata_layout))
        # downloader = pn.Column(download_header, wbx, date_time_range_slider, select_output_format, export_resampling, export_options_button, event_log, width=400, sizing_mode='fixed')
        downloader = pn.Row(Spacer(width=10), pn.Column(Spacer(height=120),
                                                        download_header, 
                                                        wbx, 
                                                        date_time_range_slider, 
                                                        select_output_format, 
                                                        export_resampling, 
                                                        export_options_button, 
                                                        event_log, width=400, sizing_mode='fixed'))
        export_button.on_click(functools.partial(show_hide_widget, widget=downloader))
        downloader.visible = False

        variables_selector.param.watch(on_var_select, parameter_names=['value'])
        dimension_group.param.watch(on_dimension_select, parameter_names=['value'])
        #if quadmesh_checkbox:
        #    quadmesh_checkbox.param.watch(on_quadmesh_select, parameter_names=['value'])
        selected_var = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
        dimension = dimension_group.value

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
                                          buttons), 
                                   quadmesh_checkbox, 
                                   quadmesh_plot, 
                                   plot_plot, 
                                   Spacer(height=10), 
                                   sizing_mode='scale_both') # , sizing_mode='scale_both'

        main_app = pn.Row(plot_container, 
                        Spacer(width=10), 
                        downloader, 
                        metadata_layout, height_policy='max')

        # tmpl.add_panel('A',  main_app)
        # tmpl.servable()

        ACCENT_BASE_COLOR = "#003366"
        pn.extension(sizing_mode="stretch_both")
        template = pn.template.BootstrapTemplate(
            site=" ADC NC-CF Data Visualization ",
            # site_url="https://www.northwestknowledge.net/adc/",
            favicon="/assets/ADC_logo.png",
            title="Time Series Profile Tool",
            logo="/assets/ADC_logo.png",
            header_background=ACCENT_BASE_COLOR,
            # accent_base_color=ACCENT_BASE_COLOR,
            main=[main_app],
        ).servable()