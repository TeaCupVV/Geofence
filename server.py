"""
EPICS EVEI Geofence — Local Server
-----------------------------------
Serves the geofence-drawing webpage and receives finished polygons from it,
writing them straight into coordinates.csv on this computer. No download
step, no manual file transfer — computer_end.py on this same computer reads
coordinates.csv directly and watches it for changes.

CSV format (matches what computer_end.py's get_coordinates() expects):
    OUTER
    40.423700,-86.921200
    40.423800,-86.921300
    40.423650,-86.921100
    INNER
    40.423720,-86.921220
    ...

Run:
    pip install flask
    python server.py

Then open http://localhost:5000 in a browser on this computer.

If you need to draw the boundary from a DIFFERENT device (phone/laptop) than
the one wired to the Pico, change app.run() at the bottom to
app.run(host="0.0.0.0", port=5000) and open http://<this-computer-LAN-IP>:5000
from the other device instead.
"""

import csv
import os
import tempfile
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "coordinates.csv")


def read_existing_boards():
    """
    Parse the current coordinates.csv (OUTER/INNER label format) into
    {"outer": [(lat, lon), ...], "inner": [(lat, lon), ...]}.
    Empty lists if the file doesn't exist yet or a board hasn't been drawn.
    """
    boards = {"outer": [], "inner": []}
    if not os.path.exists(CSV_PATH):
        return boards

    current = None
    with open(CSV_PATH, "r", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            label = row[0].strip().upper()
            if label in ("OUTER", "INNER") and len(row) == 1:
                current = label.lower()
            elif current and len(row) >= 2:
                try:
                    boards[current].append((float(row[0]), float(row[1])))
                except ValueError:
                    pass  # skip malformed row rather than fail the whole read
    return boards


def write_boards(boards):
    """
    Atomic write: write to a temp file in the same directory, then os.replace()
    it over the real file. This guarantees computer_end.py never reads a
    half-written CSV, even if it happens to poll mid-write.
    """
    fd, tmp_path = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.writer(f)
            if boards["outer"]:
                writer.writerow(["OUTER"])
                for lat, lon in boards["outer"]:
                    writer.writerow([f"{lat:.6f}", f"{lon:.6f}"])
            if boards["inner"]:
                writer.writerow(["INNER"])
                for lat, lon in boards["inner"]:
                    writer.writerow([f"{lat:.6f}", f"{lon:.6f}"])
        os.replace(tmp_path, CSV_PATH)  # atomic on POSIX and Windows
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/save-geofence", methods=["POST"])
def save_geofence():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON body received"}), 400

    board = data.get("board")
    points = data.get("points")  # expected: [[lat, lon], [lat, lon], ...]

    if board not in ("outer", "inner"):
        return jsonify({"error": "board must be 'outer' or 'inner'"}), 400
    if not isinstance(points, list) or len(points) < 3:
        return jsonify({"error": "Need at least 3 points to save a polygon"}), 400

    parsed_points = []
    for i, pt in enumerate(points, start=1):
        try:
            lat, lon = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            return jsonify({"error": f"Bad point at index {i}: {pt}"}), 400
        parsed_points.append((lat, lon))

    # Keep the OTHER board's points untouched; replace only this board's.
    boards = read_existing_boards()
    boards[board] = parsed_points
    write_boards(boards)

    return jsonify({
        "status": "ok",
        "board": board,
        "points_saved": len(parsed_points),
        "csv_path": CSV_PATH,
    })


if __name__ == "__main__":
    # localhost only — same computer that's wired to the Pico.
    # Switch to host="0.0.0.0" if you need to draw from a different device
    # on the same network (see note above).
    app.run(host="127.0.0.1", port=5000, debug=True)
