"""
Trail Weather App – GPX Upload Handler
Converts uploaded GPX files to trackpoints + mile markers on the fly.
"""

import os
import tempfile
import gpxpy
import pandas as pd
import numpy as np
from pyproj import Geod

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "trail_weather_uploads")


def process_gpx_upload(uploaded_file, trail_name, mile_interval=10):
    """Process an uploaded GPX file and return trail data paths.

    Returns a dict with keys: trackpoints_df, mm_nobo_df, mm_sobo_df, trail_name
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Parse GPX
    gpx = gpxpy.parse(uploaded_file.getvalue().decode("utf-8"))

    data = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                row = {
                    "track_name": track.name or trail_name,
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                }
                if point.elevation is not None:
                    row["elevation"] = point.elevation
                data.append(row)

    if not data:
        return None

    trackpoints_df = pd.DataFrame(data)

    # Calculate mile markers (NOBO = as-is, SOBO = reversed)
    mm_nobo_df = _calculate_milemarkers(trackpoints_df, mile_interval, reverse=False)
    mm_sobo_df = _calculate_milemarkers(trackpoints_df, mile_interval, reverse=True)

    return {
        "trackpoints_df": trackpoints_df,
        "mm_nobo_df": mm_nobo_df,
        "mm_sobo_df": mm_sobo_df,
        "trail_name": trail_name,
    }


def _calculate_milemarkers(df, interval_miles, reverse=False):
    """Calculate mile marker positions along the trail."""
    interval_meters = float(interval_miles) * 1609.344
    geod = Geod(ellps="WGS84")

    work_df = df.iloc[::-1].reset_index(drop=True) if reverse else df.copy()

    if len(work_df) < 2:
        return pd.DataFrame(columns=["mile_marker", "latitude", "longitude"])

    lats = work_df["latitude"].values
    lons = work_df["longitude"].values

    result = [{"mile_marker": 0, "latitude": lats[0], "longitude": lons[0]}]

    total_distance = 0.0
    next_target = interval_meters

    for i in range(1, len(work_df)):
        az12, _, seg_len = geod.inv(lons[i-1], lats[i-1], lons[i], lats[i])

        while total_distance + seg_len >= next_target:
            remaining = next_target - total_distance
            lon_new, lat_new, _ = geod.fwd(lons[i-1], lats[i-1], az12, remaining)
            result.append({
                "mile_marker": round(next_target / 1609.344),
                "latitude": lat_new,
                "longitude": lon_new,
            })
            next_target += interval_meters

        total_distance += seg_len

    return pd.DataFrame(result)
