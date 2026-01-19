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
import random
import math
from geopy.distance import geodesic

def create_random_geojson_line(start_lat, start_lon, num_vertices=1000, max_distance_meters=500):
    """
    Generates a GeoJSON LineString feature from a starting position
    with each subsequent vertex being randomly placed within a
    specified distance of the previous one.

    Args:
        start_lat (float): The starting latitude.
        start_lon (float): The starting longitude.
        num_vertices (int): The number of vertices (points) to generate.
        max_distance_meters (int): The maximum distance in meters between consecutive vertices.

    Returns:
        dict: A dictionary representing the GeoJSON LineString Feature.
    """
    coords = []
    current_lat, current_lon = start_lat, start_lon

    for _ in range(num_vertices):
        # Add the current point to the list of coordinates
        coords.append([current_lon, current_lat])

        # Convert meters to approximate degrees for a radial distance
        # 1 degree of latitude is about 111,320 meters.
        # 1 degree of longitude depends on the latitude.
        # For simplicity, we can use an approximation assuming a constant degree size
        # and checking the final distance with geopy.
        distance_deg = max_distance_meters / 111320.0

        while True:
            # Generate a random distance and angle for the next point
            random_dist = random.uniform(0, max_distance_meters)
            random_angle = random.uniform(0, 2 * math.pi)

            # Calculate the new point using polar coordinates
            # This is a simplified calculation that works well for small distances
            # but is not perfectly accurate for long-distance spherical geometry.
            delta_lat = (random_dist / 111320.0) * math.cos(random_angle)
            delta_lon = (random_dist / (111320.0 * math.cos(math.radians(current_lat)))) * math.sin(random_angle)

            new_lat = current_lat + delta_lat
            new_lon = current_lon + delta_lon
            
            # Verify the distance with a precise method
            if geodesic((current_lat, current_lon), (new_lat, new_lon)).meters <= max_distance_meters:
                current_lat, current_lon = new_lat, new_lon
                break

    # Construct the GeoJSON object
    geojson = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        }
    }
    return geojson

# # Example usage
# start_latitude = 59.9139  # Bergen, Norway
# start_longitude = 10.7522
# geojson_line = create_random_geojson_line(start_latitude, start_longitude)

# import json
# print(json.dumps(geojson_line, indent=2))