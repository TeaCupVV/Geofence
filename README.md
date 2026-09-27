# EPICS EVEI Geofence — Full Pipeline

No CSV download, no manual file transfer. Draw a polygon on the website →
it's saved straight into `coordinates.csv` on the computer → your Pico
script picks up the change automatically and re-sends it over serial.

## Files

| File | Runs on | Purpose |
|---|---|---|
| `server.py` | Computer | Serves `index.html`, writes `coordinates.csv` when you press "Finish Polygon" |
| `index.html` | Browser | The map — same as before, `fetch()`s points to the server instead of just alerting |
| `coordinates.csv` | Computer | Auto-created/updated by `server.py`, in `OUTER`/`INNER` label format |
| `computer_end.py` | Computer | Your serial handshake + sensor-logging code, now with a background thread that watches `coordinates.csv` and auto-resends updated coordinates to the Pico |

## One-time setup

```
pip install flask pyserial
```

## Running it

1. **Plug the Pico into the computer via USB**, on whatever COM port
   `computer_end.py` is configured for (currently `COM6` — change it in
   `initialize()` if yours differs).

2. **Start the web server:**
   ```
   python server.py
   ```
   Open `http://localhost:5000`, draw the outer and inner boundaries, press
   "Finish Polygon" for each. You'll see a green "✓ saved" message once
   `coordinates.csv` has been written — no download, no copying files.

3. **Start the computer-end script** (separate terminal, can run before or
   after step 2 — it'll pick up whatever's in `coordinates.csv` once it's
   there):
   ```
   python computer_end.py
   ```
   It sends `START`, waits for `listening...`, sends the current
   coordinates, then keeps running: one thread logs the Pico's sensor
   stream to `datalog<timestamp>.txt`, another watches `coordinates.csv`
   and automatically re-sends it to the Pico whenever the website saves an
   updated polygon.

4. **Redraw anytime.** Go back to the website, adjust a polygon, press
   "Finish Polygon" again — within ~1 second `computer_end.py` notices the
   file changed and sends the new coordinates to the Pico, no restart
   needed.

## One important thing to verify on the Pico side

`computer_end.py`'s auto-update re-sends the coordinate string directly
over the already-open serial connection, **without** repeating the `START`
/ `listening...` handshake. That only works if your Pico firmware checks
for new incoming data on every loop iteration (not just once at boot,
right after printing `listening...`). If your current firmware only reads
coordinates that one time, it'll ignore the auto-update sends — in that
case, either add a "check for new data" step to the Pico's main loop, or
tell me and I'll change the watcher to redo the full handshake on every
update instead (slower, but doesn't require touching the Pico code).

## Other notes

- **CSV format**: `coordinates.csv` looks like:
  ```
  OUTER
  40.423700,-86.921200
  40.423800,-86.921300
  40.423650,-86.921100
  INNER
  40.423720,-86.921220
  ...
  ```
  `get_coordinates()` flattens this into one comma-separated string,
  keeping `OUTER`/`INNER` as labels and taking the absolute value of every
  number (so make sure your Pico firmware knows the hemisphere/sign
  convention it's expecting, since the sign is dropped here same as in
  your original script).
- **Same computer only, for now**: `server.py` binds to `localhost`. If you
  ever need to draw boundaries from a phone while the Pico stays wired to a
  separate computer, change `app.run(host=...)` to `"0.0.0.0"` in
  `server.py` and open the page using that computer's LAN IP instead.
