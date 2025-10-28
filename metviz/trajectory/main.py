"""Interactive map demo used by the ADC NC-CF Data Visualization project.

This module builds a simple ipyleaflet map wrapped in a Panel template and
provides UI widgets for:

- Loading WMS layers by providing a GetCapabilities URL.
- Adding draggable markers to the map and editing marker properties.
- Managing removable layers (markers and WMS layers) via a layer manager.

The UI is assembled using Panel and ipyleaflet and expects the following
optional external dependencies at runtime: `owslib`, `ipywidgets`, and
`ipyleaflet`.

This file is intended for exploratory/demo use and is kept small and
imperative; functions are documented with docstrings to aid maintenance.
"""

from turtle import title
from ipywidgets import HTML

from ipyleaflet import Map, Marker, Popup, LayersControl, GeoJSON

import panel as pn

pn.extension("ipywidgets", sizing_mode="stretch_width")

from ipyleaflet import Map, Marker

ACCENT_BASE_COLOR = "#003366"

import owslib.wms

# --- WMS GetCapabilities UI ---

from ipyleaflet import WMSLayer
from ipyleaflet import projections

# Local helper to generate a random geojson line
from genline import create_random_geojson_line

# --- WMS GetCapabilities UI ---

wms_toggle = pn.widgets.Toggle(name="Show WMS Loader", button_type="primary", value=False)

wms_url_input = pn.widgets.TextInput(name="WMS GetCapabilities URL", placeholder="Enter WMS URL")
wms_ok_button = pn.widgets.Button(name="OK", button_type="success")
wms_layers_pane = pn.pane.Markdown("", height=100, sizing_mode="stretch_width")
wms_error_pane = pn.pane.Alert("", alert_type="danger", visible=False)
wms_layers_selector = pn.widgets.CheckBoxGroup(name="Available WMS Layers", options=[], visible=False)
wms_add_button = pn.widgets.Button(name="Add Selected Layer(s) to Map", button_type="primary", visible=False)

def load_wms_layers(event):
    """Load WMS GetCapabilities from the URL in the widget.

    This function reads the URL entered in `wms_url_input` and attempts to
    parse the WMS GetCapabilities document using `owslib.wms.WebMapService`.

    On success it populates `wms_layers_pane` with a markdown list of
    available layers and fills `wms_layers_selector.options` with tuples
    (label, layer_name) so the user can choose layers to add to the map.

    On failure the function displays an error message in
    `wms_error_pane` and hides the selector and add button.

    Args:
        event: Panel click event (ignored; present to wire up as a callback).
    """
    url = wms_url_input.value.strip()
    if not url:
        wms_error_pane.object = "Please enter a WMS GetCapabilities URL."
        wms_error_pane.visible = True
        wms_layers_pane.object = ""
        wms_layers_selector.visible = False
        wms_add_button.visible = False
        return
    try:
        wms = owslib.wms.WebMapService(url)
        layers_md = "### Available WMS Layers\n"
        options = []
        for layer_name, layer in wms.contents.items():
            # Label for user, value for logic
            label = f"{layer_name}: {layer.title or ''}"
            options.append((label, layer_name))  # value is only layer_name
            layers_md += f"- **{layer_name}**: {layer.title or ''}\n"
        # Add other WMS options
        layers_md += "\n**WMS Version:** " + wms.version
        layers_md += "\n**Service Title:** " + (wms.identification.title or "")
        wms_layers_pane.object = layers_md
        wms_layers_selector.options = options
        wms_layers_selector.visible = True
        wms_add_button.visible = True
        wms_error_pane.visible = False
    except Exception as e:
        wms_error_pane.object = f"Error loading WMS: {e}"
        wms_error_pane.visible = True
        wms_layers_pane.object = ""
        wms_layers_selector.visible = False
        wms_add_button.visible = False

wms_ok_button.on_click(load_wms_layers)

def add_selected_wms_layers(event):
    """Add the user-selected WMS layers to the map.

    Reads the selected layer names from `wms_layers_selector` and creates
    an `ipyleaflet.WMSLayer` for each selected layer. The created layers are
    added to the global `lmap` object.

    Args:
        event: Panel click event (ignored; present to wire up as a callback).
    """
    url = wms_url_input.value.strip()
    selected_layers = wms_layers_selector.value
    if not url or not selected_layers:
        return
    # Use a CORS proxy for the WMS URL
    proxy_url = "https://corsproxy.io/?" + url
    for layer_name in selected_layers:
        layer_name = layer_name[1]  # Extract actual layer name
        wms_layer = WMSLayer(
            url=url,
            layers=layer_name,
            crs=projections.EPSG4326, 
            name=layer_name,
            transparent=True,
            format="image/png"
        )
        lmap.add_layer(wms_layer)

wms_add_button.on_click(add_selected_wms_layers)

wms_dialog = pn.Column(
    wms_url_input,
    wms_ok_button,
    wms_error_pane,
    # wms_layers_pane,
    wms_layers_selector,
    wms_add_button,
    visible=False,
    margin=(10, 10),
    sizing_mode="stretch_width"
)


def toggle_wms_dialog(event):
    """Toggle visibility of the WMS configuration dialog.

    Args:
        event: Panel widget change event (ignored; used as a watcher callback).
    """
    wms_dialog.visible = wms_toggle.value

wms_toggle.param.watch(toggle_wms_dialog, 'value')


def get_marker_and_map():
    """Create the initial ipyleaflet Map and a main draggable Marker.

    Returns:
        tuple: (marker, lmap) where `marker` is the main Marker instance and
        `lmap` is the ipyleaflet Map instance configured for the demo.
    """
    center = (52.204793, 360.121558)

    lmap = Map(center=center, zoom=15, height=500)

    marker = Marker(location=center, draggable=True)
    # Add custom properties
    marker.name = "Main Marker"
    marker.description = "This is a draggable marker."
    #
    lmap.add_layer(marker)
    lmap.layout.height="100%"
    lmap.layout.width="100%"
    lmap.add_control(LayersControl(position='topright'))
    return marker, lmap

marker, lmap = get_marker_and_map()


json_widget = pn.pane.JSON({}, height=75)


checkbox = pn.widgets.Checkbox(name="Enable Add Marker", value=False)
pick_line_checkbox = pn.widgets.Checkbox(name="Pick point for line", value=False)

def print_marker_properties(event, marker_obj):
    """Callback invoked when a marker's location changes.

    Updates the `json_widget` pane with the marker's current properties and
    prints the updated values to stdout (useful for debugging in notebooks).

    Args:
        event (dict): Event payload from ipyleaflet containing a 'new'
            key with the new (lat, lon) location.
        marker_obj (Marker): The marker instance whose properties are shown.
    """
    new = event["new"]
    print(f"Marker Name: {marker_obj.name}")
    print(f"Marker Description: {marker_obj.description}")
    print(f"New Location: {new}")
    # Update the json_widget with marker properties
    json_widget.object = {
        "x": new[0],
        "y": new[1],
        "name": marker_obj.name,
        "description": marker_obj.description
    }

# Attach observer to main marker to print and update json_widget when dragged
marker.observe(lambda event, m=marker: print_marker_properties(event, m), 'location')

# Panel widgets for editing marker properties
marker_name_input = pn.widgets.TextInput(name="Marker Name", value="")
marker_desc_input = pn.widgets.TextInput(name="Marker Description", value="")
save_button = pn.widgets.Button(name="Save Marker Properties", button_type="primary")

edit_panel = pn.Column(marker_name_input, marker_desc_input, save_button, visible=False)
current_marker = [None]  # Use a list for mutability in nested scope

# Holder for a single generated line layer so we can remove/replace it
generated_line_layer = [None]
# Hold the list of coordinates for the last generated line (list of [lon, lat])
generated_line_coords = []
# Slider to select a vertex index on the generated line
vertex_slider = pn.widgets.IntSlider(name="Vertex index", start=0, end=0, step=1, value=0, visible=False)
# Holder for the currently shown vertex marker so we can remove it when the slider moves
animated_vertex_marker = [None]

def _place_vertex_marker(index):
    """Place a single marker at the given vertex index of the generated line.

    Removes any previously placed animated marker before adding the new one.
    """
    # remove previous animated marker
    if animated_vertex_marker[0] is not None:
        while animated_vertex_marker[0] in lmap.layers:
            lmap.remove_layer(animated_vertex_marker[0])
        animated_vertex_marker[0] = None

    if not generated_line_coords:
        return

    # clamp index
    idx = max(0, min(index, len(generated_line_coords) - 1))
    lon, lat = generated_line_coords[idx]
    m = Marker(location=(lat, lon), draggable=False)
    m.name = f"Vertex {idx}"
    m.description = f"Vertex {idx} of generated line"
    lmap.add_layer(m)
    animated_vertex_marker[0] = m
    update_layer_manager()

def _on_slider_change(event):
    # Panel uses 'value' param watch which provides old/new values
    try:
        new_index = event.new
    except AttributeError:
        new_index = event
    _place_vertex_marker(new_index)

vertex_slider.param.watch(_on_slider_change, 'value')

def show_edit_panel(marker):
    """Populate the edit panel with the selected marker's properties.

    The edit panel contains text inputs to edit the marker's name and
    description. The selected marker is stored in `current_marker[0]` for
    later saving.

    Args:
        marker (Marker): The marker to edit.
    """
    marker_name_input.value = marker.name if hasattr(marker, "name") else ""
    marker_desc_input.value = marker.description if hasattr(marker, "description") else ""
    edit_panel.visible = True
    current_marker[0] = marker

def save_marker_properties(event):
    """Save edited marker properties back to the marker instance.

    Removes any existing instances of the marker from the map to avoid
    duplication, updates the `name` and `description` attributes, re-adds
    the marker to the map and updates the JSON widget and layer manager.

    Args:
        event: Button click event (ignored; present to wire up as a callback).
    """
    print("current_marker:", current_marker)
    marker = current_marker[0]
    if marker:
        # lmap.remove_layer(current_marker[1])
        # Remove all occurrences to avoid duplicates
        while marker in lmap.layers:
            lmap.remove_layer(marker)
        remove_layer(marker)
        print(f"Removing marker at {marker.location} to update properties.")
        marker.name = marker_name_input.value
        marker.description = marker_desc_input.value
        lmap.add_layer(marker)
        print(f"Saved properties for marker at {marker.location}:")
        print(f"  Name: {marker.name}")
        print(f"  Description: {marker.description}")
        edit_panel.visible = False
        json_widget.object = {
            "x": marker.location[0],
            "y": marker.location[1],
            "name": marker.name,
            "description": marker.description
        }
        marker.popup.value = f"""Hello <b>{marker.description}</b>"""
        update_layer_manager()  # <-- Update if you want to reflect name changes
  

def create_button_click(val):
    """Simple click handler used for debugging.

    Args:
        val: Value emitted by the widget click (logged to stdout).
    """
    print(val)
    

save_button.on_click(save_marker_properties)

def on_map_click(**kwargs):
    """Handle clicks on the map to create new markers when enabled.

    If the 'Enable Add Marker' checkbox is checked and the interaction type
    is a 'click', this function will create a new draggable marker at the
    clicked coordinates, attach a popup, register the movement observer,
    and open the edit panel for that marker.

    Args:
        **kwargs: Arbitrary interaction payload from ipyleaflet. Expected keys
            include 'type' and 'coordinates'.
    """
    # Priority: picking a point to generate a line if that mode is active
    if pick_line_checkbox.value and kwargs.get("type") == "click":
        latlng = kwargs.get("coordinates")
        if latlng:
            lat, lon = latlng[0], latlng[1]
            print(f"Picked point for line generation: {(lat, lon)}")
            # Generate a GeoJSON LineString starting at clicked point
            geojson = create_random_geojson_line(lat, lon, num_vertices=200, max_distance_meters=500)
            # Remove existing generated line if present
            if generated_line_layer[0] is not None:
                while generated_line_layer[0] in lmap.layers:
                    lmap.remove_layer(generated_line_layer[0])
            gj = GeoJSON(data=geojson, name="Generated Line")
            gj.name = "Generated Line"
            generated_line_layer[0] = gj
            lmap.add_layer(gj)
            # store coordinates for slider/marker playback (geojson coords are [lon, lat])
            generated_line_coords[:] = geojson.get('geometry', {}).get('coordinates', [])
            if generated_line_coords:
                # configure slider
                vertex_slider.start = 0
                vertex_slider.end = max(0, len(generated_line_coords) - 1)
                vertex_slider.value = 0
                vertex_slider.visible = True
                # place initial vertex marker
                _place_vertex_marker(0)
            else:
                vertex_slider.visible = False
            update_layer_manager()
            return

    # Fallback: add a marker when the marker mode is enabled
    if checkbox.value and kwargs.get("type") == "click":
        latlng = kwargs.get("coordinates")
        if latlng:
            marker = Marker(location=latlng, draggable=True)
            marker.name = f"Marker at {latlng}"
            marker.description = f"Marker at {latlng}"
            lmap.add_layer(marker)
            print(f"Added marker at {latlng}")
            marker.observe(lambda event, m=marker: print_marker_properties(event, m), 'location')
            message = HTML()
            message.placeholder = "Some HTML"
            message.description = "Some HTML"
            message.value = "Hello <b>World</b>"
            marker.popup = message
            show_edit_panel(marker)
            update_layer_manager()  # <-- Only update when a marker is added

lmap.on_interaction(on_map_click)  # Only once!


def add_selected_wms_layers(event):
    """(Re)defined helper to add selected WMS layers and refresh the manager.

    Note: This module contains a second definition of `add_selected_wms_layers`
    later in the file. This definition mirrors the earlier one but also
    calls `update_layer_manager()` after adding layers so the UI reflects
    the new entries.

    Args:
        event: Panel click event (ignored; present to wire up as a callback).
    """
    url = wms_url_input.value.strip()
    selected_layers = wms_layers_selector.value
    if not url or not selected_layers:
        return
    proxy_url = "https://corsproxy.io/?" + url
    for layer_name in selected_layers:
        wms_layer = WMSLayer(
            url=url,
            layers=layer_name,
            crs=projections.EPSG4326, 
            name=layer_name,
            transparent=True,
            format="image/png"
        )
        lmap.add_layer(wms_layer)
    update_layer_manager()  # <-- Only update when WMS layers are added

wms_add_button.on_click(add_selected_wms_layers)

# component = pn.Column(
#     checkbox,
#     pn.panel(lmap, sizing_mode="stretch_both", min_height=500),
#     pn.Row(json_widget, edit_panel)
# )
####

def get_removable_layers():
    """Return a deduplicated list of layers that can be removed by the UI.

    Excludes the primary `marker` and attempts to ensure uniqueness by a key
    constructed from the layer type and identifying attributes (location and
    name for markers, name for WMS layers).

    Returns:
        list: A list of ipyleaflet layer objects suitable for removal.
    """
    # Exclude the main marker and ensure uniqueness by (location, name)
    seen = set()
    unique_layers = []
    for lyr in lmap.layers:
        # Include markers (except the primary one), WMS layers and GeoJSON layers
        if ((isinstance(lyr, Marker) and lyr is not marker)
            or isinstance(lyr, WMSLayer)
            or isinstance(lyr, GeoJSON)):
            # Use (rounded lat, rounded lon, name) as a unique key
            if isinstance(lyr, Marker):
                key = (round(lyr.location[0], 6), round(lyr.location[1], 6), getattr(lyr, "name", ""))
            elif isinstance(lyr, WMSLayer):
                key = (getattr(lyr, "name", ""),)
            elif isinstance(lyr, GeoJSON):
                key = (getattr(lyr, "name", "GeoJSON"),)
            else:
                key = id(lyr)
            if key not in seen:
                unique_layers.append(lyr)
                seen.add(key)
    return unique_layers

def remove_layer(layer):
    """Remove the given layer from the map and refresh the layer manager.

    Repeatedly removes occurrences of the same layer object to handle
    accidental duplicates and then calls `update_layer_manager()` so the
    UI stays in sync.

    Args:
        layer: The ipyleaflet layer object to remove.
    """
    # If the removed layer is the generated line, clean up slider and animated marker
    if generated_line_layer[0] is layer:
        generated_line_layer[0] = None
        generated_line_coords[:] = []
        # remove the animated marker if present
        if animated_vertex_marker[0] is not None:
            while animated_vertex_marker[0] in lmap.layers:
                lmap.remove_layer(animated_vertex_marker[0])
            animated_vertex_marker[0] = None
        vertex_slider.visible = False

    # Remove all occurrences of this layer object (in case of duplicates)
    while layer in lmap.layers:
        lmap.remove_layer(layer)
    update_layer_manager()

def update_layer_manager(**kwargs):
    """Rebuild the layer manager UI to reflect the current removable layers.

    This function queries `get_removable_layers()` and constructs a list of
    rows containing the layer name and a Remove button wired to call
    `remove_layer()` for that layer.
    """
    # Clear and repopulate the layer manager panel
    removable_layers = get_removable_layers()
    items = []
    for lyr in removable_layers:
        lyr_name = getattr(lyr, "name", str(lyr))
        btn = pn.widgets.Button(name="Remove", button_type="danger", width=60)
        # Closure to capture current layer
        btn.on_click(lambda event, l=lyr: remove_layer(l))
        items.append(pn.Row(pn.pane.Markdown(f"**{lyr_name}**"), btn))
    layer_manager[:] = items

layer_manager = pn.Column(name="Layer Manager")
update_layer_manager()

# Update the manager whenever a marker or WMS layer is added
def add_marker_and_update(*args, **kwargs):
    """Helper used by external wiring to trigger a layer manager refresh.

    Kept for backwards compatibility with earlier wiring where an add
    operation would explicitly call this helper.
    """
    # on_map_click(*args, **kwargs)
    update_layer_manager()

def add_selected_wms_layers_and_update(event):
    """Convenience wrapper: add selected WMS layers then refresh manager.

    Provided so UI wiring can use a single handler that both adds layers and
    updates the layer manager pane.
    """
    add_selected_wms_layers(event)
    update_layer_manager()


component = pn.Column(
    pn.Row(checkbox, pick_line_checkbox),
    vertex_slider,
    pn.panel(lmap, sizing_mode="stretch_both", min_height=500),
    pn.Row(json_widget, pn.Column(edit_panel, wms_toggle, wms_dialog, pn.pane.Markdown("### Remove Layers"), layer_manager)),
)


template = pn.template.FastListTemplate(
    site=" ADC NC-CF Data Visualization ",
    # site_url="https://www.northwestknowledge.net/adc/",
    favicon="/assets/ADC_logo.png",
    title="Map Widget Demo",
    logo="/assets/ADC_logo.png",
    header_background=ACCENT_BASE_COLOR,
    accent_base_color=ACCENT_BASE_COLOR,
    main=[component],
).servable()