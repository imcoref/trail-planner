#!/usr/bin/env python3
import argparse
import os
import gpxpy
import pandas as pd
from pyproj import Geod





colors = [
    "#FF0000",  # rot
    "#00AA00",  # grün
    "#0000FF",  # blau
    "#FFFF00",  # gelb
    "#FFA500",  # orange
    "#800080"   # lila
]

def existing_file(path):
    """Prüft, ob die Datei existiert."""
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f"Input file doesnot exist: {path}")
    return path

def examine_file(input_file_name):
    # Load and parse the GPX file
    gpx_file = open(input_file_name, 'r')
    gpx = gpxpy.parse(gpx_file)
    for track in gpx.tracks:
        print(track.name)
    return

def convert_gpx_to_csv(input_file_name, track_names, trailname):
    # Load and parse the GPX file
    gpx_file = open(input_file_name, 'r')
    gpx = gpxpy.parse(gpx_file)

    data = []
    i = 0

     # Iterate through all tracks
    for track in gpx.tracks:
        
        if track.name is None or  track.name.startswith(tuple(track_names)): 
            i = i + 1
            # Iterate through all segments within a track
            for segment in track.segments:
                for point in segment.points:
                    if track.name is None:
                        track.name = trailname
                    data.append({
                        'track_name': track.name,  # Helpful to identify which track
                        #'time': point.time,
                        'latitude': point.latitude,
                        'longitude': point.longitude,
                        'color' : colors[i % len(colors)]
                        #'elevation': point.elevation
                    })

    # Create DataFrame
    df = pd.DataFrame(data)

    df.to_csv('./data/' + trailname  + '_trackpoints.csv', index=False)


def calculate_milemarkers( trailname, direction_label, interval_miles):

    # ==========================
    # Milemarker calculation
    # ==========================
    interval_meters = float(interval_miles) * 1609.344
    geod = Geod(ellps="WGS84")

    input_csv = './data/' + trailname  + '_trackpoints.csv'
    output_csv = './data/' + trailname + '_MM_points_list_' + direction_label + '.csv' 

    df_original = pd.read_csv(input_csv)

    if direction_label == 'NOBO':
        df = df_original
    else:
        df = df_original.iloc[::-1].reset_index(drop=True)

    

    if len(df) < 2:
        raise ValueError("not enough trackpoints.")

    latitudes = df["latitude"].values
    longitudes = df["longitude"].values

    # ==========================
    # Add Mile 0
    # ==========================
    result = []

    result.append({
        "mile_marker": 0,
        "latitude": latitudes[0],
        "longitude": longitudes[0]
    })

    total_distance = 0.0
    next_target = interval_meters

    for i in range(1, len(df)):
        lon1 = longitudes[i - 1]
        lat1 = latitudes[i - 1]
        lon2 = longitudes[i]
        lat2 = latitudes[i]

        az12, az21, segment_length = geod.inv(lon1, lat1, lon2, lat2)

        while total_distance + segment_length >= next_target:
            remaining = next_target - total_distance
            lon_new, lat_new, _ = geod.fwd(lon1, lat1, az12, remaining)

            result.append({
                "mile_marker": round(next_target / 1609.344),
                "latitude": lat_new,
                "longitude": lon_new
            })

            next_target += interval_meters

        total_distance += segment_length

    out_df = pd.DataFrame(result)
    # filename = f"{output_csv}_{direction_label}.csv"
    out_df.to_csv(output_csv, index=False)

    print(f"{len(out_df)} points written to {output_csv}")
    print(f"Total length of track: {total_distance / 1609.344:.2f} miles\n")





def main():
    parser = argparse.ArgumentParser(
        description="gpx"
    )

    # Pflicht-Optionen
    parser.add_argument(
        "-i", "--input_file",
        required=True,
        type=existing_file,
        help="gpx-File for trail with (multiple) tracks"
    )

    parser.add_argument(
        "-e", "--examine",
        action="store_true",
        help="Examine gpx-File for tracks"
    )

    parser.add_argument(
        "-n", "--name_of_trail",
        metavar="STRING",
        help="Trail name e.g. PCT"
    )

   
    parser.add_argument(
        "-b", "--batch",
        nargs="+",              # beliebig viele, mindestens einer
        metavar="STRING",
        help="List of strings with beginning letters of desired tracks eg. OR CA"
    )

    parser.add_argument(
        "-m", "--mile_marker_file",
        metavar="STRING",
        help="generate milemarker file with given mile interval"
    )

    args = parser.parse_args()

    # if args.mile_marker_file and (args.batch or args.name_of_trail):
    #     parser.error("argument -b and -n are required")

    # if  not args.examine and not args.batch and not args.name_of_trail:
    #     parser.error("argument -b and -n are required")

    

    if args.examine:
        examine_file(args.input_file)
    else:
        convert_gpx_to_csv(args.input_file, args.batch, args.name_of_trail)

    if args.mile_marker_file:
        calculate_milemarkers(args.name_of_trail, 'NOBO', args.mile_marker_file)
        calculate_milemarkers(args.name_of_trail, 'SOBO', args.mile_marker_file)
if __name__ == "__main__":
    main()