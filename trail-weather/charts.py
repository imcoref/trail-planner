"""
Trail Weather App – Chart Builder Module
Creates Plotly charts: temperature, precipitation, wind, elevation profile,
weather distribution, and year-over-year comparison.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import streamlit as st


# ─── Dark theme template ─────────────────────────────────────────────
DARK_TEMPLATE = "plotly_dark"
CHART_BG = "rgba(0,0,0,0)"
PAPER_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.1)"

def _dark_layout(**kwargs):
    """Return common dark theme layout settings."""
    base = dict(
        template=DARK_TEMPLATE,
        plot_bgcolor=CHART_BG,
        paper_bgcolor=PAPER_BG,
        font=dict(color="#e2e8f0"),
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    base.update(kwargs)
    return base


def build_temperature_chart(df, temp_symbol, selected_date=None):
    """Temperature range chart across mile markers."""
    day_df = df[df["Date"] == selected_date].copy() if selected_date else df.copy()
    if day_df.empty:
        return None

    temp_max_col = f"Temp Max ({temp_symbol})"
    temp_min_col = f"Temp Min ({temp_symbol})"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=day_df["Mile Marker"], y=day_df[temp_max_col],
        mode="lines+markers", name=f"Max {temp_symbol}",
        line=dict(color="#ef4444", width=2), marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=day_df["Mile Marker"], y=day_df[temp_min_col],
        mode="lines+markers", name=f"Min {temp_symbol}",
        line=dict(color="#3b82f6", width=2), marker=dict(size=5),
        fill="tonexty", fillcolor="rgba(59,130,246,0.15)",
    ))

    title = "🌡️ Temperature"
    if selected_date:
        title += f" — {selected_date}"
    fig.update_layout(**_dark_layout(
        title=title, xaxis_title="Mile Marker",
        yaxis_title=f"Temperature ({temp_symbol})", height=320,
    ))
    fig.update_xaxes(gridcolor=GRID_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR)
    return fig


def build_precipitation_chart(df, selected_date=None, rain_unit="mm", snow_unit="cm"):
    """Precipitation chart (rain + snow) across mile markers."""
    day_df = df[df["Date"] == selected_date].copy() if selected_date else df.copy()
    if day_df.empty:
        return None

    rain_col = f"Rain ({rain_unit})"
    snow_col = f"Snow ({snow_unit})"
    
    if rain_col not in day_df.columns:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=day_df["Mile Marker"], y=day_df[rain_col],
        name="🌧️ Rain", marker_color="#3b82f6", opacity=0.8,
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=day_df["Mile Marker"], y=day_df[snow_col],
        name="❄️ Snow", marker_color="#93c5fd", opacity=0.8,
    ), secondary_y=True)

    title = "🌧️ Precipitation"
    if selected_date:
        title += f" — {selected_date}"
    fig.update_layout(**_dark_layout(title=title, xaxis_title="Mile Marker", height=300, barmode="group"))
    fig.update_yaxes(title_text=f"Rain ({rain_unit})", secondary_y=False, gridcolor=GRID_COLOR)
    fig.update_yaxes(title_text=f"Snow ({snow_unit})", secondary_y=True, gridcolor=GRID_COLOR)
    fig.update_xaxes(gridcolor=GRID_COLOR)
    return fig


def build_wind_chart(df, selected_date=None, wind_unit="km/h"):
    """Wind speed and gust chart across mile markers."""
    day_df = df[df["Date"] == selected_date].copy() if selected_date else df.copy()
    if day_df.empty:
        return None

    wind_col = f"💨 Wind Max ({wind_unit})"
    gust_col = f"💨 Gusts ({wind_unit})"
    if wind_col not in day_df.columns:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=day_df["Mile Marker"], y=day_df[gust_col],
        mode="lines+markers", name="Gusts",
        line=dict(color="#f97316", width=2, dash="dot"), marker=dict(size=4),
        fill="tozeroy", fillcolor="rgba(249,115,22,0.1)",
    ))
    fig.add_trace(go.Scatter(
        x=day_df["Mile Marker"], y=day_df[wind_col],
        mode="lines+markers", name="Max Wind",
        line=dict(color="#22c55e", width=2), marker=dict(size=5),
    ))

    # Danger threshold line (80 km/h or ~50 mph)
    danger_threshold = 80 if wind_unit == "km/h" else 50
    fig.add_hline(y=danger_threshold, line_dash="dash", line_color="#ef4444", opacity=0.5,
                  annotation_text="⚠️ Danger", annotation_position="top left")

    title = "💨 Wind Speed"
    if selected_date:
        title += f" — {selected_date}"
    fig.update_layout(**_dark_layout(
        title=title, xaxis_title="Mile Marker",
        yaxis_title=wind_unit, height=300,
    ))
    fig.update_xaxes(gridcolor=GRID_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR)
    return fig


def build_sunrise_sunset_chart(df, selected_date=None):
    """Sunrise/Sunset timeline showing the daylight window per mile marker."""
    day_df = df[df["Date"] == selected_date].copy() if selected_date else df.copy()
    if day_df.empty or "_sunrise_h" not in day_df.columns:
        return None

    # For "All Days" mode, average sunrise/sunset per mile marker
    if selected_date is None:
        day_df = day_df.groupby("Mile Marker").agg({
            "_sunrise_h": "mean", "_sunset_h": "mean"
        }).reset_index()

    sunrise = day_df["_sunrise_h"]
    sunset = day_df["_sunset_h"]
    daylight = sunset - sunrise

    fig = go.Figure()

    # Dark before sunrise (invisible spacer)
    fig.add_trace(go.Bar(
        x=day_df["Mile Marker"], y=sunrise,
        name="Night", marker_color="rgba(0,0,0,0)",
        showlegend=False, hoverinfo="skip",
    ))

    # Daylight window (stacked on top of spacer)
    fig.add_trace(go.Bar(
        x=day_df["Mile Marker"], y=daylight,
        name="☀️ Daylight",
        marker_color="#fbbf24",
        opacity=0.85,
        customdata=list(zip(
            [f"{int(h)}:{int((h % 1) * 60):02d}" for h in sunrise],
            [f"{int(h)}:{int((h % 1) * 60):02d}" for h in sunset],
            np.round(daylight, 1),
        )),
        hovertemplate="Mile %{x}<br>🌅 Sunrise: %{customdata[0]}<br>🌇 Sunset: %{customdata[1]}<br>☀️ %{customdata[2]}h daylight<extra></extra>",
    ))

    title = "🌅 Sunrise / Sunset"
    if selected_date:
        title += f" — {selected_date}"

    fig.update_layout(**_dark_layout(
        title=title, xaxis_title="Mile Marker",
        yaxis_title="Time of Day", height=300,
        barmode="stack",
    ))
    # Y-axis: show as hours (6:00 to 20:00)
    fig.update_yaxes(
        range=[5, 21],
        tickvals=[6, 8, 10, 12, 14, 16, 18, 20],
        ticktext=["6:00", "8:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"],
        gridcolor=GRID_COLOR,
    )
    fig.update_xaxes(gridcolor=GRID_COLOR)
    return fig


def build_weather_summary_chart(df):
    """Pie chart of weather condition distribution."""
    weather_counts = df["Weather"].value_counts().head(10)
    fig = go.Figure(data=[go.Pie(
        labels=weather_counts.index, values=weather_counts.values,
        hole=0.45, textposition="inside", textinfo="percent+label",
    )])
    fig.update_layout(**_dark_layout(
        title="🌤️ Weather Distribution", height=350,
        showlegend=False,
    ))
    return fig


@st.cache_data(show_spinner=False, ttl=None)
def build_elevation_profile(elev_df, mm_df=None, start_mm=None, end_mm=None):
    """Build an elevation profile from pre-computed elevation CSV data.

    Args:
        elev_df: DataFrame with distance_miles, elevation_m columns
        mm_df: Mile marker DataFrame (optional, for reference markers)
        start_mm: Start mile marker for highlight range
        end_mm: End mile marker for highlight range
    """
    if elev_df is None or elev_df.empty:
        return None

    dist = elev_df["distance_miles"].values
    elev_m = elev_df["elevation_m"].values
    elev_ft = elev_m * 3.281

    # Scale distance to match mile marker range
    total_trail_dist = dist[-1]
    if mm_df is not None and not mm_df.empty:
        total_trail_miles = mm_df["mile_marker"].max()
        # Scale distance to match MM numbering
        scaled_dist = dist * (total_trail_miles / total_trail_dist) if total_trail_dist > 0 else dist
    else:
        scaled_dist = dist

    fig = go.Figure()

    # Selected range highlight (behind main line)
    if start_mm is not None and end_mm is not None:
        mask = (scaled_dist >= start_mm) & (scaled_dist <= end_mm)
        if mask.any():
            fig.add_trace(go.Scatter(
                x=scaled_dist[mask], y=elev_m[mask],
                mode="lines", name="Selected Range",
                line=dict(color="#22c55e", width=2.5),
                fill="tozeroy", fillcolor="rgba(34,197,94,0.25)",
                hovertemplate="Mile %{x:.0f}<br>%{y:.0f}m / %{customdata:.0f}ft<extra></extra>",
                customdata=elev_ft[mask],
            ))

    # Full trail profile (dimmed)
    fig.add_trace(go.Scatter(
        x=scaled_dist, y=elev_m,
        mode="lines", name="Elevation",
        line=dict(color="#64748b", width=1),
        hovertemplate="Mile %{x:.0f}<br>%{y:.0f}m / %{customdata:.0f}ft<extra></extra>",
        customdata=elev_ft,
    ))

    fig.update_layout(**_dark_layout(
        title="🏔️ Elevation Profile",
        xaxis_title="Mile Marker",
        yaxis_title="Elevation (m)",
        height=320,
    ))
    fig.update_xaxes(gridcolor=GRID_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR)
    return fig


def build_year_comparison_chart(df_current, df_previous, temp_symbol, year_current, year_previous):
    """Side-by-side temperature comparison between two years."""
    if df_current is None or df_previous is None:
        return None
    if df_current.empty or df_previous.empty:
        return None

    temp_max_col = f"Temp Max ({temp_symbol})"
    temp_min_col = f"Temp Min ({temp_symbol})"

    # Aggregate by mile marker
    curr_avg = df_current.groupby("Mile Marker").agg({
        temp_max_col: "mean", temp_min_col: "mean"
    }).reset_index()
    prev_avg = df_previous.groupby("Mile Marker").agg({
        temp_max_col: "mean", temp_min_col: "mean"
    }).reset_index()

    fig = go.Figure()

    # Previous year (dashed)
    fig.add_trace(go.Scatter(
        x=prev_avg["Mile Marker"], y=prev_avg[temp_max_col],
        mode="lines", name=f"{year_previous} Max",
        line=dict(color="#f97316", width=2, dash="dot"),
    ))
    fig.add_trace(go.Scatter(
        x=prev_avg["Mile Marker"], y=prev_avg[temp_min_col],
        mode="lines", name=f"{year_previous} Min",
        line=dict(color="#38bdf8", width=2, dash="dot"),
    ))

    # Current year (solid)
    fig.add_trace(go.Scatter(
        x=curr_avg["Mile Marker"], y=curr_avg[temp_max_col],
        mode="lines+markers", name=f"{year_current} Max",
        line=dict(color="#ef4444", width=2), marker=dict(size=4),
    ))
    fig.add_trace(go.Scatter(
        x=curr_avg["Mile Marker"], y=curr_avg[temp_min_col],
        mode="lines+markers", name=f"{year_current} Min",
        line=dict(color="#3b82f6", width=2), marker=dict(size=4),
    ))

    fig.update_layout(**_dark_layout(
        title=f"📅 Year Comparison: {year_current} vs {year_previous}",
        xaxis_title="Mile Marker",
        yaxis_title=f"Avg Temperature ({temp_symbol})",
        height=350,
    ))
    fig.update_xaxes(gridcolor=GRID_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR)
    return fig
