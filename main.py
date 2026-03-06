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
from elevation_utils import (
    load_elevation_profile, get_segment_elevation_stats,
    plan_thru_hike, get_thru_hike_summary, recalculate_day_stats,
)
from pages_content import thru_hike_planner_page, history_weather_page, coming_soon_page


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
        "weather_by_mm_and_year_thru": None,
        "weather_history_df": None,
        "mm_range_coords": None,
        "last_unit_system": None,
        "last_nobo": None,
        "last_trail": None,
        "comparison_df": None,
        "thru_hike_days": None,
        "unit_system": "Metric",
        "show_mm": True,
        "show_poi": False,
        "reset_mm_range": False,
        "direction": "NOBO",
        "last_thru_params": None,
        "itinerary_manually_edited": False,
        "spot_weather_df": None,
        "spot_last_click": None,
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
    # Page config
    st.set_page_config(
        page_title="Trail Weather Tool",
        page_icon="🥾",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS
    st.markdown(
        """
        <style>
        /* ─── Shepherd Footer ─── */
        .shepherd-footer {
            margin-top: 2rem;
            padding: 1rem;
            text-align: center;
            color: #666;
            font-size: 0.9rem;
        }
        .shepherd-footer a {
            color: #0066cc;
            text-decoration: none;
        }
        .shepherd-footer a:hover {
            text-decoration: underline;
        }

        /* ─── Metric Cards with colored accents ─── */
        [data-testid="stMetric"] {
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(128, 128, 128, 0.2);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        }
        /* Colored left border accents for metrics via nth-of-type */
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-of-type(1) [data-testid="stMetric"] {
            border-left: 4px solid #3b82f6;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-of-type(2) [data-testid="stMetric"] {
            border-left: 4px solid #10b981;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-of-type(3) [data-testid="stMetric"] {
            border-left: 4px solid #f59e0b;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-of-type(4) [data-testid="stMetric"] {
            border-left: 4px solid #ef4444;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-of-type(5) [data-testid="stMetric"] {
            border-left: 4px solid #8b5cf6;
        }

        /* ─── Styled control card container ─── */
        .control-card {
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 16px;
            padding: 1.5rem 1.5rem 1rem 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
        }

        /* ─── Section dividers ─── */
        .section-divider {
            height: 3px;
            background: linear-gradient(90deg, transparent, rgba(59,130,246,0.3), transparent);
            border: none;
            margin: 2rem 0;
            border-radius: 2px;
        }
        .section-header {
            font-size: 1.6rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            letter-spacing: -0.02em;
        }

        /* ─── DataFrames ─── */
        .stDataFrame { border-radius: 8px; overflow: hidden; }

        /* ─── Expander refinements ─── */
        [data-testid="stExpander"] {
            border-radius: 12px;
            border: 1px solid rgba(128, 128, 128, 0.15);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    init_session_state()

    # Initialize additional page navigation state
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Thru-Hike  Planner"

    available_trails = get_available_trails()

    # ═══════════════════════════════════════════════════════════════
    # SIDEBAR - Trail Selection, Emblem, Page Navigation, Settings
    # ═══════════════════════════════════════════════════════════════

    # Trail Selector
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
    else:
        selected_trail = None
        trail_meta = None
        trail_files = None
        has_emblem = False
        emblem_path = None

    if trail_meta:
        trail_name_display = f"{trail_meta['emoji']} {trail_meta['name']}"
        timezone = trail_meta["timezone"]
    else:
        st.error("❌ No trail data available. Add trail CSVs to the data directory.")
        return

    # Reset weather data when trail changes
    if selected_trail != st.session_state.last_trail:
        st.session_state.mm_weather_df = None
        st.session_state.mm_range_coords = None
        st.session_state.comparison_df = None
        st.session_state.weather_by_mm_and_year = None
        st.session_state.weather_by_mm_and_year_thru = None
        st.session_state.weather_history_df = None
        st.session_state.thru_hike_days = None
        st.session_state.reset_mm_range = True
        # Explicitly set MM selectboxes to new trail's full range
        nobo_reset = st.session_state.direction == "NOBO"
        mm_file_reset = trail_files["mm_nobo"] if nobo_reset else trail_files["mm_sobo"]
        mm_df_reset = load_csv(mm_file_reset)
        mm_opts_reset = mm_df_reset["mile_marker"].tolist()
        st.session_state.start_mm_page = mm_opts_reset[0]
        st.session_state.end_mm_page = mm_opts_reset[-1]
        st.session_state.start_mm_weather = mm_opts_reset[0]
        st.session_state.end_mm_weather = mm_opts_reset[-1]
        st.session_state.last_trail = selected_trail
        st.rerun()

    st.sidebar.markdown("---")

    # ─── Page Navigation ──────────────────────────────────────────
    st.sidebar.markdown("### 🗺️ Navigation")
    page_options = [
        "🥾 Thru-Hike Planner",
        "📊 History Weather",
        "📍 Spot Weather"
    ]
    current_page = st.sidebar.radio(
        "Select Page",
        options=page_options,
        index=page_options.index(st.session_state.current_page) if st.session_state.current_page in page_options else 0,
        label_visibility="collapsed"
    )
    
    # Update session state if page changed
    if current_page != st.session_state.current_page:
        st.session_state.current_page = current_page
        st.rerun()

    st.sidebar.markdown("---")

    # ─── Settings ─────────────────────────────────────────────────
    st.sidebar.markdown("### Settings")
    
    # Get current values from session state
    is_metric = st.session_state.unit_system == "Metric"
    
    unit_system_new = st.sidebar.radio(
        "Units", 
        ["Metric", "Imperial"], 
        horizontal=True, 
        index=0 if is_metric else 1
    )
    if unit_system_new != st.session_state.unit_system:
        st.session_state.unit_system = unit_system_new
        st.session_state.mm_weather_df = None
        st.session_state.weather_by_mm_and_year = None
        st.session_state.weather_by_mm_and_year_thru = None
        st.session_state.weather_history_df = None
        st.session_state.comparison_df = None
        st.session_state.spot_weather_df = None
        st.rerun()

    col3, col4 = st.sidebar.columns(2)
    with col3:
        show_mm_new = st.checkbox("Mile Markers", value=st.session_state.show_mm)
        if show_mm_new != st.session_state.show_mm:
            st.session_state.show_mm = show_mm_new
            st.rerun()
    with col4:
        has_poi = trail_files and os.path.isfile(trail_files["poi"])
        show_poi_new = st.checkbox("POIs", value=st.session_state.show_poi, disabled=not has_poi)
        if show_poi_new != st.session_state.show_poi:
            st.session_state.show_poi = show_poi_new
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("Proudly presented by Shepherd 🇩🇪 🍺 🥨")

    # Donate button
    donate_img_path = os.path.join(os.path.dirname(__file__), "data", "donate.png")
    if os.path.isfile(donate_img_path):
        donate_b64 = load_emblem_b64(donate_img_path)
        st.sidebar.markdown(
            f'<a href="https://paypal.me/imcoref" target="_blank">'
            f'<img src="data:image/png;base64,{donate_b64}" '
            f'style="width:100%; max-width:200px; display:block; margin:0 auto; cursor:pointer;">'
            f'</a>',
            unsafe_allow_html=True,
        )

    # ═══════════════════════════════════════════════════════════════
    # MAIN CONTENT - Page Routing
    # ═══════════════════════════════════════════════════════════════

    # Load trail data (needed by all pages)
    nobo = st.session_state.direction == "NOBO"
    route_df = load_csv(trail_files["trackpoints"])
    mm_file = trail_files["mm_nobo"] if nobo else trail_files["mm_sobo"]
    mm_df = load_csv(mm_file)

    mm_options = mm_df["mile_marker"].tolist()

    # Apply URL params
    if available_trails:
        apply_url_params(available_trails, mm_options)

    # Route to appropriate page
    if current_page == "🥾 Thru-Hike Planner":
        thru_hike_planner_page(
            selected_trail=selected_trail,
            trail_meta=trail_meta,
            route_df=route_df,
            mm_df=mm_df,
            mm_options=mm_options
        )
    elif current_page == "📊 History Weather":
        history_weather_page(
            selected_trail=selected_trail,
            trail_meta=trail_meta,
            route_df=route_df,
            mm_df=mm_df,
            mm_options=mm_options,
            timezone=timezone
        )
    elif current_page == "📍 Spot Weather":
        coming_soon_page(route_df=route_df)

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
