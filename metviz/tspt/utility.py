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
from pydantic import BaseModel, AnyHttpUrl
import base64
import re
from itsdangerous import TimestampSigner
import uuid
from pathlib import Path
import os
import json
import requests


pandas_frequency_offsets = {
            "Hourly": "h",
            "Calendar day": "D",
            "Weekly": "W",
            "Month end": "ME",
            "Quarter end": "QE",
            "Yearly": "YE",
        }

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
    
    
def generate_download_string():
    """_summary_

    Args:
        df (_type_): _description_
        filename (_type_): _description_
        title (_type_): _description_

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
from pydantic import BaseModel, AnyHttpUrl
import base64
import re
from itsdangerous import TimestampSigner
import uuid
from pathlib import Path
import os
import json
import requests


pandas_frequency_offsets = {
            "Hourly": "h",
            "Calendar day": "D",
            "Weekly": "W",
            "Month end": "ME",
            "Quarter end": "QE",
            "Yearly": "YE",
        }

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
