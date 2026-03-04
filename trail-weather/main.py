#!/usr/bin/env python3
"""
🥾 Trail History Weather — Deluxe Edition
Interactive weather history viewer for long-distance hiking trails.

Features:
  - Multi-trail support with auto-discovery
  - Interactive map with mile markers
  - Elevation profile from GPX data
  - Wind speed + gusts charts
  - Daylight / sunrise-sunset hours
  - Danger alerts (freezing, extreme heat, storms, high wind)
  - GPX file upload for custom trails
  - Year-over-year comparison
  - Share via URL parameters
  - CSV export

Original concept by Shepherd 🇩🇪 🍺 🥨
Pimped with ❤️ by GitHub Copilot
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import timedelta, date as Date
from streamlit_folium import st_folium

from config import get_available_trails, get_trail_files
from weather_api import fetch_weather, process_weather_responses, detect_danger_alerts
from map_builder import build_trail_map, calculate_range_coords
from charts import (
    build_temperature_chart, build_precipitation_chart, build_wind_chart,
    build_sunrise_sunset_chart, build_weather_summary_chart, build_elevation_profile,
    build_year_comparison_chart,
)
from gpx_upload import process_gpx_upload
from trail_db import save_trail, list_saved_trails, load_trail, delete_trail
from elevation_utils import (
    load_elevation_profile, get_segment_elevation_stats,
    plan_thru_hike, get_thru_hike_summary, recalculate_day_stats,
)


# ─── Page Config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="🥾 Trail History Weather",
    page_icon="🥾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS (Dark Mode) ───────────────────────────────────────
st.markdown("""
<style>
#     [data-testid="stSidebar"] {
#         background: linear-gradient(180deg, #1a2332 0%, #0d1117 100%);
#     }
#     .main .block-container {
#         padding-top: 0.5rem;
#         padding-bottom: 0.5rem;
#     }
#     [data-testid="stMetric"] {
#         background: #1a2332;
#         border-radius: 10px;
#         padding: 14px;
#         border: 1px solid #2d3748;
#     }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    .shepherd-footer {
        text-align: center; padding: 1.5rem 0 0.5rem 0;
        color: #64748b; font-size: 0.85rem;
    }
#     .shepherd-footer a { color: #3b82f6 !important; }
#     .danger-box {
#         background: linear-gradient(135deg, #451a03 0%, #7c2d12 100%);
#         border: 1px solid #ea580c;
#         border-radius: 10px;
#         padding: 1rem;
#         margin-bottom: 0.5rem;
#     }
#     .danger-box-warn {
#         background: linear-gradient(135deg, #422006 0%, #713f12 100%);
#         border: 1px solid #ca8a04;
#         border-radius: 10px;
#         padding: 1rem;
#         margin-bottom: 0.5rem;
#     }
# </style>
# """, unsafe_allow_html=True)


# ─── Cached Data Loaders ──────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def load_csv(path):
    """Load and cache a CSV file."""
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_emblem_b64(path):
    """Load and base64-encode an emblem image."""
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


@st.cache_data(show_spinner=False)
def simplify_route(route_df, max_points=800):
    """Decimate route to max_points for faster map rendering."""
    if len(route_df) <= max_points:
        return list(zip(route_df["latitude"], route_df["longitude"]))
    step = max(1, len(route_df) // max_points)
    simplified = route_df.iloc[::step]
    return list(zip(simplified["latitude"], simplified["longitude"]))


@st.cache_data(show_spinner=False)
def cached_danger_alerts(_df_hash, df, temp_symbol, wind_unit):
    """Cached version of danger alert detection."""
    return detect_danger_alerts(df, temp_symbol, wind_unit)


def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "start_date": Date.today(),
        "end_date": Date.today() + timedelta(days=30),
        "last_start_date": None,
        "mm_weather_df": None,
        "weather_by_mm_and_year": None,
        "mm_range_coords": None,
        "last_unit_system": None,
        "last_nobo": None,
        "last_trail": None,
        "uploaded_trail": None,
        "comparison_df": None,
        "thru_hike_days": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def apply_url_params(available_trails, mm_options):
    """Apply URL query parameters if present (share link support)."""
    params = st.query_params
    if "trail" in params and params["trail"] in available_trails:
        st.session_state.selected_trail = params["trail"]
    if "start" in params:
        try:
            st.session_state.start_date = Date.fromisoformat(params["start"])
        except ValueError:
            pass
    if "end" in params:
        try:
            st.session_state.end_date = Date.fromisoformat(params["end"])
        except ValueError:
            pass


BASE_URL = "https://trail-history-weather.hom-tech.de"

def generate_share_url(trail, start_date, end_date, start_mm, end_mm):
    """Generate a shareable URL with current settings."""
    return f"{BASE_URL}?trail={trail}&start={start_date}&end={end_date}&mm_start={start_mm}&mm_end={end_mm}"


def main():
    init_session_state()

    available_trails = get_available_trails()

    # ─── Sidebar ──────────────────────────────────────────────────

    # Trail Selector
    use_upload = False
    trail_options = {k: f"{v['emoji']} {v['name']}" for k, v in available_trails.items()}

    if available_trails:
        selected_trail = st.sidebar.selectbox(
            "🗺️ Select Trail",
            options=list(trail_options.keys()),
            format_func=lambda x: trail_options[x],
            key="selected_trail",
            label_visibility="collapsed",
        )
        trail_meta = available_trails[selected_trail]
        trail_files = get_trail_files(selected_trail)

        # Logo in sidebar (non-clickable)
        emblem_path = trail_files["emblem"]
        has_emblem = os.path.isfile(emblem_path)
        if has_emblem:
            b64 = load_emblem_b64(emblem_path)
            st.sidebar.markdown(
                f'<img src="data:image/png;base64,{b64}" width="160" '
                f'style="pointer-events:none; user-select:none; display:block; margin:0 auto 0.5rem auto;">',
                unsafe_allow_html=True,
            )
        #st.sidebar.markdown(f"### {trail_meta['emoji']} {trail_meta['name']}")
    else:
        selected_trail = None
        trail_meta = None
        trail_files = None
        has_emblem = False
        emblem_path = None

    # ─── GPX Upload ───────────────────────────────────────────────
    # with st.sidebar.expander("📤 Upload Custom Trail (GPX)", expanded=not bool(available_trails)):
    #     uploaded_gpx = st.file_uploader(
    #         "Drop your GPX file here",
    #         type=["gpx"],
    #         label_visibility="collapsed",
    #     )
    #     upload_name = st.text_input("Trail Name", value="MyTrail", max_chars=20)
    #     upload_interval = st.number_input("Mile Marker Interval", value=10, min_value=1, max_value=50)

    #     if uploaded_gpx and st.button("🔄 Process & Save GPX", width='stretch'):
    #         with st.spinner("Processing GPX file..."):
    #             result = process_gpx_upload(uploaded_gpx, upload_name, upload_interval)
    #             if result:
    #                 # Save to SQLite
    #                 trail_id = save_trail(
    #                     upload_name, upload_interval,
    #                     result["trackpoints_df"],
    #                     result["mm_nobo_df"],
    #                     result["mm_sobo_df"],
    #                 )
    #                 st.session_state.uploaded_trail = result
    #                 st.session_state.mm_weather_df = None
    #                 st.session_state.mm_range_coords = None
    #                 st.success(f"✅ {upload_name} saved! "
    #                           f"{len(result['trackpoints_df'])} trackpoints, "
    #                           f"{len(result['mm_nobo_df'])} mile markers")
    #             else:
    #                 st.error("❌ No track data found in GPX file")

    # ─── Saved Custom Trails ──────────────────────────────────────
    # saved_trails = list_saved_trails()
    # with st.sidebar.expander(f"💾 Saved Trails ({len(saved_trails)})", expanded=len(saved_trails) > 0):
    #     if saved_trails:
    #         for t in saved_trails:
    #             col_load, col_del = st.columns([3, 1])
    #             with col_load:
    #                 if st.button(
    #                     f"📂 {t['name']} ({t['total_miles']:.0f} mi)",
    #                     key=f"load_{t['id']}",
    #                     width='stretch',
    #                 ):
    #                     loaded = load_trail(t["id"])
    #                     if loaded:
    #                         st.session_state.uploaded_trail = loaded
    #                         st.session_state.mm_weather_df = None
    #                         st.session_state.mm_range_coords = None
    #                         st.rerun()
    #             with col_del:
    #                 if st.button("🗑️", key=f"del_{t['id']}"):
    #                     delete_trail(t["id"])
    #                     if (st.session_state.uploaded_trail
    #                             and st.session_state.uploaded_trail.get("trail_name") == t["name"]):
    #                         st.session_state.uploaded_trail = None
    #                         st.session_state.mm_weather_df = None
    #                         st.session_state.mm_range_coords = None
    #                     st.rerun()
    #         else:
    #             st.caption("No trails saved yet.\nUpload a GPX file ☝️")

    # Determine data source: uploaded trail or built-in
    if st.session_state.uploaded_trail:
        use_upload = True
        upl = st.session_state.uploaded_trail
        trail_name_display = f"📤 {upl['trail_name']}"
        timezone = "UTC"
        if st.sidebar.button("❌ Clear Active Upload"):
            st.session_state.uploaded_trail = None
            st.session_state.mm_weather_df = None
            st.session_state.mm_range_coords = None
            st.rerun()
    elif trail_meta:
        trail_name_display = f"{trail_meta['emoji']} {trail_meta['name']}"
        timezone = trail_meta["timezone"]
    else:
        st.error("❌ No trail data available. Upload a GPX file or add trail CSVs.")
        return

    # Reset weather data when trail changes
    if not use_upload and selected_trail != st.session_state.last_trail:
        st.session_state.mm_weather_df = None
        st.session_state.mm_range_coords = None
        st.session_state.comparison_df = None
        st.session_state.thru_hike_days = None
        st.session_state.reset_mm_range = True
        st.session_state.last_trail = selected_trail

    st.sidebar.markdown("---")

    # Initialize Settings variables early (UI widgets are at bottom of sidebar)
    # Get or set default values
    if "unit_system" not in st.session_state:
        st.session_state.unit_system = "Metric"
    if "direction" not in st.session_state:
        st.session_state.direction = "NOBO"
    if "show_mm" not in st.session_state:
        st.session_state.show_mm = False
    if "show_poi" not in st.session_state:
        st.session_state.show_poi = False
    
    # Use values from session state
    unit_system = st.session_state.unit_system
    is_metric = unit_system == "Metric"
    temperature_unit = "celsius" if is_metric else "fahrenheit"
    temp_symbol = "°C" if is_metric else "°F"
    wind_unit = "km/h" if is_metric else "mph"
    rain_unit = "mm" if is_metric else "in"
    snow_unit = "cm" if is_metric else "in"
    direction = st.session_state.direction
    nobo = direction == "NOBO"
    show_mm = st.session_state.show_mm
    show_poi = st.session_state.show_poi

    # ─── Load Trail Data (cached) ────────────────────────────────
    if use_upload:
        upl = st.session_state.uploaded_trail
        route_df = upl["trackpoints_df"]
        mm_df = upl["mm_nobo_df"] if nobo else upl["mm_sobo_df"]
    else:
        route_df = load_csv(trail_files["trackpoints"])
        mm_file = trail_files["mm_nobo"] if nobo else trail_files["mm_sobo"]
        mm_df = load_csv(mm_file)

    mm_options = mm_df["mile_marker"].tolist()

    # Apply URL params
    if not use_upload and available_trails:
        apply_url_params(available_trails, mm_options)

    # ─── 🥾 Thru-Hike Planner (Inputs) ───────────────────────────
    st.sidebar.markdown("### 🥾 Thru-Hike Planner")
    thru_col1, thru_col2 = st.sidebar.columns([2, 1])
    with thru_col1:
        thru_pace = st.number_input(
            "📏 max mi/day (flat)",
            min_value=5.0, max_value=40.0, value=20.0, step=1.0,
            help="Target miles per day on flat terrain. Elevation gain reduces effective pace.",
        )
    with thru_col2:
        thru_adjust_elev = st.checkbox("🏔️ Elev.", value=True,
                                        help="Naismith's Rule: +1h/600m ascent, +1h/800m descent")

    # ─── Mile Marker Range ────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📏 Mile Marker Range")

    # Direction selector
    direction_new = st.sidebar.radio("Direction", ["NOBO", "SOBO"], horizontal=True, index=0 if nobo else 1)
    if direction_new != direction:
        st.session_state.direction = direction_new
        st.session_state.mm_weather_df = None
        st.session_state.comparison_df = None
        st.session_state.thru_hike_days = None
        st.rerun()

    # Auto-reset MM range when trail changes
    if st.session_state.get("reset_mm_range", False):
        # Clear stale selectbox keys so they default to first/last
        if "start_mm" in st.session_state:
            del st.session_state["start_mm"]
        if "end_mm" in st.session_state:
            del st.session_state["end_mm"]
        st.session_state.reset_mm_range = False

    start_mm = st.sidebar.selectbox("Start MM", mm_options, index=0, key="start_mm")
    end_mm = st.sidebar.selectbox("End MM", mm_options, index=len(mm_options) - 1, key="end_mm")

    # Force End MM to max if it's not a valid option for this trail
    if end_mm not in mm_options:
        end_mm = mm_options[-1]
        st.session_state.end_mm = end_mm
    if start_mm > end_mm:
        start_mm, end_mm = end_mm, start_mm

    st.sidebar.caption(f"📐 Range: **{start_mm}** → **{end_mm}** ({end_mm - start_mm:.0f} mi)")

    selected_points = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ]

    # Reset thru-hike plan if MM range changed
    mm_range_key = (start_mm, end_mm)
    if st.session_state.get("last_mm_range") != mm_range_key:
        st.session_state.thru_hike_days = None
        st.session_state.last_mm_range = mm_range_key

    # Compute thru-hike plan
    if not use_upload and selected_trail:
        seg_stats = get_segment_elevation_stats(selected_trail, direction)
        # Filter seg_stats to only include segments within the selected MM range
        if seg_stats is not None:
            seg_stats = seg_stats[
                (seg_stats["start_mm"] >= start_mm) & (seg_stats["end_mm"] <= end_mm)
            ].reset_index(drop=True)
    else:
        seg_stats = None

    thru_mm_df = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ].reset_index(drop=True)

    # ─── 📅 Date Range ────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📅 Date Range")
    date_format = "DD-MM-YYYY" if is_metric else "YYYY-MM-DD"
    start_date = st.sidebar.date_input(
        "Start Date",
        min_value=Date.today(),
        max_value=Date(2100, 12, 31),
        format=date_format,
        key="start_date",
    )
    
    # Placeholder for end date - will be calculated by thru-hike planner
    hike_start = st.session_state.start_date
    hike_duration_days = None

    # ─── 🥾 Thru-Hike Planner (Calculations) ─────────────────────
    # Compute thru-hike plan
    if not use_upload and selected_trail:
        seg_stats = get_segment_elevation_stats(selected_trail, direction)
        # Filter seg_stats to only include segments within the selected MM range
        if seg_stats is not None:
            seg_stats = seg_stats[
                (seg_stats["start_mm"] >= start_mm) & (seg_stats["end_mm"] <= end_mm)
            ].reset_index(drop=True)
    else:
        seg_stats = None

    thru_mm_df = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ].reset_index(drop=True)

    # Check if thru-hike parameters changed - if so, force recalculation
    thru_params_key = (start_mm, end_mm, hike_start, thru_pace, thru_adjust_elev, selected_trail, direction)
    params_changed = st.session_state.get("last_thru_params") != thru_params_key
    manually_edited = st.session_state.get("itinerary_manually_edited", False)
    
    # Recalculate only if:
    # - Parameters changed AND not manually edited
    # - OR thru_hike_days doesn't exist
    if len(thru_mm_df) >= 2 and ((params_changed and not manually_edited) or st.session_state.thru_hike_days is None):
        thru_days = plan_thru_hike(
            thru_mm_df, seg_stats, hike_start,
            thru_pace, thru_adjust_elev,
        )
        summary = get_thru_hike_summary(thru_days)
        st.session_state.thru_hike_days = thru_days
        st.session_state.last_thru_params = thru_params_key
        st.session_state.itinerary_manually_edited = False
    
    # Display thru-hike summary and table
    if st.session_state.thru_hike_days:
        thru_days = st.session_state.thru_hike_days
        summary = get_thru_hike_summary(thru_days)
        if summary:
            hike_duration_days = summary["total_days"]
            end_date_hike = hike_start + timedelta(days=hike_duration_days - 1)
            # target_end = min(end_date_hike, Date.today() - timedelta(days=1))

            # # Auto-set end date to match hike duration
            # st.session_state.end_date = target_end

            st.sidebar.markdown(
                f"📅 **{summary['total_days']} Days** "
                f"({summary['avg_daily_mi']} mi/day)  \n"
                f"🏁 **{hike_start.strftime('%d.%m.%Y')} → "
                f"{end_date_hike.strftime('%d.%m.%Y')}**  \n"
                f"⬆️ {summary['total_gain_ft']:,} ft &nbsp; "
                f"⬇️ {summary['total_loss_ft']:,} ft &nbsp; "
                f"🏔️ {summary['highest_camp_ft']:,} ft"
            )
            
            # ─── Thru-Hike Itinerary Table (Editable) ───────────────────────
            with st.expander("📋 Show Daily Stages (End MM editable)", expanded=False):
                itinerary_df = pd.DataFrame(thru_days)
                
                # Show manual edit status
                if st.session_state.get("itinerary_manually_edited", False):
                    st.info("✏️ Plan was manually edited. Click '🔄 Update Plan' to recalculate automatically.")
                
                display_cols = {
                    "day": "Day",
                    "date": "Date",
                    "start_mm": "Start MM",
                    "end_mm": "End MM",
                    "distance_mi": "Miles",
                    "gain_ft": "↑ Gain (ft)",
                    "loss_ft": "↓ Loss (ft)",
                    "camp_elev_ft": "Camp Elev (ft)",
                }
                show_df = itinerary_df[[c for c in display_cols.keys() if c in itinerary_df.columns]]
                show_df = show_df.rename(columns=display_cols)
                
                # Make End MM column editable
                edited_df = st.data_editor(
                    show_df,
                    hide_index=True,
                    width='stretch',
                    disabled=["Day", "Date", "Start MM", "Miles", "↑ Gain (ft)", "↓ Loss (ft)", "Camp Elev (ft)"],
                    key="itinerary_editor"
                )
                
                # Check if End MM values changed
                if not edited_df["End MM"].equals(show_df["End MM"]):
                    if st.button("🔄 Recalculate with new values", key="recalc_itinerary"):
                        # Get current params for saving
                        current_params = (start_mm, end_mm, hike_start, thru_pace, thru_adjust_elev, selected_trail, direction)
                        
                        # Find the first day with changed End MM
                        first_changed_idx = None
                        for i, row in edited_df.iterrows():
                            if row["End MM"] != show_df.iloc[i]["End MM"]:
                                first_changed_idx = i
                                break
                        
                        if first_changed_idx is not None:
                            # Keep days before the change as-is
                            updated_days = [thru_days[j].copy() for j in range(first_changed_idx)]
                            
                            # Update the changed day
                            changed_day = thru_days[first_changed_idx].copy()
                            if first_changed_idx > 0:
                                changed_day["start_mm"] = updated_days[-1]["end_mm"]
                            changed_day["end_mm"] = float(edited_df.iloc[first_changed_idx]["End MM"])
                            changed_day["distance_mi"] = round(changed_day["end_mm"] - changed_day["start_mm"], 1)
                            
                            # Recalculate gain/loss for changed day
                            stats = recalculate_day_stats(changed_day, thru_mm_df, seg_stats)
                            changed_day.update(stats)
                            
                            # Recalculate position
                            from elevation_utils import _interpolate_position
                            mms = thru_mm_df["mile_marker"].values
                            lats = thru_mm_df["latitude"].values
                            lons = thru_mm_df["longitude"].values
                            elevs = thru_mm_df["elevation_m"].values if "elevation_m" in thru_mm_df.columns else np.zeros(len(mms))
                            
                            camp_lat, camp_lon, camp_elev = _interpolate_position(
                                changed_day["end_mm"], mms, lats, lons, elevs
                            )
                            changed_day["camp_lat"] = camp_lat
                            changed_day["camp_lon"] = camp_lon
                            changed_day["camp_elev_m"] = round(camp_elev)
                            changed_day["camp_elev_ft"] = round(camp_elev * 3.281)
                            changed_day["mile_marker"] = changed_day["end_mm"]
                            
                            # Update date if not first day
                            if first_changed_idx > 0:
                                prev_date = updated_days[-1]["date_obj"]
                                changed_day["date_obj"] = prev_date + timedelta(days=1)
                                changed_day["date"] = changed_day["date_obj"].strftime("%Y-%m-%d")
                            
                            updated_days.append(changed_day)
                            
                            # Replan all subsequent days from the new End MM
                            remaining_mm = end_mm - changed_day["end_mm"]
                            
                            if remaining_mm > 0.1:
                                # Create a sub-dataframe for replanning
                                replan_mm_df = thru_mm_df[thru_mm_df["mile_marker"] >= changed_day["end_mm"]].reset_index(drop=True)
                                
                                if len(replan_mm_df) >= 2:
                                    # Get next date
                                    next_date = changed_day["date_obj"] + timedelta(days=1)
                                    
                                    # Replan remaining days
                                    replanned_days = plan_thru_hike(
                                        replan_mm_df, seg_stats, next_date,
                                        thru_pace, thru_adjust_elev,
                                    )
                                    
                                    # Adjust day numbers to continue from current day
                                    for new_day in replanned_days:
                                        new_day["day"] = len(updated_days) + 1
                                        updated_days.append(new_day)
                            
                            # Save updated plan and mark as manually edited
                            st.session_state.thru_hike_days = updated_days
                            st.session_state.itinerary_manually_edited = True
                            st.session_state.last_thru_params = current_params
                            st.success(f"✓ {len(updated_days)} days updated (replanned from day {first_changed_idx + 1})!")
                            st.rerun()

    # Complete Date Range section with end date display

    # Automatically set end date based on thru-hike duration
    if hike_duration_days:
        end_date = start_date + timedelta(days=hike_duration_days - 1)
        st.session_state["end_date"] = end_date
        st.sidebar.markdown(f"**End Date:** {end_date.strftime('%d.%m.%Y' if is_metric else '%Y-%m-%d')} *(automatically calculated)*")
    else:
        # If no thru-hike plan, allow manual end date selection
        end_date_raw = st.session_state.get("end_date", start_date + timedelta(days=30))
        if end_date_raw < start_date:
            st.session_state["end_date"] = start_date
            end_date_raw = start_date
        end_date = st.sidebar.date_input(
            "End Date",
            min_value=start_date,
            max_value=Date(2100, 12, 31),
            format=date_format,
            key="end_date",
        )
    
    # Button to recalculate thru-hike plan with new dates
    if st.sidebar.button("🔄 Update Plan", width='stretch', help="Recalculation with changed start date"):
        st.session_state.thru_hike_days = None
        st.session_state.itinerary_manually_edited = False
        st.rerun()

    st.sidebar.markdown("---")

    # ─── Load Weather ─────────────────────────────────────────────
    wind_speed_unit_api = "kmh" if is_metric else "mph"
    if st.sidebar.button("⚡ Load Weather", type="primary", width='stretch'):
        with st.spinner(f"🌤️ Loading weather from last 5 years for {trail_name_display}..."):
            latitudes = selected_points["latitude"].tolist()
            longitudes = selected_points["longitude"].tolist()
            mile_markers = selected_points["mile_marker"].tolist()

            # Load weather data for the same date range in the last 5 years
            current_year = Date.today().year
            weather_by_mm_and_year = {}
            
            for year_offset in range(1, 6):  # Last 5 years: current_year-1 to current_year-5
                target_year = current_year - year_offset
                try:
                    # Adjust dates to target year
                    hist_start = start_date.replace(year=target_year)
                    hist_end = end_date.replace(year=target_year)
                    
                    responses = fetch_weather(
                        latitudes, longitudes, hist_start, hist_end,
                        temperature_unit, timezone, wind_speed_unit_api,
                    )
                    year_df = process_weather_responses(
                        responses, mile_markers, latitudes, longitudes, temp_symbol, timezone,
                        wind_unit, rain_unit, snow_unit,
                    )
                    
                    # Store data by mile marker and year
                    for mm in mile_markers:
                        if mm not in weather_by_mm_and_year:
                            weather_by_mm_and_year[mm] = {}
                        mm_data = year_df[year_df["Mile Marker"] == mm]
                        if not mm_data.empty:
                            weather_by_mm_and_year[mm][target_year] = mm_data
                except Exception as e:
                    st.warning(f"⚠️ Could not load data for year {target_year}: {str(e)}")
            
            st.session_state.weather_by_mm_and_year = weather_by_mm_and_year
            st.session_state.mm_weather_df = None  # Clear old format
            st.session_state.mm_range_coords = calculate_range_coords(
                route_df, mm_df, start_mm, end_mm
            )
            st.session_state.comparison_df = None

    # ─── Year Comparison Button ───────────────────────────────────
    # if st.session_state.mm_weather_df is not None:
    #     if st.sidebar.button("📅 Compare with Previous Year", width='stretch'):
    #         prev_start = start_date.replace(year=start_date.year - 1)
    #         prev_end = end_date.replace(year=end_date.year - 1)
    #         with st.spinner("📅 Loading previous year data..."):
    #             latitudes = selected_points["latitude"].tolist()
    #             longitudes = selected_points["longitude"].tolist()
    #             mile_markers = selected_points["mile_marker"].tolist()
    #
    #             prev_responses = fetch_weather(
    #                 latitudes, longitudes, prev_start, prev_end,
    #                 temperature_unit, timezone, wind_speed_unit_api,
    #             )
    #             st.session_state.comparison_df = process_weather_responses(
    #                 prev_responses, mile_markers, latitudes, longitudes, temp_symbol, timezone,
    #                 wind_unit, rain_unit, snow_unit,
    #             )
    #         st.rerun()

    # Clear Button
    if st.session_state.get("weather_by_mm_and_year") is not None or st.session_state.mm_range_coords is not None:
        if st.sidebar.button("🗑️ Clear Selection", width='stretch'):
            st.session_state.mm_range_coords = None
            st.session_state.mm_weather_df = None
            st.session_state.weather_by_mm_and_year = None
            st.session_state.comparison_df = None
            st.session_state.thru_hike_days = None
            st.session_state.reset_mm_range = True
            st.rerun()

    

    # ─── Settings (UI Widgets) ─────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Settings")
    unit_system_new = st.sidebar.radio("Units", ["Metric", "Imperial"], horizontal=True, index=0 if is_metric else 1)
    if unit_system_new != unit_system:
        st.session_state.unit_system = unit_system_new
        st.session_state.mm_weather_df = None
        st.session_state.comparison_df = None
        st.rerun()

    col3, col4 = st.sidebar.columns(2)
    with col3:
        show_mm_new = st.checkbox("Mile Markers", value=show_mm)
        if show_mm_new != show_mm:
            st.session_state.show_mm = show_mm_new
            st.rerun()
    with col4:
        if not use_upload and trail_files:
            has_poi = os.path.isfile(trail_files["poi"])
        else:
            has_poi = False
        show_poi_new = st.checkbox("POIs", value=show_poi, disabled=not has_poi)
        if show_poi_new != show_poi:
            st.session_state.show_poi = show_poi_new
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("Proudly presented by Shepherd 🇩🇪 🍺 🥨")
    # st.sidebar.caption("Pimped by GitHub Copilot 🤖✨")

    # # ─── Share Link ───────────────────────────────────────────────
    # if not use_upload and st.session_state.mm_weather_df is not None:
    #     share_url = generate_share_url(selected_trail, start_date, end_date, start_mm, end_mm)
    #     st.sidebar.markdown("---")
    #     st.sidebar.markdown("### 🔗 Share")
    #     st.sidebar.code(share_url, language=None)

    # ═══════════════════════════════════════════════════════════════
    # MAIN CONTENT
    # ═══════════════════════════════════════════════════════════════

    # ─── Map ──────────────────────────────────────────────────────
    poi_df = None
    if not use_upload and has_poi and show_poi:
        poi_df = load_csv(trail_files["poi"])

    route_coords = simplify_route(route_df)

    m = build_trail_map(
        route_df=route_df,
        mm_range_coords=st.session_state.mm_range_coords,
        mm_df=mm_df,
        show_mm=show_mm,
        direction=direction,
        poi_df=poi_df,
        show_poi=show_poi,
        emblem_image=emblem_path if has_emblem else None,
        route_coords=route_coords,
    )
    st_folium(m, width='stretch', height=650, returned_objects=[])

    # ─── Elevation Profile ────────────────────────────────────────
    if not use_upload and selected_trail:
        elev_df = load_elevation_profile(selected_trail)
        if elev_df is not None:
            elev_chart = build_elevation_profile(
                elev_df, mm_df, start_mm, end_mm,
            )
            if elev_chart:
                st.plotly_chart(elev_chart, width='stretch')

    # ─── Weather Data (Last 5 Years) ──────────────────────────────
    if st.session_state.get("weather_by_mm_and_year") is not None:
        weather_by_mm_and_year = st.session_state.weather_by_mm_and_year
        
        st.markdown("### 📊 Historical Weather Data (Last 5 Years)")
        st.markdown(f"**Date Range:** {start_date.strftime('%B %d')} to {end_date.strftime('%B %d')}")
        st.markdown("---")
        
        # Display data for each mile marker
        for mm in sorted(weather_by_mm_and_year.keys()):
            with st.expander(f"📍 Mile Marker {mm}", expanded=False):
                year_data = weather_by_mm_and_year[mm]
                
                if not year_data:
                    st.info("No data available for this mile marker")
                    continue
                
                # Prepare table with 6 rows (5 years + average)
                temp_max_col = f"Temp Max ({temp_symbol})"
                temp_min_col = f"Temp Min ({temp_symbol})"
                rain_col = f"Rain ({rain_unit})"
                snow_col = f"Snow ({snow_unit})"
                wind_col = f"Wind Max ({wind_unit})"
                gust_col = f"Gusts ({wind_unit})"
                
                table_rows = []
                
                # Collect data for each year (sorted from newest to oldest)
                for year in sorted(year_data.keys(), reverse=True):
                    year_df = year_data[year]
                    
                    # Aggregate data across the date range for this year
                    row = {
                        "Year": str(year),
                        temp_max_col: f"{year_df[temp_max_col].max():.1f}" if temp_max_col in year_df.columns else "N/A",
                        temp_min_col: f"{year_df[temp_min_col].min():.1f}" if temp_min_col in year_df.columns else "N/A",
                        rain_col: f"{year_df[rain_col].sum():.1f}" if rain_col in year_df.columns else "N/A",
                        snow_col: f"{year_df[snow_col].sum():.1f}" if snow_col in year_df.columns else "N/A",
                        wind_col: f"{year_df[wind_col].max():.1f}" if wind_col in year_df.columns else "N/A",
                        gust_col: f"{year_df[gust_col].max():.1f}" if gust_col in year_df.columns else "N/A",
                    }
                    
                    # Add weather description (most common)
                    if "Weather" in year_df.columns:
                        weather_counts = year_df["Weather"].value_counts()
                        row["Weather"] = weather_counts.index[0] if len(weather_counts) > 0 else "N/A"
                    else:
                        row["Weather"] = "N/A"
                    
                    table_rows.append(row)
                
                # Calculate average row
                if table_rows:
                    avg_row = {"Year": "Average"}
                    
                    # Calculate averages for numeric columns
                    for col in [temp_max_col, temp_min_col, rain_col, snow_col, wind_col, gust_col]:
                        values = []
                        for row in table_rows:
                            try:
                                val = float(row[col])
                                values.append(val)
                            except (ValueError, TypeError):
                                pass
                        
                        if values:
                            avg_row[col] = f"{np.mean(values):.1f}"
                        else:
                            avg_row[col] = "N/A"
                    
                    avg_row["Weather"] = "Various"
                    table_rows.append(avg_row)
                
                # Display table
                if table_rows:
                    table_df = pd.DataFrame(table_rows)
                    st.dataframe(table_df, width='stretch', hide_index=True)

    # Footer
    st.markdown(
        '<div class="shepherd-footer">'
        'Made with ❤️ for Thru-Hikers everywhere<br>'
        'Weather data by <a href="https://open-meteo.com/" target="_blank">Open-Meteo</a>'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
