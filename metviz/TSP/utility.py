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

# Utility methods for hvplot
from pydantic import BaseModel, AnyHttpUrl, ValidationError
import base64
import re
from itsdangerous import TimestampSigner
import uuid
from pathlib import Path
import os
import json
import requests
import panel as pn
import xarray as xr
import numpy as np
import gc
from bokeh.models import Button, Div
from bokeh.layouts import column, Spacer
import sys
import gc

def on_server_loaded():
    print("server loaded")
    print("")
    sys.stdout.flush()
    

def on_session_created(session_context):
    print("session created")
    print("")
    sys.stdout.flush()


def on_session_destroyed(session_context):
    print("session destroyed")
    print("")
    print(dir(session_context))
    try:
        del ds
        gc.collect()
    except UnboundLocalError:
        pass
    try:
        del plot_widget
        gc.collect()
    except UnboundLocalError:
        pass
    plot_widget = None
    gc.collect()
    sys.stdout.flush()


class ModelURL(BaseModel):
    """_summary_

    Args:
        BaseModel (_type_): _description_

    example usage:
    try:
        ModelURL(url='ftp://invalid.url')
    except ValidationError as e:
        print(e)
    """

    url: AnyHttpUrl
    
def validate_url(url):
    try:
        nc_url = str(url)
        try:
            ModelURL(url=nc_url)
            valid_url = True
        except ValidationError as e:
            print(e)
            valid_url = False
    except TypeError:
        valid_url = False
    return valid_url

def validate_opendap(url):
    """Validate if a url is a valid OPeNDAP url

    Args:
        url (str): url to validate as OPeNDAP
    Returns:
        bool: True if valid OPeNDAP url, False otherwise
    """
    try:
        nc_url = str(url)
        # try to load the data trough xarray
        xr.open_dataset(nc_url, decode_times=False)
        valid_opendap = True
    except TypeError:
        valid_opendap = False
    except OSError:
        valid_opendap = False
    return valid_opendap


pandas_frequency_offsets = {
            "Hourly": "h",
            "Calendar day": "D",
            "Weekly": "W",
            "Month end": "ME",
            "Quarter end": "QE",
            "Yearly": "YE",
        }


def generate_download_string():
    """Generate download url and token for downloading a dataframe

    Args:
        df (pd.Dataframe): pandas dataframe to be downloaded
        filename (str): filename for the download file
        title (str): title for the download link

    Returns:
        _type_: _description_

    example usage:
    generate_download_link(df, filename="download.csv", title="Download CSV file")
    """
    
    download_url = ""
    output_format = "csv"
    rv = base64.b64encode(uuid.uuid4().bytes).decode("utf-8")
    unique = re.sub(
        r"[\=\+\/]", lambda m: {"+": "-", "/": "_", "=": ""}[m.group(0)], rv
    )
    filename = str(unique) + "." + str(output_format)
    s = TimestampSigner("secret-key")
    download_token = s.sign(filename).decode()
    # dirpath = os.path.join(os.path.dirname(__file__),'static', download)
    # dirpath = os.environ["TSPLOT_DOWNLOAD"]
    # TSPLOT_DOWNLOAD = os.path.join(os.path.dirname(__file__),'static', 'download')
    dirpath = os.environ["TSPLOT_DOWNLOAD"]
    outfile = Path(dirpath, str(download_token))
    return outfile


def dict_to_html(dd, level=0):
    """
    Convert dict to html using basic html tags
    """
    text = ''
    for k, v in dd.items():
        text += '<br>' + '&nbsp;'*(4*level) + '<b>%s</b>: %s' % (k, dict_to_html(v, level+1) if isinstance(v, dict) else (json.dumps(v) if isinstance(v, list) else v))
    return text

def dict_to_html_ul(dd, level=0):
    """
    Convert dict to html using ul/li tags
    """
    text = '<ul>'
    for k, v in dd.items():
        text += '<li><b>%s</b>: %s</li>' % (k, dict_to_html_ul(v, level+1) if isinstance(v, dict) else (json.dumps(v) if isinstance(v, list) else v))
    text += '</ul>'
    return text

def get_download_link(data):
    processing_endpoint = os.environ["PROCESSING_ENDPOINT"]
    download_endpoint = os.environ["DOWNLOAD_ENDPOINT"]
    s: requests.Session = requests.Session()
    url: str = f"{processing_endpoint}/process_data"
    r = s.post(url, data=data)
    print(url, data)
    download_endpoint = f"{download_endpoint}/results"
    download_url = f"{download_endpoint}/{r.json()['download_token']}"
    return download_url

    s = TimestampSigner("secret-key")
    download_token = s.sign(filename).decode()
    # dirpath = os.path.join(os.path.dirname(__file__),'static', download)
    # dirpath = os.environ["TSPLOT_DOWNLOAD"]
    # TSPLOT_DOWNLOAD = os.path.join(os.path.dirname(__file__),'static', 'download')
    dirpath = os.environ["TSPLOT_DOWNLOAD"]
    outfile = Path(dirpath, str(download_token))
    return outfile


def dict_to_html(dd, level=0):
    """
    Convert dict to html using basic html tags
    """
    text = ''
    for k, v in dd.items():
        text += '<br>' + '&nbsp;'*(4*level) + '<b>%s</b>: %s' % (k, dict_to_html(v, level+1) if isinstance(v, dict) else (json.dumps(v) if isinstance(v, list) else v))
    return text

def dict_to_html_ul(dd, level=0):
    """
    Convert dict to html using ul/li tags
    """
    text = '<ul>'
    for k, v in dd.items():
        text += '<li><b>%s</b>: %s</li>' % (k, dict_to_html_ul(v, level+1) if isinstance(v, dict) else (json.dumps(v) if isinstance(v, list) else v))
    text += '</ul>'
    return text

def get_download_link(data):
    processing_endpoint = os.environ["PROCESSING_ENDPOINT"]
    download_endpoint = os.environ["DOWNLOAD_ENDPOINT"]
    s: requests.Session = requests.Session()
    url: str = f"{processing_endpoint}/process_data"
    r = s.post(url, data=data)
    print(url, data)
    download_endpoint = f"{download_endpoint}/results"
    download_url = f"{download_endpoint}/{r.json()['download_token']}"
    return download_url


def is_monotonic(ds):
    """Check if an array is monotonic (either increasing or decreasing)

    Args:
        array (np.array): array to check
    Returns:
        bool: True if monotonic, False otherwise
    """
    var_coord = [i for i in ds.coords if ds.coords.dtypes[i] == np.dtype('<M8[ns]')]
    coords_values = ds.coords[var_coord[0]].values[::-1]
    monotonic = all(coords_values[i] <= coords_values[i + 1] for i in range(len(coords_values) - 1)) or all(coords_values[i] >= coords_values[i + 1] for i in range(len(coords_values) - 1))
    return monotonic

@pn.cache(per_session=True, max_items=10, ttl=600)
def load_data(url):
    try:
        del ds
        gc.collect()
    except UnboundLocalError:
        pass
    ds = None
    decoded_time = False
    error_log = None
    try:
        ds = xr.open_dataset(str(url).strip())
        decoded_time=True
    except ValueError as e:
        print(e)
        ds = xr.open_dataset(str(url).strip(), decode_times=False)
        decoded_time=False
        error_log = e
    except OSError as e:
        error_log = e
    if ds and not ds.coords:
        erdapp_uglyness = list(dict(xr.open_dataset(url).dims).keys())[0]
        renamed_vars = {i:i.replace(erdapp_uglyness+".", "") for i in list(xr.open_dataset(url).variables.keys())}
        new_nc_url = url+'?'+'time,'+','.join(list(xr.open_dataset(url).variables)).replace(f"{erdapp_uglyness}.", "").replace(f"time,", "")
        del ds
        gc.collect()
        ds = xr.open_dataset(new_nc_url)
        ds = ds.set_coords(f"{erdapp_uglyness}.time")
        ds = ds.swap_dims(s=f"time")
        ds = ds.set_xindex(f"{erdapp_uglyness}.time")
        ds = ds.rename_vars(renamed_vars)
   
    vars = ds.coords[list(ds.coords)[0]].values
    if 'featureType' in ds.attrs:
        featureType = ds.attrs['featureType'].lower()
    elif 'cdm_data_type' in ds[vars[0]].attrs:
        featureType = ds[vars[0]].attrs['cdm_data_type'].lower()
    else:
        featureType = None
    if featureType == 'timeseries':
        monotonic = is_monotonic(ds)
    else:
        monotonic = None
    return ds, decoded_time, error_log, monotonic, featureType


def show_hide_widget(event=None, widget=None):
    """Toggle visibility of a download widget.

    Accepts either an event (from `.on_click`) or a widget object passed directly
    via the `widget` keyword. Falls back to the global `downloader` if neither
    is available.
    """
    # determine the target widget to toggle
    target = widget
    if target is None:
        # event may be a Bokeh/Panel event with different attributes
        try:
            target = getattr(event, 'obj', None) or getattr(event, 'sender', None)
        except Exception:
            print("first exception in show_hide_widget")
            target = None
    # if target is None:
    #     # final fallback to the global downloader
    #     target = downloader

    # try:
    #     result = [key for key, value in mapping_var_names.items() if value == variables_selector.value]
    # except Exception:
    #     print("second exception in show_hide_widget")
    #     result = None

    # hide export resampling option if the dataset does not have a time coord
    # try:
    #     time_dim = [i for i in ds.coords if ds.coords.dtypes[i] == np.dtype('<M8[ns]')][0]
    #     if result and time_dim not in ds[result].indexes:
    #         export_resampling.visible = False
    # except Exception:
    #     print("third exception in show_hide_widget")
    #     # if anything goes wrong, silently skip adjusting resampling visibility
    #     pass

    try:
        if target.visible:
            target.visible = False
        else:
            # This will not work,
            # metadata_button.on_click(functools.partial(show_hide_widget, widget=metadata_layout))
            # needs to be changed to use functools.partial to pass both widget directly, 
            # the one being revealed and the one to be hidden
            # ensure metadata is hidden when showing the downloader
            # try:
            #     metadata_layout.visible = False
            # except Exception:
            #     print("fourth exception in show_hide_widget")
            #     pass
            target.visible = True
    except Exception:
        print("fifth exception in show_hide_widget")
        # best-effort toggle: if the target doesn't have .visible, ignore
        pass

def build_download_widget(ds, mapping_var_names, frequency_selector=True):
    """docstring"""  
    event_log = Div(text=f"""<br><br> <br><br>""")
    try:
        var_coord = [i for i in ds.coords if ds.coords.dtypes[i] == np.dtype('<M8[ns]')]
        time_coord = True
    except:
        time_coord = False
        var_coord = list(ds.coords)
    try:
        time_dim = var_coord[0]
        date_time_range_slider = pn.widgets.DatetimeRangeSlider(
            name='Date Range',
            start=ds.coords[time_dim].values.min(), end=ds.coords[time_dim].values.max(),
            value=(ds.coords[time_dim].values.min(), ds.coords[time_dim].values.max())        )
        export_resampling_option = pn.widgets.RadioButtonGroup(name='Resamplig', 
                                              options=['Raw', 'Resampled'])  
    except:
        date_time_range_slider = Div(text=f"""<br><br> Time Dimension not available """)
        export_resampling_option = Div(text=f"""<br><br> Resampling disabled """)
    checkbox_group = pn.FlexBox(*[pn.widgets.Checkbox(name=str(i)) for i in mapping_var_names.keys()])
    select_output_format = pn.widgets.Select(name='Export Format', options=['NetCDF', 'CSV', 'Parquet'])
    
    select_output_format_mapping = {'NetCDF':'nc', 'CSV':'csv', 'Parquet':'pq'}
    
    export_button = Button(
        label="Export",
        height=30,
        width=120,
    )  
    # export_button.on_click(show_hide_export_widget)
    
    
    export_options_button = Button(
        label="Download",
        height=30,
        width_policy='fit'
        # width=30,
    )  # , width_policy='fixed'
    # export_options_button.on_click(export_selection)
    if not frequency_selector: 
        export_resampling_option.visible = False
    
    return export_button, checkbox_group, date_time_range_slider, export_options_button, event_log, select_output_format, export_resampling_option


def build_metadata_widget(attrs):
    metadata_text = dict_to_html_ul(attrs)
    metadata_layout = pn.Row(Spacer(width=10), pn.Column(Spacer(height=120),
                                                Div(text=f'<font size = "2" color = "darkslategray" ><b>Metadata<b></font> {metadata_text}'), 
                                                width=400, sizing_mode='fixed'))
    
    metadata_layout.visible = False

    metadata_button = Button(
        label="Metadata",
        height=30,
        width=120,
    )  # , width_policy='fixed'
    # metadata_button.on_click(show_hide_metadata_widget)
    return metadata_layout, metadata_button


# def build_download_widget(ds, mapping_var_names, frequency_selector):
#     export_resampling_option = pn.widgets.RadioButtonGroup(name='Resamplig', 
#                                               options=['Raw', 'Resampled'])    
#     event_log = Div(text=f"""<br><br> <br><br>""")
#     try:
#         time_dim = var_coord[0]
#         date_time_range_slider = pn.widgets.DatetimeRangeSlider(
#             name='Date Range',
#             start=ds.coords[time_dim].values.min(), end=ds.coords[time_dim].values.max(),
#             value=(ds.coords[time_dim].values.min(), ds.coords[time_dim].values.max())        )
#     except:
#         date_time_range_slider = Div(text=f"""<br><br> Time Dimension not available """)
    
#     checkbox_group = pn.FlexBox(*[pn.widgets.Checkbox(name=str(i)) for i in mapping_var_names.keys()])
#     select_output_format = pn.widgets.Select(name='Export Format', options=['NetCDF', 'CSV', 'Parquet'])
    
#     select_output_format_mapping = {'NetCDF':'nc', 'CSV':'csv', 'Parquet':'pq'}
    
#     export_button = Button(
#         label="Export",
#         height=30,
#         width=120,
#     )  
#     # export_button.on_click(show_hide_export_widget)
    
    
#     export_options_button = Button(
#         label="Download",
#         height=30,
#         width_policy='fit'
#         # width=30,
#     )  # , width_policy='fixed'
#     export_options_button.on_click(export_selection)
#     if not frequency_selector: 
#         export_resampling_option.visible = False
    
#     return export_button, checkbox_group, date_time_range_slider, export_options_button, event_log, select_output_format, export_resampling_option