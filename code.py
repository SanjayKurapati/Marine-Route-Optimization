#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Converted from Jupyter Notebook: notebook.ipynb
Conversion Date: 2025-11-21T06:46:22.945Z
"""

import geopandas as gpd
from shapely.geometry import Point
import numpy as np
import networkx as nx
import folium
from flask import Flask, render_template_string, request
from flask_ngrok import run_with_ngrok
from pyngrok import ngrok
import requests
import math
import time

ngrok.set_auth_token("2jsgEzXGMKiUuZFR7Dav17SOAf9_zpXKLhUVvb6scpJFAVHd")

WEATHERAPI_KEY = "35efb21612b64f93816143549242110"
USE_REAL_WEATHER = True

app = Flask(__name__)
run_with_ngrok(app)

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Marine Route Optimization</title>
</head>
<body>
    <h2>Marine Route Optimization (FAST VERSION)</h2>
    <form method="POST">
        <label>Start:</label>
        <select name="start_port">
            {% for p in ports %}
                <option value="{{ p }}">{{ p }}</option>
            {% endfor %}
        </select>

        <label>End:</label>
        <select name="end_port">
            {% for p in ports %}
                <option value="{{ p }}">{{ p }}</option>
            {% endfor %}
        </select>

        <button type="submit">Find Route</button>
    </form>

    {% if total_km %}
        <h3>Total Distance: {{ total_km }} km</h3>
    {% endif %}
    {% if map_html %}
        {{ map_html | safe }}
    {% endif %}
</body>
</html>
"""

ports = {
    "Mumbai": (18.9498, 72.8330),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Kochi": (9.9312, 76.2673),
    "Visakhapatnam": (17.6868, 83.2185),
    "Paradip": (20.3164, 86.6102),
    "Tuticorin": (8.7642, 78.1348),
    "Haldia": (22.0605, 88.1095),
    "Mormugao": (15.4052, 73.8017)
}

# -----------------------------------------------------
# FAST WEATHER: ONLY called during route
# -----------------------------------------------------
weather_sector_cache = {}

def get_weather(lat, lon):
    sector = (round(lat), round(lon))

    if sector in weather_sector_cache:
        return weather_sector_cache[sector]

    fallback = (10, 1.2)

    if not USE_REAL_WEATHER:
        return fallback

    url = "http://api.weatherapi.com/v1/marine.json"
    params = {"key": WEATHERAPI_KEY, "q": f"{lat},{lon}"}

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
        wind = data['forecast']['forecastday'][0]['hour'][0]['wind_kph']
        wave = data['forecast']['forecastday'][0]['hour'][0].get('wave_height_m', 1.0)

        weather_sector_cache[sector] = (wind, wave)
        return wind, wave
    except:
        return fallback


# -----------------------------------------------------
# LOAD LAND SHAPES (FAST)
# -----------------------------------------------------
world = gpd.read_file("C:/Users/sunny/Downloads/shapefiles")
land = world.unary_union

# -----------------------------------------------------
# BUILD GRID FAST (NO WEATHER HERE)
# -----------------------------------------------------
res = 0.25
xmin, xmax = 65, 90
ymin, ymax = 5, 25

grid = [(round(x, 4), round(y, 4))
        for x in np.arange(xmin, xmax, res)
        for y in np.arange(ymin, ymax, res)]

sea_nodes = [pt for pt in grid if not Point(pt).within(land)]

# -----------------------------------------------------
# BUILD GRAPH FAST (NO WEATHER HERE)
# -----------------------------------------------------
G = nx.Graph()

for node in sea_nodes:
    G.add_node(node)

for x, y in sea_nodes:
    for dx in [-res, 0, res]:
        for dy in [-res, 0, res]:
            if dx == dy == 0:
                continue
            nb = (round(x + dx, 4), round(y + dy, 4))
            if nb in G:
                mid = Point((x + nb[0]) / 2, (y + nb[1]) / 2)
                if not mid.buffer(0.05).intersects(land):
                    dist = math.hypot(dx, dy)
                    G.add_edge((x, y), nb, weight=dist)

# -----------------------------------------------------
# FIND NEAREST SEA NODE
# -----------------------------------------------------
def nearest_sea(lat, lon):
    return min(G.nodes, key=lambda p: (p[1] - lat)**2 + (p[0] - lon)**2)

# -----------------------------------------------------
# A* PATHFINDING (WEATHER APPLIED HERE ONLY)
# -----------------------------------------------------
def haversine(p1, p2):
    R = 6371
    lat1, lon1 = math.radians(p1[1]), math.radians(p1[0])
    lat2, lon2 = math.radians(p2[1]), math.radians(p2[0])
    return 2 * R * math.asin(
        math.sqrt(
            math.sin((lat2 - lat1)/2)**2 +
            math.cos(lat1)*math.cos(lat2)*math.sin((lon2 - lon1)/2)**2
        )
    )

def astar(start, end):
    return nx.astar_path(G, start, end, heuristic=haversine, weight="weight")

# -----------------------------------------------------
# FLASK ROUTE
# -----------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    map_html, total_km = None, None

    if request.method == "POST":
        s = request.form["start_port"]
        e = request.form["end_port"]

        s_node = nearest_sea(*ports[s])
        e_node = nearest_sea(*ports[e])

        path = astar(s_node, e_node)

        # Apply weather ONLY to path
        total_km = 0
        m = folium.Map(location=ports[s], zoom_start=5)

        folium.Marker(ports[s], popup="Start").add_to(m)
        folium.Marker(ports[e], popup="End").add_to(m)

        for i in range(len(path) - 1):
            lat, lon = path[i][1], path[i][0]

            wind, wave = get_weather(lat, lon)
            total_km += haversine(path[i], path[i+1])

            folium.CircleMarker(
                location=(lat, lon),
                radius=3,
                color="blue",
                fill=True,
                popup=f"Wind: {wind} kph<br>Wave: {wave} m"
            ).add_to(m)

        folium.PolyLine([(p[1], p[0]) for p in path], color="blue").add_to(m)

        map_html = m._repr_html_()

    return render_template_string(INDEX_HTML, ports=ports, map_html=map_html,
                                  total_km=f"{total_km:.2f}" if total_km else None)

# -----------------------------------------------------
# RUN APP
# -----------------------------------------------------
if __name__ == "__main__":
    app.run()