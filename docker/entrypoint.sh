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
# /OGC_client /seaice/daily /seaice/monthly /seaicemod/monthlymod /anymap
panel serve --port ${PORT} --cookie-secret my_super_safe_cookie_secret --address 0.0.0.0 --log-level ${LOG_LEVEL} --index /assets/custom_index.html --static-dirs assets=/assets --allow-websocket-origin='*'  /TSP /TRJ --index-titles /TSP="NC-Visualization Tool" /TRJ="Trajectory"
# /OGC_client="OGC Client" /daily="Sea Ice Daily" /monthly="Sea Ice Monthly" /monthlymod="Sea Ice Model" /anymap="Anymap"
