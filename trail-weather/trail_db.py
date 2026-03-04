"""
Trail Weather App – SQLite Database Module
Persists uploaded custom trails so they survive container restarts.

DB location: /app/uploads/trails.db (mounted as Docker volume)
"""

import sqlite3
import os
import json
from datetime import datetime

import pandas as pd

DB_DIR = os.environ.get("TRAIL_UPLOADS_DIR", os.path.join(os.path.dirname(__file__), "uploads"))
DB_PATH = os.path.join(DB_DIR, "trails.db")


def _get_conn():
    """Get a SQLite connection, creating the DB + tables if needed."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trails (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            mile_interval INTEGER NOT NULL DEFAULT 10,
            num_trackpoints INTEGER NOT NULL DEFAULT 0,
            num_milemarkers INTEGER NOT NULL DEFAULT 0,
            total_miles REAL    NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL,
            UNIQUE(name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trackpoints (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            trail_id INTEGER NOT NULL,
            idx      INTEGER NOT NULL,
            latitude REAL    NOT NULL,
            longitude REAL   NOT NULL,
            elevation REAL,
            FOREIGN KEY (trail_id) REFERENCES trails(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS milemarkers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trail_id    INTEGER NOT NULL,
            direction   TEXT    NOT NULL,  -- 'NOBO' or 'SOBO'
            mile_marker INTEGER NOT NULL,
            latitude    REAL    NOT NULL,
            longitude   REAL    NOT NULL,
            FOREIGN KEY (trail_id) REFERENCES trails(id) ON DELETE CASCADE
        )
    """)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return conn


def save_trail(trail_name, mile_interval, trackpoints_df, mm_nobo_df, mm_sobo_df):
    """Save a processed trail to the database. Overwrites if name exists."""
    conn = _get_conn()
    try:
        # Delete existing trail with same name
        existing = conn.execute("SELECT id FROM trails WHERE name = ?", (trail_name,)).fetchone()
        if existing:
            conn.execute("DELETE FROM trails WHERE id = ?", (existing[0],))

        total_miles = float(mm_nobo_df["mile_marker"].max()) if len(mm_nobo_df) > 0 else 0

        conn.execute(
            "INSERT INTO trails (name, mile_interval, num_trackpoints, num_milemarkers, total_miles, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (trail_name, mile_interval, len(trackpoints_df), len(mm_nobo_df), total_miles,
             datetime.now().isoformat()),
        )
        trail_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Save trackpoints
        tp_rows = []
        for idx, row in trackpoints_df.iterrows():
            tp_rows.append((
                trail_id, int(idx),
                float(row["latitude"]), float(row["longitude"]),
                float(row["elevation"]) if "elevation" in row and pd.notna(row.get("elevation")) else None,
            ))
        conn.executemany(
            "INSERT INTO trackpoints (trail_id, idx, latitude, longitude, elevation) VALUES (?, ?, ?, ?, ?)",
            tp_rows,
        )

        # Save mile markers (NOBO + SOBO)
        mm_rows = []
        for _, row in mm_nobo_df.iterrows():
            mm_rows.append((trail_id, "NOBO", int(row["mile_marker"]),
                           float(row["latitude"]), float(row["longitude"])))
        for _, row in mm_sobo_df.iterrows():
            mm_rows.append((trail_id, "SOBO", int(row["mile_marker"]),
                           float(row["latitude"]), float(row["longitude"])))
        conn.executemany(
            "INSERT INTO milemarkers (trail_id, direction, mile_marker, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?)",
            mm_rows,
        )

        conn.commit()
        return trail_id
    finally:
        conn.close()


def list_saved_trails():
    """Return a list of saved trail dicts (id, name, stats, created_at)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, mile_interval, num_trackpoints, num_milemarkers, "
            "total_miles, created_at FROM trails ORDER BY name"
        ).fetchall()
        return [
            {
                "id": r[0], "name": r[1], "mile_interval": r[2],
                "num_trackpoints": r[3], "num_milemarkers": r[4],
                "total_miles": r[5], "created_at": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


def load_trail(trail_id):
    """Load a trail from the database and return the same dict format as gpx_upload."""
    conn = _get_conn()
    try:
        trail = conn.execute("SELECT id, name FROM trails WHERE id = ?", (trail_id,)).fetchone()
        if not trail:
            return None

        # Trackpoints
        tp_rows = conn.execute(
            "SELECT latitude, longitude, elevation FROM trackpoints "
            "WHERE trail_id = ? ORDER BY idx",
            (trail_id,),
        ).fetchall()
        tp_data = [{"latitude": r[0], "longitude": r[1], "elevation": r[2]} for r in tp_rows]
        trackpoints_df = pd.DataFrame(tp_data)

        # Mile markers NOBO
        mm_nobo_rows = conn.execute(
            "SELECT mile_marker, latitude, longitude FROM milemarkers "
            "WHERE trail_id = ? AND direction = 'NOBO' ORDER BY mile_marker",
            (trail_id,),
        ).fetchall()
        mm_nobo_df = pd.DataFrame(mm_nobo_rows, columns=["mile_marker", "latitude", "longitude"])

        # Mile markers SOBO
        mm_sobo_rows = conn.execute(
            "SELECT mile_marker, latitude, longitude FROM milemarkers "
            "WHERE trail_id = ? AND direction = 'SOBO' ORDER BY mile_marker",
            (trail_id,),
        ).fetchall()
        mm_sobo_df = pd.DataFrame(mm_sobo_rows, columns=["mile_marker", "latitude", "longitude"])

        return {
            "trackpoints_df": trackpoints_df,
            "mm_nobo_df": mm_nobo_df,
            "mm_sobo_df": mm_sobo_df,
            "trail_name": trail[1],
        }
    finally:
        conn.close()


def delete_trail(trail_id):
    """Delete a trail and all its data from the database."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM milemarkers WHERE trail_id = ?", (trail_id,))
        conn.execute("DELETE FROM trackpoints WHERE trail_id = ?", (trail_id,))
        conn.execute("DELETE FROM trails WHERE id = ?", (trail_id,))
        conn.commit()
    finally:
        conn.close()
