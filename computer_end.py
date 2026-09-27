"""
EPICS EVEI Geofence — Computer-End Script
--------------------------------------------
This is your original script, restructured so it keeps running after the
first send instead of stopping once coordinates go out. It now does three
things at once, in separate threads:

  1. Handshake with the Pico once at startup (START -> "listening..." ->
     send initial coordinates), same as before.
  2. Continuously read the Pico's sensor/GPS stream and log it to
     datalog<timestamp>.txt, same as before.
  3. NEW: watch coordinates.csv for changes. Whenever server.py (the
     website's local server) writes an updated polygon to that file, this
     script automatically re-sends the new coordinate string to the Pico
     over the SAME open serial connection -- no restart, no manual re-run.

IMPORTANT ASSUMPTION -- please verify against your Pico firmware:
Step 3 sends the coordinate string again WITHOUT re-doing the "START" /
"listening..." handshake, since the connection is already open and the Pico
is already in its main loop. This assumes your Pico code can accept a fresh
coordinate string at any time (e.g. it checks for incoming UART data on
every loop iteration, not just once at boot). If your current Pico firmware
only reads coordinates once right after "listening...", you'll need to add
a small check on the Pico side so it re-parses new incoming data whenever it
arrives. If that's not something you want to change right now, the watcher
thread below can be adjusted to redo the full START handshake per update
instead -- just say so and I'll change it.
"""

import time
import os
import threading
from datetime import date
import serial
import csv

coordinateFilename = "coordinates"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, f"{coordinateFilename}.csv")

datetime_str = str(date.today()) + '_' + time.strftime("%H-%M-%S", time.localtime())

_last_sent_mtime = None  # tracks the coordinates.csv mtime we last sent to the Pico


def initialize():
    ser = None
    while ser is None:
        try:
            ser = serial.Serial('COM6', 115200, timeout=1)
        except Exception:
            print("Busy Port: Closing Thonny?")
            time.sleep(1)

    # Clear the buffer of old error messages
    ser.reset_input_buffer()

    # Send the START command with a carriage return
    print("Sending START signal...")
    ser.write(b"START\r\n")

    return ser


def wait_for_ready(ser):
    """Blocks until the Pico announces it's ready to receive coordinates."""
    print("Waiting for Pico to wake up...")
    while True:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line:
            print(line)
            if "listening..." in line:
                break


def send_coordinates(cmd, ser):
    """
    Send a coordinate string to the Pico in 64-byte chunks, same framing
    your original serialWrite() used. Used both for the first send and for
    every later auto-update.
    """
    payload = str(cmd) + '\r'
    for i in range(0, len(payload), 64):
        ser.write(payload[i:i + 64].encode())
        time.sleep(0.05)


def listen_loop(ser):
    """
    Runs forever in its own thread: reads whatever the Pico streams back
    (GPS/IMU data, status lines, etc.) and logs every line, same as your
    original serialWrite()'s final while-loop.
    """
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(line)
                with open(f'datalog{datetime_str}.txt', 'a') as f:
                    f.write(f'{line}\n')
        except serial.SerialException:
            print("\nError: The Pico disconnected unexpectedly.")
            break


def get_coordinates():
    """
    Reads coordinates.csv (written automatically by server.py whenever a
    polygon is finished on the website) and flattens it into the single
    comma-separated string the Pico expects: OUTER/INNER labels kept as-is,
    every numeric value replaced with its absolute value as a string.
    """
    try:
        with open(CSV_PATH, 'r') as filename:
            data = list(csv.reader(filename, delimiter=","))
    except FileNotFoundError:
        print(f"Could not find {coordinateFilename}.csv! Check your file path.")
        return ""

    new_data = []
    for row in range(len(data)):
        for col in range(len(data[row])):
            if data[row][col] == "OUTER" or data[row][col] == "INNER":
                new_data.append(data[row][col])
            else:
                new_data.append(str(abs(float(data[row][col]))))

    return ', '.join(new_data)


def watch_csv_loop(ser, poll_interval=1.0):
    """
    Runs forever in its own thread: whenever coordinates.csv's modified time
    changes (the website saved a newly finished polygon), automatically
    re-sends the updated coordinate string to the Pico. See the module
    docstring for the assumption this relies on.
    """
    global _last_sent_mtime
    while True:
        try:
            if os.path.exists(CSV_PATH):
                mtime = os.path.getmtime(CSV_PATH)
                if mtime != _last_sent_mtime:
                    coordinate_data = get_coordinates()
                    if coordinate_data:
                        print("\n[watch] coordinates.csv changed -- sending updated coordinates to Pico...")
                        send_coordinates(coordinate_data, ser)
                        print("[watch] Updated coordinates sent.\n")
                    _last_sent_mtime = mtime
        except Exception as e:
            print(f"[watch] Error checking/sending updated coordinates: {e}")
        time.sleep(poll_interval)


if __name__ == '__main__':
    ser = initialize()
    wait_for_ready(ser)

    coordinate_data = get_coordinates()
    if coordinate_data:
        print("\n--- Pico is ready! Sending initial coordinates ---")
        send_coordinates(coordinate_data, ser)
        print("--- Coordinates sent. Watching for updates + sensor stream ---\n")
        if os.path.exists(CSV_PATH):
            _last_sent_mtime = os.path.getmtime(CSV_PATH)
    else:
        print("No coordinates.csv yet -- will send as soon as a polygon is saved on the website.")

    # Sensor-stream logging and CSV-change watching run continuously
    # in the background; the main thread just stays alive.
    threading.Thread(target=listen_loop, args=(ser,), daemon=True).start()
    threading.Thread(target=watch_csv_loop, args=(ser,), daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")
