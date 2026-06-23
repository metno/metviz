#!/bin/bash
LOG_LEVEL=${LOG_LEVEL:-debug}

# Serve the Panel apps under a path prefix when mounted behind a proxy
# (PANEL_PREFIX=/panel in production). Unset in dev -> served at the root.
PREFIX_ARG=""
if [ -n "${PANEL_PREFIX}" ]; then
  PREFIX_ARG="--prefix ${PANEL_PREFIX}"
fi

# WebSocket origin allow-list. PANEL_ALLOW_ORIGIN may hold several space-
# separated hosts; each becomes its own --allow-websocket-origin flag. Default
# '*' allows any origin (dev/VPN). In production pin to the public host(s), e.g.:
#   PANEL_ALLOW_ORIGIN="metviz.metsis-dev.k8s.met.no 192.168.12.115"
ORIGIN_ARGS=""
set -f  # disable globbing so a bare '*' is passed literally, not expanded to files
for _o in ${PANEL_ALLOW_ORIGIN:-*}; do
  ORIGIN_ARGS="${ORIGIN_ARGS} --allow-websocket-origin=${_o}"
done
set +f

# cryo colorscheme
## light #beb9d7   
## dark #464769 

# --basic-auth /credentials.json
# /mapdap /mapdap="Trajectory Loader"
# /map="Trajectory widget"
# /trajectory
# /tspt
# /OGC_client /seaice/daily /seaice/monthly /seaicemod/monthlymod /anymap
# Behind a TLS-terminating proxy: --use-xheaders makes Bokeh honor
# X-Forwarded-Proto/Host (so it emits wss:// + the public host). The allowed
# WebSocket origin defaults to '*' (dev/VPN); in production set
# PANEL_ALLOW_ORIGIN to the public host, e.g. metviz.metsis-dev.k8s.met.no.
panel serve ${PREFIX_ARG} --use-xheaders --autoreload --port ${PORT} --cookie-secret my_super_safe_cookie_secret --address 0.0.0.0 --log-level ${LOG_LEVEL} --index /assets/custom_index.html --static-dirs assets=/assets ${ORIGIN_ARGS}  /TSP /TRJ /Catalog /OGC_client --index-titles /TSP="NC-Visualization Tool" /TRJ="Trajectory" /Catalog="Search Catalog" /OGC_client="OGC Client"
# /OGC_client="OGC Client" /daily="Sea Ice Daily" /monthly="Sea Ice Monthly" /monthlymod="Sea Ice Model" /anymap="Anymap"
