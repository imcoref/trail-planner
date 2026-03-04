"""
Trail Weather App – Map Builder Module
Constructs the Folium map with trail routes, mile markers, and POIs.
"""

import os
import folium
import numpy as np


def find_nearest_index(lat, lon, df):
    """Find the index of the nearest point in a DataFrame."""
    distances = np.sqrt(
        (df["latitude"] - lat) ** 2 + (df["longitude"] - lon) ** 2
    )
    return distances.idxmin()


def build_trail_map(
    route_df,
    mm_range_coords=None,
    mm_df=None,
    show_mm=False,
    direction="NOBO",
    poi_df=None,
    show_poi=False,
    emblem_image=None,
    route_coords=None,
):
    """Build a Folium map with the trail and optional overlays."""

    mean_lat = route_df["latitude"].mean()
    mean_lon = route_df["longitude"].mean()

    if mm_range_coords:
        m = folium.Map(zoom_start=9)  
        
        folium.TileLayer("OpenTopoMap").add_to(m)
        folium.TileLayer("OpenStreetMap").add_to(m)
        
    else:
        m = folium.Map(location=[mean_lat, mean_lon], zoom_start=7)
        
        folium.TileLayer("OpenTopoMap").add_to(m)
        folium.TileLayer("OpenStreetMap").add_to(m)

    # Full trail route (grey) — use pre-simplified coords if provided
    if route_coords is None:
        # Fallback: simplify on the fly
        step = max(1, len(route_df) // 800)
        subset = route_df.iloc[::step]
        route_coords = list(zip(subset["latitude"], subset["longitude"]))
    folium.PolyLine(route_coords, weight=4, color="#eb25d1", opacity=1).add_to(m)

    # Highlighted range (bold blue)
    if mm_range_coords:
        folium.PolyLine(
            mm_range_coords, weight=10, color="#2563eb", opacity=0.85
        ).add_to(m)
        m.fit_bounds(mm_range_coords)

    # Mile Markers
    if show_mm and mm_df is not None:
        for _, row in mm_df.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=5,
                color="#ef4444",
                fill=True,
                fill_color="#ef4444",
                fill_opacity=0.8,
                tooltip=f"{direction} Mile {row['mile_marker']}",
            ).add_to(m)

    # POIs
    if show_poi and poi_df is not None:
        for _, row in poi_df.iterrows():
            if emblem_image and os.path.isfile(emblem_image):
                icon = folium.CustomIcon(
                    emblem_image, icon_size=(22, 22),
                    icon_anchor=(1, 22), popup_anchor=(-3, -76),
                )
            else:
                icon = folium.Icon(color="green", icon="info-sign")

            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                popup=folium.Popup(f"<b>{row['name']}</b>", max_width=300),
                tooltip=row["name"],
                icon=icon,
            ).add_to(m)

    folium.LayerControl().add_to(m)
    return m


def calculate_range_coords(route_df, mm_df, start_mm, end_mm):
    """Calculate the route section between two mile markers."""
    start_row = mm_df[mm_df["mile_marker"] == start_mm].iloc[0]
    end_row = mm_df[mm_df["mile_marker"] == end_mm].iloc[0]

    start_idx = find_nearest_index(start_row["latitude"], start_row["longitude"], route_df)
    end_idx = find_nearest_index(end_row["latitude"], end_row["longitude"], route_df)

    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx

    selected = route_df.iloc[start_idx : end_idx + 1]
    return list(zip(selected["latitude"], selected["longitude"]))
