#!/bin/bash
LOG_LEVEL=${LOG_LEVEL:-debug}

# cryo colorscheme
## light #beb9d7   
## dark #464769 

# --basic-auth /credentials.json
# /mapdap /mapdap="Trajectory Loader"
# /map="Trajectory widget"
# /trajectory
# /tspt
panel serve --port ${PORT} --cookie-secret my_super_safe_cookie_secret --autoreload --address 0.0.0.0 --log-level ${LOG_LEVEL} --index /assets/custom_index.html --static-dirs assets=/assets --allow-websocket-origin='*'  /TSP /trj /OGC_client /seaice/daily /seaice/monthly /seaicemod/monthlymod  --index-titles /TSP="NC-Visualization Tool" /trj="trj" /csw="OGC Client" /daily="Sea Ice Daily" /monthly="Sea Ice Monthly" /monthlymod="Sea Ice Model"
