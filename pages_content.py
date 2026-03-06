"""
Page content modules for the Trail Weather App
Each function represents a separate page in the multi-page application.
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import timedelta, date as Date
from streamlit_folium import st_folium

from config import get_trail_files
from weather_api import fetch_weather, process_weather_responses
from map_builder import build_trail_map, calculate_range_coords
from charts import (
    build_elevation_profile, build_temperature_chart, build_precipitation_chart,
    build_wind_chart, build_sunrise_sunset_chart, build_weather_summary_chart
)
from elevation_utils import (
    load_elevation_profile, get_segment_elevation_stats,
    plan_thru_hike, get_thru_hike_summary, recalculate_day_stats, _interpolate_position
)


def thru_hike_planner_page(selected_trail, trail_meta, use_upload, route_df, mm_df, mm_options):
    """Page 1: Thru-Hike Planner with all controls and visualization"""
    
    st.title("🥾 Thru-Hike Planner")
    st.caption("Plan your thru-hike with elevation-adjusted daily mileage. Edit the itinerary to match your campgrounds or POIs.")
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # Get settings from session state
    unit_system = st.session_state.unit_system
    is_metric = unit_system == "Metric"
    direction = st.session_state.direction
    nobo = direction == "NOBO"
    show_mm = st.session_state.show_mm
    show_poi = st.session_state.show_poi
    
    temp_symbol = "°C" if is_metric else "°F"
    wind_unit = "km/h" if is_metric else "mph"
    rain_unit = "mm" if is_metric else "in"
    snow_unit = "cm" if is_metric else "in"
    
    trail_files = get_trail_files(selected_trail) if not use_upload else None
    
    # ═══ Control Section ═══
    st.markdown(
        f'<div class="control-card">'
        f'<h3 style="text-align: center; margin-top: 0;">I want to hike the {trail_meta["emoji"]} {selected_trail} …</h3>'
        f'</div>',
        unsafe_allow_html=True,
    )
    
    col1, col2, col3 = st.columns(3)
    
    # Column 1: Thru-Hike Planner Settings
    with col1:
        st.markdown("#### with a daily mileage...")
        thru_pace = st.number_input(
            "📏 max mi/day (flat)",
            min_value=5.0, max_value=40.0, value=20.0, step=1.0,
            help="Target miles per day on flat terrain. Elevation gain reduces effective pace.",
        )
        thru_adjust_elev = st.checkbox("🏔️ Adjust for Elevation", value=True,
                                        help="Naismith's Rule: +1h/600m ascent, +1h/800m descent")
    
    # Column 2: Mile Marker Range & Direction
    with col2:
        st.markdown("#### from... to...")
        if "start_mm_page" not in st.session_state:
            st.session_state.start_mm_page = mm_options[0]
        if "end_mm_page" not in st.session_state:
            st.session_state.end_mm_page = mm_options[-1]
        start_mm = st.selectbox("Start MM", mm_options, key="start_mm_page")
        end_mm = st.selectbox("End MM", mm_options, key="end_mm_page")
        
        if start_mm > end_mm:
            start_mm, end_mm = end_mm, start_mm
        
        st.caption(f"📐 Range: **{start_mm}** → **{end_mm}** ({end_mm - start_mm:.0f} mi)")
        
        direction_new = st.radio("Direction", ["NOBO", "SOBO"], horizontal=True, index=0 if nobo else 1)
        if direction_new != direction:
            st.session_state.direction = direction_new
            st.session_state.thru_hike_days = None
            st.rerun()
        
    # Column 3: Date Range
    with col3:
        st.markdown("####  starting on")
        date_format = "DD-MM-YYYY" if is_metric else "YYYY-MM-DD"
        start_date = st.date_input(
            "Start Date",
            min_value=Date.today(),
            max_value=Date(2100, 12, 31),
            format=date_format,
            key="start_date_page",
        )
    
    selected_points = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ]
    
    # Get elevation stats
    if not use_upload and selected_trail:
        seg_stats = get_segment_elevation_stats(selected_trail, direction)
        if seg_stats is not None:
            seg_stats = seg_stats[
                (seg_stats["start_mm"] >= start_mm) & (seg_stats["end_mm"] <= end_mm)
            ].reset_index(drop=True)
    else:
        seg_stats = None
    
    thru_mm_df = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ].reset_index(drop=True)
    
    # Calculate thru-hike plan
    hike_start = start_date
    hike_duration_days = None
    
    thru_params_key = (start_mm, end_mm, hike_start, thru_pace, thru_adjust_elev, selected_trail, direction)
    params_changed = st.session_state.get("last_thru_params") != thru_params_key
    manually_edited = st.session_state.get("itinerary_manually_edited", False)
    
    if len(thru_mm_df) >= 2 and ((params_changed and not manually_edited) or st.session_state.thru_hike_days is None):
        thru_days = plan_thru_hike(thru_mm_df, seg_stats, hike_start, thru_pace, thru_adjust_elev)
        st.session_state.thru_hike_days = thru_days
        st.session_state.last_thru_params = thru_params_key
        st.session_state.itinerary_manually_edited = False
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # Display summary and table
    if st.session_state.thru_hike_days:
        thru_days = st.session_state.thru_hike_days
        summary = get_thru_hike_summary(thru_days)
        
        if summary:
            hike_duration_days = summary["total_days"]
            end_date_hike = hike_start + timedelta(days=hike_duration_days - 1)
            
            # Summary metrics
            st.markdown('<p class="section-header">📊 Trip Summary</p>', unsafe_allow_html=True)
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric("🗓️ Duration", f"{summary['total_days']} days")
            with m2:
                st.metric("📏 Avg Daily", f"{summary['avg_daily_mi']} mi/day")
            with m3:
                st.metric("⬆️ Total Gain", f"{summary['total_gain_ft']:,} ft")
            with m4:
                st.metric("⬇️ Total Loss", f"{summary['total_loss_ft']:,} ft")
            with m5:
                st.metric("🏔️ Highest Camp", f"{summary['highest_camp_ft']:,} ft")
            
            st.markdown(f"**Trip Dates:** {hike_start.strftime('%d.%m.%Y')} → {end_date_hike.strftime('%d.%m.%Y')}")
            
            # Editable itinerary table
            with st.expander("📋 Daily Itinerary (Start MM Day 1 & End MM editable)", expanded=False):
                itinerary_df = pd.DataFrame(thru_days)
                
                if st.session_state.get("itinerary_manually_edited", False):
                    st.info("✏️ Plan was manually edited. Click '🔄 Reset Plan' to recalculate automatically.")
                
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
                
                # Add Notes column – preserve existing notes from session state
                saved_notes = st.session_state.get("itinerary_notes", {})
                show_df["Notes"] = show_df.index.map(lambda i: saved_notes.get(i, ""))
                
                edited_df = st.data_editor(
                    show_df,
                    hide_index=True,
                    width='stretch',
                    disabled=["Day", "Date", "Miles", "↑ Gain (ft)", "↓ Loss (ft)", "Camp Elev (ft)"],
                    key="itinerary_editor_page"
                )
                
                # Persist Notes from the edited DataFrame
                if "Notes" in edited_df.columns:
                    st.session_state["itinerary_notes"] = {
                        i: v for i, v in edited_df["Notes"].items() if v
                    }
                
                # Download button (CSV)
                csv_data = edited_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Itinerary (CSV)",
                    data=csv_data,
                    file_name=f"{selected_trail}_itinerary.csv",
                    mime="text/csv",
                )
                
                # Detect edits via the widget's internal edited_rows state
                editor_state = st.session_state.get("itinerary_editor_page", {})
                edited_rows = editor_state.get("edited_rows", {}) if isinstance(editor_state, dict) else {}
                

                # ── Check if Start MM was changed in the first row ──
                start_mm_row0_changed = False
                new_start_mm_value = None
                for row_key, changes in edited_rows.items():
                    if int(row_key) == 0 and "Start MM" in changes:
                        start_mm_row0_changed = True
                        new_start_mm_value = float(changes["Start MM"])
                        break
                
                if start_mm_row0_changed and new_start_mm_value is not None:
                    mms = thru_mm_df["mile_marker"].values
                    lats = thru_mm_df["latitude"].values
                    lons = thru_mm_df["longitude"].values
                    elevs = thru_mm_df["elevation_m"].values if "elevation_m" in thru_mm_df.columns else np.zeros(len(mms))
                    
                    # Build a new mm_df starting from the new Start MM
                    replan_mm_df = thru_mm_df[thru_mm_df["mile_marker"] >= new_start_mm_value].reset_index(drop=True)
                    
                    # Insert interpolated point at exact new Start MM if needed
                    if len(replan_mm_df) == 0 or replan_mm_df.iloc[0]["mile_marker"] != new_start_mm_value:
                        interp_lat, interp_lon, interp_elev = _interpolate_position(
                            new_start_mm_value, mms, lats, lons, elevs
                        )
                        new_row = pd.DataFrame([{
                            "mile_marker": new_start_mm_value,
                            "latitude": interp_lat,
                            "longitude": interp_lon,
                            "elevation_m": interp_elev,
                        }])
                        replan_mm_df = pd.concat([new_row, replan_mm_df], ignore_index=True)
                    
                    if len(replan_mm_df) >= 2:
                        replanned_days = plan_thru_hike(
                            replan_mm_df, seg_stats, hike_start,
                            thru_pace, thru_adjust_elev,
                        )
                        st.session_state.thru_hike_days = replanned_days
                        st.session_state.itinerary_manually_edited = True
                        st.session_state.last_thru_params = (start_mm, end_mm, hike_start, thru_pace, thru_adjust_elev, selected_trail, direction)
                        del st.session_state["itinerary_editor_page"]
                        st.rerun()
                
                # ── Find the first row where End MM was changed ──
                first_changed_idx = None
                new_end_mm_value = None
                for row_idx_str, changes in sorted(edited_rows.items(), key=lambda x: int(x[0])):
                    if "End MM" in changes:
                        first_changed_idx = int(row_idx_str)
                        new_end_mm_value = float(changes["End MM"])
                        break
                
                if first_changed_idx is not None and new_end_mm_value is not None:
                    current_params = (start_mm, end_mm, hike_start, thru_pace, thru_adjust_elev, selected_trail, direction)
                    
                    updated_days = [thru_days[j].copy() for j in range(first_changed_idx)]
                    
                    changed_day = thru_days[first_changed_idx].copy()
                    if first_changed_idx > 0:
                        changed_day["start_mm"] = updated_days[-1]["end_mm"]
                    changed_day["end_mm"] = new_end_mm_value
                    changed_day["distance_mi"] = round(changed_day["end_mm"] - changed_day["start_mm"], 1)
                    
                    stats = recalculate_day_stats(changed_day, thru_mm_df, seg_stats)
                    changed_day.update(stats)
                    
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
                    
                    if first_changed_idx > 0:
                        prev_date = updated_days[-1]["date_obj"]
                        changed_day["date_obj"] = prev_date + timedelta(days=1)
                        changed_day["date"] = changed_day["date_obj"].strftime("%Y-%m-%d")
                    
                    updated_days.append(changed_day)
                    
                    remaining_mm = end_mm - changed_day["end_mm"]
                    
                    if remaining_mm > 0.1:
                        replan_mm_df = thru_mm_df[thru_mm_df["mile_marker"] >= changed_day["end_mm"]].reset_index(drop=True)
                        
                        # Ensure the exact end_mm value is the first point in replan_mm_df
                        new_end = changed_day["end_mm"]
                        if len(replan_mm_df) == 0 or replan_mm_df.iloc[0]["mile_marker"] != new_end:
                            # Interpolate lat/lon/elev for the exact mile marker
                            interp_lat, interp_lon, interp_elev = _interpolate_position(
                                new_end, mms, lats, lons, elevs
                            )
                            new_row = pd.DataFrame([{
                                "mile_marker": new_end,
                                "latitude": interp_lat,
                                "longitude": interp_lon,
                                "elevation_m": interp_elev,
                            }])
                            replan_mm_df = pd.concat([new_row, replan_mm_df], ignore_index=True)
                        
                        if len(replan_mm_df) >= 2:
                            next_date = changed_day["date_obj"] + timedelta(days=1)
                            replanned_days = plan_thru_hike(
                                replan_mm_df, seg_stats, next_date,
                                thru_pace, thru_adjust_elev,
                            )
                            
                            for new_day in replanned_days:
                                new_day["day"] = len(updated_days) + 1
                                updated_days.append(new_day)
                    
                    st.session_state.thru_hike_days = updated_days
                    st.session_state.itinerary_manually_edited = True
                    st.session_state.last_thru_params = current_params
                    # Clear data_editor state so it picks up the new values
                    del st.session_state["itinerary_editor_page"]
                    st.rerun()
                
                if st.button("🔄 Reset Plan", key="reset_plan"):
                    st.session_state.thru_hike_days = None
                    st.session_state.itinerary_manually_edited = False
                    if "itinerary_editor_page" in st.session_state:
                        del st.session_state["itinerary_editor_page"]
                    st.rerun()
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # Historical Weather Section
    st.markdown('<p class="section-header">🌤️ Historical Weather Data</p>', unsafe_allow_html=True)
    st.caption("Load weather data for your selected mile marker range.")
    
    # Calculate end date for weather query
    weather_end_date = start_date
    if hike_duration_days:
        weather_end_date = start_date + timedelta(days=hike_duration_days - 1)
    
    today = Date.today()
    temperature_unit = "celsius" if is_metric else "fahrenheit"
    
    col_weather1, col_weather2 = st.columns([1, 3])
    with col_weather1:
        if st.button("⚡ Load Historical Weather", type="primary", key="load_weather_thru"):
            hist_start = start_date
            hist_end = weather_end_date
            
            with st.spinner("🌤️ Loading weather from last 5 years..."):
                wind_speed_unit_api = "kmh" if is_metric else "mph"
                current_year = today.year
                weather_by_mm_and_year = {}
                
                for year_offset in range(1, 6):
                    target_year = current_year - year_offset
                    try:
                        year_start = hist_start.replace(year=target_year)
                        year_end = hist_end.replace(year=target_year)
                        
                        responses = fetch_weather(
                            selected_points["latitude"].tolist(),
                            selected_points["longitude"].tolist(),
                            year_start, year_end,
                            temperature_unit, "UTC",
                            wind_speed_unit_api,
                        )
                        year_df = process_weather_responses(
                            responses,
                            selected_points["mile_marker"].tolist(),
                            selected_points["latitude"].tolist(),
                            selected_points["longitude"].tolist(),
                            temp_symbol, "UTC",
                            wind_unit, rain_unit, snow_unit,
                        )
                        
                        for mm in selected_points["mile_marker"].tolist():
                            if mm not in weather_by_mm_and_year:
                                weather_by_mm_and_year[mm] = {}
                            mm_data = year_df[year_df["Mile Marker"] == mm]
                            if not mm_data.empty:
                                weather_by_mm_and_year[mm][target_year] = mm_data
                    except Exception as e:
                        st.warning(f"⚠️ Could not load data for year {target_year}: {str(e)}")
                
                st.session_state.weather_by_mm_and_year_thru = weather_by_mm_and_year
                st.rerun()
    
    with col_weather2:
        st.caption(f"📅 Date range: {start_date.strftime('%d.%m.%Y')} → {weather_end_date.strftime('%d.%m.%Y')}")
    
    # Display weather data
    if st.session_state.get("weather_by_mm_and_year_thru") is not None:
        weather_data = st.session_state.weather_by_mm_and_year_thru
        
        st.markdown("### 📊 Weather Summary by Mile Marker")
        
        for mm in sorted(weather_data.keys()):
            with st.expander(f"📍 Mile Marker {mm}", expanded=False):
                year_data = weather_data[mm]
                
                if not year_data:
                    st.info("No data available")
                    continue
                
                temp_max_col = f"Temp Max ({temp_symbol})"
                temp_min_col = f"Temp Min ({temp_symbol})"
                rain_col = f"Rain ({rain_unit})"
                snow_col = f"Snow ({snow_unit})"
                wind_col = f"Wind Max ({wind_unit})"
                gust_col = f"Gusts ({wind_unit})"
                
                table_rows = []
                
                for year in sorted(year_data.keys(), reverse=True):
                    year_df = year_data[year]
                    
                    row = {
                        "Year": str(year),
                        temp_max_col: f"{year_df[temp_max_col].max():.1f}" if temp_max_col in year_df.columns else "N/A",
                        temp_min_col: f"{year_df[temp_min_col].min():.1f}" if temp_min_col in year_df.columns else "N/A",
                        rain_col: f"{year_df[rain_col].sum():.1f}" if rain_col in year_df.columns else "N/A",
                        snow_col: f"{year_df[snow_col].sum():.1f}" if snow_col in year_df.columns else "N/A",
                        wind_col: f"{year_df[wind_col].max():.1f}" if wind_col in year_df.columns else "N/A",
                        gust_col: f"{year_df[gust_col].max():.1f}" if gust_col in year_df.columns else "N/A",
                    }
                    
                    if "Weather" in year_df.columns:
                        weather_counts = year_df["Weather"].value_counts()
                        row["Weather"] = weather_counts.index[0] if len(weather_counts) > 0 else "N/A"
                    else:
                        row["Weather"] = "N/A"
                    
                    table_rows.append(row)
                
                if table_rows:
                    avg_row = {"Year": "Average"}
                    
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
                
                if table_rows:
                    table_df = pd.DataFrame(table_rows)
                    st.dataframe(table_df, width='stretch', hide_index=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # Map
    st.markdown('<p class="section-header">🗺️ Trail Map</p>', unsafe_allow_html=True)
    poi_df = None
    if not use_upload and trail_files and show_poi:
        poi_file = trail_files["poi"]
        if os.path.isfile(poi_file):
            poi_df = pd.read_csv(poi_file)
    
    from main import simplify_route
    route_coords = simplify_route(route_df)
    
    # Calculate range coordinates for the selected mile marker range
    mm_range_coords = calculate_range_coords(route_df, mm_df, start_mm, end_mm)
    
    trail_files_main = get_trail_files(selected_trail) if not use_upload else None
    emblem_path = trail_files_main["emblem"] if trail_files_main else None
    has_emblem = emblem_path and os.path.isfile(emblem_path)
    
    m = build_trail_map(
        route_df=route_df,
        mm_range_coords=mm_range_coords,
        mm_df=mm_df,
        show_mm=show_mm,
        direction=direction,
        poi_df=poi_df,
        show_poi=show_poi,
        emblem_image=emblem_path if has_emblem else None,
        route_coords=route_coords,
    )
    st_folium(m, use_container_width=True, height=600, returned_objects=[])
    
    # Elevation Profile
    if not use_upload and selected_trail:
        elev_df = load_elevation_profile(selected_trail)
        if elev_df is not None:
            st.markdown('<p class="section-header">📈 Elevation Profile</p>', unsafe_allow_html=True)
            elev_chart = build_elevation_profile(elev_df, mm_df, start_mm, end_mm)
            if elev_chart:
                st.plotly_chart(elev_chart, width='stretch')


def history_weather_page(selected_trail, trail_meta, use_upload, route_df, mm_df, mm_options, timezone):
    """Page 2: Historical Weather Data"""
    
    st.title("🌤️ Historical Weather Data")
    st.caption("View historical weather patterns for your selected trail segment.")
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # Get settings
    unit_system = st.session_state.unit_system
    is_metric = unit_system == "Metric"
    temperature_unit = "celsius" if is_metric else "fahrenheit"
    temp_symbol = "°C" if is_metric else "°F"
    wind_unit = "km/h" if is_metric else "mph"
    rain_unit = "mm" if is_metric else "in"
    snow_unit = "cm" if is_metric else "in"
    direction = st.session_state.direction
    
    # Controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📏 Mile Marker Range")
        if "start_mm_weather" not in st.session_state:
            st.session_state.start_mm_weather = mm_options[0]
        if "end_mm_weather" not in st.session_state:
            st.session_state.end_mm_weather = mm_options[-1]
        start_mm = st.selectbox("Start MM", mm_options, key="start_mm_weather")
        end_mm = st.selectbox("End MM", mm_options, key="end_mm_weather")
        if start_mm > end_mm:
            start_mm, end_mm = end_mm, start_mm
        st.caption(f"📐 {end_mm - start_mm:.0f} miles")
    
    with col2:
        st.markdown("### 📅 Date Range")
        date_format = "DD-MM-YYYY" if is_metric else "YYYY-MM-DD"
        start_date = st.date_input(
            "Start Date",
            min_value=Date(1940, 1, 1),
            max_value=Date.today(),
            format=date_format,
            key="weather_start_date",
        )
    
    with col3:
        st.markdown("### 📅")
        end_date = st.date_input(
            "End Date",
            min_value=start_date,
            max_value=Date.today(),
            format=date_format,
            key="weather_end_date",
        )
        
        # Validate: end_date must be after start_date
        if end_date <= start_date:
            end_date = start_date + timedelta(days=1)
            if end_date > Date.today():
                end_date = Date.today()
            st.warning(f"⚠️ Enddatum wurde auf {end_date.strftime('%d.%m.%Y')} korrigiert.")
    
    selected_points = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ]
    
    # Load Weather Button
    if st.button("⚡ Load Historical Weather", type="primary", key="load_weather_history"):
        with st.spinner("🌤️ Loading weather data..."):
            latitudes = selected_points["latitude"].tolist()
            longitudes = selected_points["longitude"].tolist()
            mile_markers = selected_points["mile_marker"].tolist()
            
            wind_speed_unit_api = "kmh" if is_metric else "mph"
            
            try:
                responses = fetch_weather(
                    latitudes, longitudes, start_date, end_date,
                    temperature_unit, timezone, wind_speed_unit_api,
                )
                weather_df = process_weather_responses(
                    responses, mile_markers, latitudes, longitudes, temp_symbol, timezone,
                    wind_unit, rain_unit, snow_unit,
                )
                
                st.session_state.weather_history_df = weather_df
                st.success(f"✓ Weather data loaded for {len(mile_markers)} mile markers!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Could not load weather data: {str(e)}")
    
    # Display weather data by date
    if st.session_state.get("weather_history_df") is not None:
        weather_df = st.session_state.weather_history_df
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('<p class="section-header">📊 Weather Data by Date</p>', unsafe_allow_html=True)
        
        # Group by date
        dates = sorted(weather_df["Date"].unique())
        
        # Dropdown for chart date selection
        date_labels = {d: pd.to_datetime(d).strftime('%A, %d.%m.%Y') for d in dates}
        chart_options = ["All Days"] + [date_labels[d] for d in dates]
        selected_chart_date = st.selectbox(
            "📅 Select date for charts",
            options=chart_options,
            index=0,
            key="history_chart_date_select"
        )
        
        # Determine chart data based on selection
        if selected_chart_date == "All Days":
            chart_data = weather_df.copy()
            chart_date_label = None
        else:
            # Find the matching date
            matching_date = [d for d, label in date_labels.items() if label == selected_chart_date][0]
            chart_data = weather_df[weather_df["Date"] == matching_date].copy()
            chart_date_label = matching_date
        
        chart_data = chart_data.sort_values("Mile Marker").reset_index(drop=True)
        
        # Display charts for selected date
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            temp_chart = build_temperature_chart(chart_data, temp_symbol, chart_date_label)
            if temp_chart:
                st.plotly_chart(temp_chart, width="stretch")
            
            precip_chart = build_precipitation_chart(chart_data, chart_date_label, rain_unit, snow_unit)
            if precip_chart:
                st.plotly_chart(precip_chart, width="stretch")
        
        with col_chart2:
            wind_chart = build_wind_chart(chart_data, chart_date_label, wind_unit)
            if wind_chart:
                st.plotly_chart(wind_chart, width="stretch")
            
            sunrise_chart = build_sunrise_sunset_chart(chart_data, chart_date_label)
            if sunrise_chart:
                st.plotly_chart(sunrise_chart, width="stretch")
        
        if selected_chart_date == "All Days":
            summary_chart = build_weather_summary_chart(weather_df)
            if summary_chart:
                st.plotly_chart(summary_chart, width="stretch")
        
        # Data tables per date
        for date in dates:
            date_str = date_labels[date]
            
            with st.expander(f"📅 {date_str}", expanded=False):
                # Filter data for this date
                day_data = weather_df[weather_df["Date"] == date].copy()
                
                if day_data.empty:
                    st.info("No data available")
                    continue
                
                # Sort by mile marker
                day_data = day_data.sort_values("Mile Marker").reset_index(drop=True)
                
                # Create table with Mile Markers as rows
                temp_max_col = f"Temp Max ({temp_symbol})"
                temp_min_col = f"Temp Min ({temp_symbol})"
                rain_col = f"Rain ({rain_unit})"
                snow_col = f"Snow ({snow_unit})"
                wind_col = f"💨 Wind Max ({wind_unit})"
                gust_col = f"💨 Gusts ({wind_unit})"
                
                table_data = {
                    "MM": day_data["Mile Marker"].apply(lambda x: f"{x:.1f}"),
                    temp_max_col: day_data[temp_max_col].apply(lambda x: f"{x:.1f}"),
                    temp_min_col: day_data[temp_min_col].apply(lambda x: f"{x:.1f}"),
                    rain_col: day_data[rain_col].apply(lambda x: f"{x:.1f}"),
                    snow_col: day_data[snow_col].apply(lambda x: f"{x:.1f}"),
                    wind_col: day_data[wind_col].apply(lambda x: f"{x:.1f}"),
                    gust_col: day_data[gust_col].apply(lambda x: f"{x:.1f}"),
                    "🌅 Sunrise": day_data["🌅 Sunrise"],
                    "🌇 Sunset": day_data["🌇 Sunset"],
                    "☀️ Daylight": day_data["☀️ Daylight (h)"].apply(lambda x: f"{x:.1f}h"),
                    "Weather": day_data["Weather"],
                }
                
                display_df = pd.DataFrame(table_data)
                st.dataframe(display_df, width='stretch', hide_index=True)
        
        # Map and Elevation Profile
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('<p class="section-header">🗺️ Trail Map & 📈 Elevation Profile</p>', unsafe_allow_html=True)
        
        col_map, col_elev = st.columns([1, 1])
        
        with col_map:
            st.markdown("#### 🗺️ Map")
            # Calculate range coordinates
            mm_range_coords = calculate_range_coords(route_df, mm_df, start_mm, end_mm)
            
            from main import simplify_route
            route_coords = simplify_route(route_df)
            
            # Get POI data if available
            trail_files = get_trail_files(selected_trail) if not use_upload else None
            poi_df = None
            if trail_files and st.session_state.show_poi:
                poi_file = trail_files["poi"]
                if os.path.isfile(poi_file):
                    poi_df = pd.read_csv(poi_file)
            
            emblem_path = trail_files["emblem"] if trail_files else None
            has_emblem = emblem_path and os.path.isfile(emblem_path)
            
            m = build_trail_map(
                route_df=route_df,
                mm_range_coords=mm_range_coords,
                mm_df=mm_df,
                show_mm=st.session_state.show_mm,
                direction=direction,
                poi_df=poi_df,
                show_poi=st.session_state.show_poi,
                emblem_image=emblem_path if has_emblem else None,
                route_coords=route_coords,
            )
            st_folium(m, use_container_width=True, height=500, returned_objects=[])
        
        with col_elev:
            st.markdown("#### 📈 Elevation Profile")
            if not use_upload and selected_trail:
                from elevation_utils import load_elevation_profile
                elev_df = load_elevation_profile(selected_trail)
                if elev_df is not None:
                    elev_chart = build_elevation_profile(elev_df, mm_df, start_mm, end_mm)
                    if elev_chart:
                        st.plotly_chart(elev_chart, width="stretch")
                else:
                    st.info("No elevation data available")
            else:
                st.info("Elevation profile not available for uploaded trails")


def coming_soon_page(route_df=None):
    """Page 3: Spot Weather – click on a map to fetch weather for any location."""

    st.title("📍 Spot Weather")
    st.caption("Click anywhere on the map to fetch historical weather data for that location.")
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Settings ──────────────────────────────────────────────────
    unit_system = st.session_state.unit_system
    is_metric = unit_system == "Metric"
    temperature_unit = "celsius" if is_metric else "fahrenheit"
    temp_symbol = "°C" if is_metric else "°F"
    wind_unit = "km/h" if is_metric else "mph"
    rain_unit = "mm" if is_metric else "in"
    snow_unit = "cm" if is_metric else "in"
    wind_speed_unit_api = "kmh" if is_metric else "mph"
    date_format = "DD-MM-YYYY" if is_metric else "YYYY-MM-DD"

    # ── Date inputs ───────────────────────────────────────────────
    col_date1, col_date2, col_spacer = st.columns([1, 1, 2])

    with col_date1:
        start_date = st.date_input(
            "📅 Start Date",
            value=st.session_state.get("spot_start_date", Date.today()),
            min_value=Date(1940, 1, 1),
            max_value=Date.today(),
            format=date_format,
            key="spot_start_date",
        )

    # Auto-sync end date when start date changes
    prev_start = st.session_state.get("_spot_prev_start")
    if prev_start is not None and start_date != prev_start:
        st.session_state.spot_end_date = start_date
    st.session_state._spot_prev_start = start_date

    with col_date2:
        end_date = st.date_input(
            "📅 End Date",
            min_value=start_date,
            max_value=Date.today(),
            format=date_format,
            key="spot_end_date",
        )

    if end_date < start_date:
        end_date = start_date

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Map ───────────────────────────────────────────────────────
    st.markdown('<p class="section-header">🗺️ Click on the map</p>', unsafe_allow_html=True)

    import folium

    # Default center (USA mid-point) or last clicked position
    last_click = st.session_state.get("spot_last_click")
    center = [last_click["lat"], last_click["lng"]] if last_click else [39.5, -98.35]
    zoom = 12 if last_click else 4

    m = folium.Map(location=center, zoom_start=zoom)
    folium.TileLayer("OpenTopoMap").add_to(m)
    folium.TileLayer("OpenStreetMap").add_to(m)

    # Add trail route
    if route_df is not None and not route_df.empty:
        step = max(1, len(route_df) // 800)
        subset = route_df.iloc[::step]
        route_coords = list(zip(subset["latitude"], subset["longitude"]))
        folium.PolyLine(route_coords, weight=4, color="#eb25d1", opacity=1).add_to(m)
        # Fit map to trail if no click yet
        if not last_click:
            m.fit_bounds([
                [route_df["latitude"].min(), route_df["longitude"].min()],
                [route_df["latitude"].max(), route_df["longitude"].max()],
            ])

    folium.LayerControl().add_to(m)

    # Add marker at last clicked position
    if last_click:
        folium.Marker(
            location=[last_click["lat"], last_click["lng"]],
            popup=f"📍 {last_click['lat']:.4f}, {last_click['lng']:.4f}",
            icon=folium.Icon(color="red", icon="info-sign"),
        ).add_to(m)

    map_data = st_folium(
        m,
        use_container_width=True,
        height=500,
        returned_objects=["last_clicked"],
    )

    # ── Process click ─────────────────────────────────────────────
    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        lat = clicked["lat"]
        lng = clicked["lng"]

        # Only fetch if the click location changed
        prev = st.session_state.get("spot_last_click")
        if prev is None or prev["lat"] != lat or prev["lng"] != lng:
            st.session_state.spot_last_click = {"lat": lat, "lng": lng}
            st.session_state.spot_weather_df = None  # clear old data
            st.rerun()

    # ── Show coordinates ──────────────────────────────────────────
    if last_click:
        st.info(f"📍 Selected position: **{last_click['lat']:.4f}°N, {last_click['lng']:.4f}°E**")

        # Fetch button
        if st.button("⚡ Load Weather", type="primary", key="spot_load_weather"):
            with st.spinner("🌤️ Fetching weather data…"):
                try:
                    responses = fetch_weather(
                        [last_click["lat"]],
                        [last_click["lng"]],
                        start_date,
                        end_date,
                        temperature_unit,
                        "UTC",
                        wind_speed_unit_api,
                    )
                    weather_df = process_weather_responses(
                        responses,
                        [0.0],  # dummy mile marker
                        [last_click["lat"]],
                        [last_click["lng"]],
                        temp_symbol,
                        "UTC",
                        wind_unit,
                        rain_unit,
                        snow_unit,
                    )
                    st.session_state.spot_weather_df = weather_df
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Could not load weather data: {e}")
    else:
        st.info("👆 Click on the map to select a location.")

    # ── Display weather results ───────────────────────────────────
    if st.session_state.get("spot_weather_df") is not None:
        weather_df = st.session_state.spot_weather_df

        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('<p class="section-header">🌤️ Weather Results</p>', unsafe_allow_html=True)

        temp_max_col = f"Temp Max ({temp_symbol})"
        temp_min_col = f"Temp Min ({temp_symbol})"
        rain_col = f"Rain ({rain_unit})"
        snow_col = f"Snow ({snow_unit})"
        wind_col = f"💨 Wind Max ({wind_unit})"
        gust_col = f"💨 Gusts ({wind_unit})"

        # Summary metrics
        if len(weather_df) > 0:
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric(f"🌡️ Max Temp", f"{weather_df[temp_max_col].max():.1f} {temp_symbol}")
            with m2:
                st.metric(f"🌡️ Min Temp", f"{weather_df[temp_min_col].min():.1f} {temp_symbol}")
            with m3:
                st.metric(f"🌧️ Total Rain", f"{weather_df[rain_col].sum():.1f} {rain_unit}")
            with m4:
                st.metric(f"❄️ Total Snow", f"{weather_df[snow_col].sum():.1f} {snow_unit}")
            with m5:
                st.metric(f"💨 Max Wind", f"{weather_df[wind_col].max():.1f} {wind_unit}")

        # Charts
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            temp_chart = build_temperature_chart(weather_df, temp_symbol, None, x_col="Date")
            if temp_chart:
                st.plotly_chart(temp_chart, width="stretch")
            precip_chart = build_precipitation_chart(weather_df, None, rain_unit, snow_unit, x_col="Date")
            if precip_chart:
                st.plotly_chart(precip_chart, width="stretch")
        with col_c2:
            wind_chart = build_wind_chart(weather_df, None, wind_unit, x_col="Date")
            if wind_chart:
                st.plotly_chart(wind_chart, width="stretch")
            sunrise_chart = build_sunrise_sunset_chart(weather_df, None, x_col="Date")
            if sunrise_chart:
                st.plotly_chart(sunrise_chart, width="stretch")

        # Data table
        display_cols = {
            "Date": "Date",
            temp_max_col: temp_max_col,
            temp_min_col: temp_min_col,
            rain_col: rain_col,
            snow_col: snow_col,
            wind_col: wind_col,
            gust_col: gust_col,
            "🌅 Sunrise": "🌅 Sunrise",
            "🌇 Sunset": "🌇 Sunset",
            "☀️ Daylight (h)": "☀️ Daylight",
            "Weather": "Weather",
        }
        show_cols = [c for c in display_cols.keys() if c in weather_df.columns]
        st.dataframe(
            weather_df[show_cols],
            hide_index=True,
            width="stretch",
        )
