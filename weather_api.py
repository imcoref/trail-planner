"""
Trail Weather App – Weather API Module
Handles all Open-Meteo API interactions.
Includes wind data, daylight/sunrise/sunset, and danger alert detection.
"""

import streamlit as st
import openmeteo_requests
import requests_cache
import pandas as pd
import numpy as np
from retry_requests import retry

from data.weatherData_decoded import wmoData

# ─── Weather Emoji Mapping ──────────────────────────────────────────

WEATHER_EMOJI = {
    "Clear": "☀️",
    "Mostly Clear": "🌤️",
    "Partly Cloudy": "⛅",
    "Cloudy": "☁️",
    "Fog": "🌫️",
    "Freezing Fog": "🌫️❄️",
    "Light Drizzle": "🌦️",
    "Drizzle": "🌦️",
    "Heavy Drizzle": "🌧️",
    "Light Freezing Drizzle": "🌧️❄️",
    "Freezing Drizzle": "🌧️❄️",
    "Light Rain": "🌦️",
    "Rain": "🌧️",
    "Heavy Rain": "🌧️💧",
    "Light Freezing Rain": "🌧️❄️",
    "Freezing Rain": "🧊🌧️",
    "Light Snow": "🌨️",
    "Snow": "❄️",
    "Heavy Snow": "❄️❄️",
    "Snow Grains": "🌨️",
    "Light Rain Shower": "🌦️",
    "Rain Shower": "🌧️",
    "Heavy Rain Shower": "⛈️",
    "Snow Shower": "🌨️",
    "Heavy Snow Shower": "❄️⛈️",
    "Thunderstorm": "⛈️",
    "Hailstorm": "⛈️🧊",
    "Heavy Hailstorm": "⛈️🧊💥",
}

# ─── Danger Weather Names ────────────────────────────────────────────
DANGER_WEATHER_NAMES = {
    "Heavy Rain", "Freezing Rain", "Heavy Snow", "Heavy Rain Shower",
    "Heavy Snow Shower", "Thunderstorm", "Hailstorm", "Heavy Hailstorm",
}


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_weather(latitudes, longitudes, start_date, end_date, temp_unit, timezone, wind_speed_unit="kmh"):
    """Fetch historical weather data from Open-Meteo Archive API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "daily": [
            "weather_code",            # 0
            "temperature_2m_max",      # 1
            "temperature_2m_min",      # 2
            "rain_sum",                # 3
            "snowfall_sum",            # 4
            "precipitation_hours",     # 5
            "sunrise",                 # 6  (int64 unix ts)
            "sunset",                  # 7  (int64 unix ts)
            "daylight_duration",       # 8
            "wind_speed_10m_max",      # 9
            "wind_gusts_10m_max",      # 10
        ],
        "temperature_unit": temp_unit,
        "wind_speed_unit": wind_speed_unit,
        "timezone": timezone,
    }
    return openmeteo.weather_api(url, params=params)


def fetch_forecast(latitudes, longitudes, temp_unit, timezone, wind_speed_unit="kmh", forecast_days=7):
    """Fetch forecast weather data from Open-Meteo Forecast API."""
    url = "https://api.open-meteo.com/v1/forecast"
    cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "daily": [
            "weather_code",            # 0
            "temperature_2m_max",      # 1
            "temperature_2m_min",      # 2
            "rain_sum",                # 3
            "snowfall_sum",            # 4
            "precipitation_hours",     # 5
            "sunrise",                 # 6  (int64 unix ts)
            "sunset",                  # 7  (int64 unix ts)
            "daylight_duration",       # 8
            "wind_speed_10m_max",      # 9
            "wind_gusts_10m_max",      # 10
        ],
        "temperature_unit": temp_unit,
        "wind_speed_unit": wind_speed_unit,
        "timezone": timezone,
        "forecast_days": forecast_days,
    }
    return openmeteo.weather_api(url, params=params)


def process_weather_responses(responses, mile_markers, latitudes, longitudes, temp_symbol, timezone="UTC",
                               wind_unit="km/h", rain_unit="mm", snow_unit="cm"):
    """Process raw API responses into a formatted DataFrame with all weather data.
    
    Args:
        responses: Raw API responses
        mile_markers: List of mile marker values
        latitudes: List of latitudes
        longitudes: List of longitudes
        temp_symbol: Temperature symbol (°C or °F)
        timezone: Timezone string
        wind_unit: Wind unit (km/h or mph)
        rain_unit: Rain unit (mm or in)
        snow_unit: Snow unit (cm or in)
    """
    all_rows = []
    
    # Conversion factors for imperial units
    is_metric = rain_unit == "mm"
    mm_to_inch = 0.0393701
    cm_to_inch = 0.393701

    for i, response in enumerate(responses):
        daily = response.Daily()
        dates = pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s"),
            end=pd.to_datetime(daily.TimeEnd(), unit="s"),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left",
        )

        daily_weather_code = daily.Variables(0).ValuesAsNumpy()
        weather_text = [wmoData.get(code, f"Unknown ({code})") for code in daily_weather_code]
        weather_with_emoji = [
            f"{WEATHER_EMOJI.get(txt, '🌡️')} {txt}" for txt in weather_text
        ]

        # Sunrise/Sunset: int64 unix timestamps → local time strings (vectorized)
        try:
            sunrise_ts = daily.Variables(6).ValuesInt64AsNumpy()
            sunset_ts = daily.Variables(7).ValuesInt64AsNumpy()
            
            # Vectorized conversion
            sunrise_dt = pd.to_datetime(sunrise_ts, unit="s", utc=True).tz_convert(timezone)
            sunset_dt = pd.to_datetime(sunset_ts, unit="s", utc=True).tz_convert(timezone)
            
            sunrise_times = sunrise_dt.strftime("%H:%M").tolist()
            sunset_times = sunset_dt.strftime("%H:%M").tolist()
            
            # Decimal hours for charting (vectorized)
            sunrise_hours = (sunrise_dt.hour + sunrise_dt.minute / 60.0).tolist()
            sunset_hours = (sunset_dt.hour + sunset_dt.minute / 60.0).tolist()
        except Exception:
            sunrise_times = ["--:--"] * len(dates)
            sunset_times = ["--:--"] * len(dates)
            sunrise_hours = [0.0] * len(dates)
            sunset_hours = [0.0] * len(dates)

        daylight_seconds = daily.Variables(8).ValuesAsNumpy()
        daylight_hours = np.round(daylight_seconds / 3600.0, 1)
        
        # Get raw values
        rain_raw = daily.Variables(3).ValuesAsNumpy()
        snow_raw = daily.Variables(4).ValuesAsNumpy()
        
        # Convert if imperial
        if is_metric:
            rain_values = rain_raw
            snow_values = snow_raw
        else:
            rain_values = rain_raw * mm_to_inch
            snow_values = snow_raw * cm_to_inch

        df_point = pd.DataFrame({
            "Date": dates,
            "Mile Marker": mile_markers[i],
            "Latitude": latitudes[i],
            "Longitude": longitudes[i],
            f"Temp Max ({temp_symbol})": daily.Variables(1).ValuesAsNumpy(),
            f"Temp Min ({temp_symbol})": daily.Variables(2).ValuesAsNumpy(),
            f"Rain ({rain_unit})": rain_values,
            f"Snow ({snow_unit})": snow_values,
            "Precip Hours": daily.Variables(5).ValuesAsNumpy(),
            "🌅 Sunrise": sunrise_times,
            "🌇 Sunset": sunset_times,
            "_sunrise_h": sunrise_hours,
            "_sunset_h": sunset_hours,
            "☀️ Daylight (h)": daylight_hours,
            f"💨 Wind Max ({wind_unit})": daily.Variables(9).ValuesAsNumpy(),
            f"💨 Gusts ({wind_unit})": daily.Variables(10).ValuesAsNumpy(),
            "Weather": weather_with_emoji,
            "_weather_text": weather_text,
        })
        all_rows.append(df_point)

    final_df = pd.concat(all_rows, ignore_index=True)
    final_df["Date"] = final_df["Date"].dt.strftime("%b %d, %Y")

    # Round numeric columns (except internal ones and coordinates)
    skip = {"_weather_code", "Latitude", "Longitude", "☀️ Daylight (h)"}
    
    # For imperial units, keep 2 decimal places for rain/snow (inches)
    rain_col = f"Rain ({rain_unit})"
    snow_col = f"Snow ({snow_unit})"
    
    for c in final_df.select_dtypes(include=[np.number]).columns:
        if c in skip:
            continue
        if not is_metric and c in [rain_col, snow_col]:
            # Round to 2 decimal places for imperial precipitation
            final_df[c] = np.round(final_df[c], 2)
        else:
            # Round to integer for other columns
            final_df[c] = np.round(final_df[c]).astype("Int64")

    return final_df


def detect_danger_alerts(df, temp_symbol, wind_unit="km/h"):
    """Detect dangerous weather conditions using vectorized pandas operations."""
    alerts = []
    temp_min_col = f"Temp Min ({temp_symbol})"
    temp_max_col = f"Temp Max ({temp_symbol})"
    freeze_thresh = 0 if temp_symbol == "°C" else 32
    heat_thresh = 40 if temp_symbol == "°C" else 104

    # Vectorized: Freezing temperatures
    if temp_min_col in df.columns:
        freezing = df[pd.to_numeric(df[temp_min_col], errors="coerce") <= freeze_thresh]
        for _, row in freezing.iterrows():
            alerts.append({
                "type": "🥶 Freezing", "severity": "warning",
                "message": f"Mile {row['Mile Marker']} on {row['Date']}: Min temp {row[temp_min_col]}{temp_symbol}",
            })

    # Vectorized: Extreme heat
    if temp_max_col in df.columns:
        hot = df[pd.to_numeric(df[temp_max_col], errors="coerce") >= heat_thresh]
        for _, row in hot.iterrows():
            alerts.append({
                "type": "🔥 Extreme Heat", "severity": "error",
                "message": f"Mile {row['Mile Marker']} on {row['Date']}: Max temp {row[temp_max_col]}{temp_symbol}",
            })

    # Vectorized: Dangerous weather codes
    if "_weather_text" in df.columns:
        danger_wx = df[df["_weather_text"].isin(DANGER_WEATHER_NAMES)]
        for _, row in danger_wx.iterrows():
            alerts.append({
                "type": f"⚠️ {row['_weather_text']}", "severity": "error",
                "message": f"Mile {row['Mile Marker']} on {row['Date']}: {row['_weather_text']}",
            })

    # Vectorized: High wind gusts (80 km/h or ~50 mph)
    gust_col = f"💨 Gusts ({wind_unit})"
    gust_thresh = 80 if wind_unit == "km/h" else 50
    gust_severe = 100 if wind_unit == "km/h" else 62
    if gust_col in df.columns:
        gusts = pd.to_numeric(df[gust_col], errors="coerce")
        high_wind = df[gusts >= gust_thresh]
        for _, row in high_wind.iterrows():
            gust_val = float(row[gust_col])
            alerts.append({
                "type": "💨 High Wind",
                "severity": "error" if gust_val >= gust_severe else "warning",
                "message": f"Mile {row['Mile Marker']} on {row['Date']}: Gusts {gust_val} {wind_unit}",
            })

    # Deduplicate
    seen = set()
    unique = []
    for a in alerts:
        key = (a["type"], a["message"])
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique
