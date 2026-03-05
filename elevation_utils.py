"""
Trail Weather App – Elevation Utilities
Provides elevation profiles, thru-hike planning with Naismith's Rule,
and elevation-adjusted daily pace calculations.
"""

import os
import pandas as pd
import numpy as np
import streamlit as st
from datetime import timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ─── Elevation Profile Loading ──────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=None)
def load_elevation_profile(trail_key: str) -> pd.DataFrame | None:
    """Load pre-computed elevation profile for a trail.
    Returns DataFrame with: distance_miles, latitude, longitude, elevation_m
    """
    path = os.path.join(DATA_DIR, trail_key, f"{trail_key}_elevation.csv")
    if not os.path.isfile(path):
        return None
    return pd.read_csv(path)


# ─── Elevation Stats Between Mile Markers ───────────────────────────

@st.cache_data(show_spinner=False, ttl=None)
def get_segment_elevation_stats(trail_key: str, direction: str) -> pd.DataFrame | None:
    """Calculate elevation gain/loss between consecutive mile markers.

    Uses the fine-grained elevation profile to sum up/down between MM positions.
    Returns DataFrame with columns:
      start_mm, end_mm, distance_mi, gain_m, loss_m, gain_ft, loss_ft
    """
    elev_profile = load_elevation_profile(trail_key)
    if elev_profile is None:
        return None

    mm_file = os.path.join(DATA_DIR, trail_key, f"{trail_key}_MM_points_list_{direction}.csv")
    if not os.path.isfile(mm_file):
        return None
    mm_df = pd.read_csv(mm_file)

    if "elevation_m" not in mm_df.columns:
        return None

    # Use the fine-grained elevation profile to compute cumulative gain/loss
    # between mile markers by mapping MM positions to profile distance
    profile_dist = elev_profile["distance_miles"].values
    profile_elev = elev_profile["elevation_m"].values
    max_profile_dist = profile_dist[-1]

    mms = mm_df["mile_marker"].values
    mm_elevs = mm_df["elevation_m"].values

    # For each pair of consecutive MMs, sum the ups and downs from the profile
    segments = []
    for i in range(len(mms) - 1):
        start_mm = mms[i]
        end_mm = mms[i + 1]
        dist = end_mm - start_mm

        # Map MM positions to approximate profile distance
        # MM 0 → profile dist 0, MM max → profile dist max
        total_trail_miles = mms[-1]
        frac_start = start_mm / total_trail_miles
        frac_end = end_mm / total_trail_miles
        d_start = frac_start * max_profile_dist
        d_end = frac_end * max_profile_dist

        # Get profile points in this range
        mask = (profile_dist >= d_start) & (profile_dist <= d_end)
        seg_elevs = profile_elev[mask]

        if len(seg_elevs) < 2:
            # Fallback to MM-level elevation
            gain = max(0, mm_elevs[i + 1] - mm_elevs[i])
            loss = max(0, mm_elevs[i] - mm_elevs[i + 1])
        else:
            diffs = np.diff(seg_elevs)
            gain = float(np.sum(diffs[diffs > 0]))
            loss = float(np.abs(np.sum(diffs[diffs < 0])))

        segments.append({
            "start_mm": start_mm,
            "end_mm": end_mm,
            "distance_mi": dist,
            "gain_m": round(gain),
            "loss_m": round(loss),
            "gain_ft": round(gain * 3.281),
            "loss_ft": round(loss * 3.281),
            "start_elev_m": mm_elevs[i],
            "end_elev_m": mm_elevs[i + 1],
        })

    return pd.DataFrame(segments)


# ─── Thru-Hike Planner ──────────────────────────────────────────────

def plan_thru_hike(
    mm_df: pd.DataFrame,
    segment_stats: pd.DataFrame | None,
    start_date,
    daily_pace: float,
    adjust_for_elevation: bool = True,
) -> list[dict]:
    """Plan a thru-hike day by day with a target daily mileage.
    
    Each day attempts to cover 'daily_pace' miles. If adjust_for_elevation is True,
    uses a simplified Naismith's Rule:
    - Every 600m (~2000ft) of elevation gain costs ~2 miles of effective distance
    - Every 800m (~2600ft) of elevation loss costs ~1.5 miles of effective distance
    
    Args:
        mm_df: Mile marker DataFrame (must have mile_marker, latitude, longitude, elevation_m)
        segment_stats: Elevation stats between MMs (from get_segment_elevation_stats)
        start_date: Hike start date
        daily_pace: Target miles per day on flat terrain
        adjust_for_elevation: Whether to adjust pace for elevation
    
    Returns:
        List of day plans with keys:
          day, date, date_obj, start_mm, end_mm, distance_mi, gain_m, loss_m,
          gain_ft, loss_ft, camp_lat, camp_lon, camp_elev_m, mile_marker
    """
    mms = mm_df["mile_marker"].values
    lats = mm_df["latitude"].values
    lons = mm_df["longitude"].values
    elevs = mm_df["elevation_m"].values if "elevation_m" in mm_df.columns else np.zeros(len(mms))
    
    # Build segment info
    segments = []
    for i in range(len(mms) - 1):
        seg_start = mms[i]
        seg_end = mms[i + 1]
        seg_dist = seg_end - seg_start
        
        if segment_stats is not None and i < len(segment_stats):
            seg_gain = segment_stats.iloc[i]["gain_m"]
            seg_loss = segment_stats.iloc[i]["loss_m"]
        else:
            elev_change = elevs[i + 1] - elevs[i]
            seg_gain = max(0, elev_change)
            seg_loss = max(0, -elev_change)
        
        segments.append({
            "start_mm": seg_start,
            "end_mm": seg_end,
            "distance": seg_dist,
            "gain_m": seg_gain,
            "loss_m": seg_loss,
        })
    
    # Plan days
    days = []
    current_day = 1
    current_date = start_date
    current_mile = mms[0]
    
    while current_mile < mms[-1]:
        day_start_mile = current_mile
        day_target_miles = daily_pace
        day_gain = 0.0
        day_loss = 0.0
        effective_miles_used = 0.0
        
        # Keep going until we've covered enough effective miles or reached the end
        while effective_miles_used < day_target_miles and current_mile < mms[-1]:
            # Find the segment we're currently in
            seg_idx = None
            for i, seg in enumerate(segments):
                if seg["start_mm"] <= current_mile < seg["end_mm"]:
                    seg_idx = i
                    break
            
            if seg_idx is None:
                # We're at or past the last mile marker
                break
            
            seg = segments[seg_idx]
            miles_into_segment = current_mile - seg["start_mm"]
            remaining_seg_miles = seg["distance"] - miles_into_segment
            
            # Calculate effective distance cost for this segment
            if adjust_for_elevation and seg["distance"] > 0:
                # Elevation penalty per mile
                gain_per_mile = seg["gain_m"] / seg["distance"]
                loss_per_mile = seg["loss_m"] / seg["distance"]
                
                # Naismith: 600m gain = ~2 miles equivalent, 800m loss = ~1.5 miles equivalent
                effective_factor = 1.0 + (gain_per_mile / 600.0) * 2.0 + (loss_per_mile / 800.0) * 1.5
            else:
                effective_factor = 1.0
            
            # How many effective miles do we have left?
            remaining_effective = day_target_miles - effective_miles_used
            
            # How many actual miles can we cover with the remaining effective miles?
            actual_miles_available = remaining_effective / effective_factor
            
            if actual_miles_available >= remaining_seg_miles:
                # We complete this segment
                actual_miles_covered = remaining_seg_miles
                proportional_gain = seg["gain_m"] * (remaining_seg_miles / seg["distance"])
                proportional_loss = seg["loss_m"] * (remaining_seg_miles / seg["distance"])
                current_mile = seg["end_mm"]
            else:
                # We stop partway through this segment
                actual_miles_covered = actual_miles_available
                proportional_gain = seg["gain_m"] * (actual_miles_covered / seg["distance"])
                proportional_loss = seg["loss_m"] * (actual_miles_covered / seg["distance"])
                current_mile += actual_miles_covered
            
            day_gain += proportional_gain
            day_loss += proportional_loss
            effective_miles_used += actual_miles_covered * effective_factor
        
        # Ensure we made some progress
        if current_mile <= day_start_mile:
            current_mile = min(day_start_mile + 0.1, mms[-1])
        
        # Interpolate position at end of day
        camp_lat, camp_lon, camp_elev = _interpolate_position(
            current_mile, mms, lats, lons, elevs
        )
        
        days.append({
            "day": current_day,
            "date": current_date.strftime("%Y-%m-%d"),
            "date_obj": current_date,
            "start_mm": round(day_start_mile, 1),
            "end_mm": round(current_mile, 1),
            "distance_mi": round(current_mile - day_start_mile, 1),
            "gain_m": round(day_gain),
            "loss_m": round(day_loss),
            "gain_ft": round(day_gain * 3.281),
            "loss_ft": round(day_loss * 3.281),
            "camp_lat": camp_lat,
            "camp_lon": camp_lon,
            "camp_elev_m": round(camp_elev),
            "camp_elev_ft": round(camp_elev * 3.281),
            "mile_marker": round(current_mile, 1),
        })
        
        current_day += 1
        current_date += timedelta(days=1)
        
        # Safety check
        if current_day > 1000:
            break
    
    return days


def _interpolate_position(target_mile, mms, lats, lons, elevs):
    """Interpolate lat/lon/elev at a specific mile marker."""
    if target_mile <= mms[0]:
        return lats[0], lons[0], elevs[0]
    if target_mile >= mms[-1]:
        return lats[-1], lons[-1], elevs[-1]
    
    for i in range(len(mms) - 1):
        if mms[i] <= target_mile <= mms[i + 1]:
            if mms[i + 1] == mms[i]:
                return lats[i], lons[i], elevs[i]
            frac = (target_mile - mms[i]) / (mms[i + 1] - mms[i])
            lat = lats[i] + frac * (lats[i + 1] - lats[i])
            lon = lons[i] + frac * (lons[i + 1] - lons[i])
            elev = elevs[i] + frac * (elevs[i + 1] - elevs[i])
            return lat, lon, elev
    
    return lats[-1], lons[-1], elevs[-1]


def recalculate_day_stats(day, mm_df, segment_stats):
    """Recalculate gain/loss for a day based on start and end mile markers."""
    start_mm = day["start_mm"]
    end_mm = day["end_mm"]
    
    mms = mm_df["mile_marker"].values
    elevs = mm_df["elevation_m"].values if "elevation_m" in mm_df.columns else np.zeros(len(mms))
    
    # Find segments that overlap with this day's range
    total_gain = 0.0
    total_loss = 0.0
    
    if segment_stats is not None:
        for _, seg in segment_stats.iterrows():
            seg_start = seg["start_mm"]
            seg_end = seg["end_mm"]
            
            # Check if segment overlaps with day's range
            if seg_start < end_mm and seg_end > start_mm:
                # Calculate overlap
                overlap_start = max(seg_start, start_mm)
                overlap_end = min(seg_end, end_mm)
                overlap_dist = overlap_end - overlap_start
                seg_dist = seg_end - seg_start
                
                if seg_dist > 0:
                    # Proportional gain/loss
                    proportion = overlap_dist / seg_dist
                    total_gain += seg["gain_m"] * proportion
                    total_loss += seg["loss_m"] * proportion
    else:
        # Fallback: use simple elevation difference
        start_elev = np.interp(start_mm, mms, elevs)
        end_elev = np.interp(end_mm, mms, elevs)
        elev_change = end_elev - start_elev
        total_gain = max(0, elev_change)
        total_loss = max(0, -elev_change)
    
    return {
        "gain_m": round(total_gain),
        "loss_m": round(total_loss),
        "gain_ft": round(total_gain * 3.281),
        "loss_ft": round(total_loss * 3.281),
    }


def get_thru_hike_summary(days: list[dict]) -> dict:
    """Summarize a thru-hike plan."""
    if not days:
        return {}
    total_distance = sum(d["distance_mi"] for d in days)
    total_gain = sum(d.get("gain_m", 0) for d in days)
    total_loss = sum(d.get("loss_m", 0) for d in days)
    avg_daily = total_distance / len(days) if days else 0

    return {
        "total_days": len(days),
        "total_distance_mi": round(total_distance, 1),
        "total_gain_m": round(total_gain),
        "total_gain_ft": round(total_gain * 3.281),
        "total_loss_m": round(total_loss),
        "total_loss_ft": round(total_loss * 3.281),
        "avg_daily_mi": round(avg_daily, 1),
        "start_date": days[0]["date"],
        "end_date": days[-1]["date"],
        "highest_camp_m": max(d.get("camp_elev_m", 0) for d in days),
        "highest_camp_ft": max(d.get("camp_elev_ft", 0) for d in days),
    }
