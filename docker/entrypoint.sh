#!/bin/bash
LOG_LEVEL=${LOG_LEVEL:-debug}

# cryo colorscheme
## light #beb9d7   
## dark #464769 

panel serve --port ${PORT} --basic-auth /credentials.json --cookie-secret my_super_safe_cookie_secret --autoreload --address 0.0.0.0 --log-level ${LOG_LEVEL} --index /assets/custom_index.html --static-dirs assets=/assets --allow-websocket-origin="ows.terrestris.de" /trajectory /tspt /OGC_client /seaice/daily /seaice/monthly --index-titles /map="Trajectory widget" /tspt="Time Series Profile Tool" /csw="OGC Client" /daily="Sea Ice Daily" /monthly="Sea Ice Monthly"
