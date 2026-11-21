# ASTRA

ASTRA is a traffic-analysis demo with a React/Vite frontend and a FastAPI backend.
The backend runs YOLO vehicle detection and stores detection history and users in
MongoDB. SUMO/TraCI scenarios and a trained Q-learning signal controller are
available for standalone evaluation. Emergency detections can launch a paired
SUMO priority comparison; the browser intersection remains a separate demo.

## Requirements

- Windows with Python 3.9 or newer
- Node.js and npm
- MongoDB Atlas (or a reachable MongoDB instance)
- The YOLO weights in `backend/models/`
- SUMO with `sumo` and `netconvert` available on `PATH` (for the simulation)

## Configure the backend

In PowerShell:

```powershell
Set-Location D:\Astra\backend
Copy-Item .env.example .env
```

Edit `backend\.env` and set `MONGODB_URI` to a reachable database, `JWT_SECRET`
to a long random value, and a non-default `ADMIN_PASSWORD`. Keep `.env` private.
`MODEL_PATH` and `RESULTS_DIR` are resolved relative to the backend directory,
regardless of the command's working directory. The default model is included in
`backend\models`.

Run the API in one terminal from `D:\Astra\backend`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The backend checks MongoDB and loads the YOLO model during startup. Open
`http://localhost:8000/docs` for the API docs and `http://localhost:8000/api/health`
for the health endpoint.

## Run the frontend

In another terminal:

```powershell
Set-Location D:\Astra\frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend connects to `http://localhost:8000` by
default. To use a different backend URL, create `frontend\.env` with:

```dotenv
VITE_API_URL=http://localhost:8000
```

The **Live Feed** page is separate from the existing upload, dashboard, and SUMO
flows. It connects four RTSP cameras on the backend, runs YOLO on sampled
frames, and uses the per-approach counts as inputs to the saved Q-learning
policy in a SUMO simulation. An ambulance or fire truck detection injects a
simulated emergency vehicle and temporarily overrides the learned policy to
serve that approach. It never connects to or controls physical traffic signals.

The **Manual SUMO** page is also separate from the browser intersection. It lets
you set regular-vehicle counts for each of the two existing lanes on all four
approaches and optionally place one emergency vehicle in selected lanes.
SUMO-GUI uses its assigned vehicle-color scheme: regular vehicles are blue and
emergency vehicles are explicitly set to red through TraCI. The backend runs
matched fixed-time and trained Q-learning-plus-priority SUMO
simulations for that manually configured scenario and returns their metrics.
This page uses the lanes already in `sumo\network\intersection.net.xml`; it
does not rebuild the road network or control physical traffic lights. The
**Show vehicle flow in SUMO-GUI** option is enabled by default and opens SUMO's
graphical window at slowed playback speed for both controller runs. The backend
must run on the same desktop session for the window to be visible. Uncheck the
option to run headlessly.

Configure `LIVE_FEED_URL_NORTH`, `LIVE_FEED_URL_SOUTH`, `LIVE_FEED_URL_EAST`,
and `LIVE_FEED_URL_WEST` in `backend\.env` with the four camera RTSP URLs, then
restart the backend and use **Live Feed & Simulation**. Keep camera credentials
private in the local environment file; do not put them in the frontend or share
them in chat. RTSP access must be available from the backend host, and its
OpenCV build must support FFmpeg/RTSP. No stream URLs are supplied by default.

Each camera’s total vehicle detections in a sampled frame are used as a queue
proxy for the trained policy; this has not been calibrated as a real queue
measurement. Live page metrics describe the SUMO simulation, not physical
traffic. Benchmark comparisons on the Dashboard remain the separate matched
seed evaluation.

## Stage 2: vehicle counting and traffic analysis

Image results classify the number of detected vehicles as Low (0-7), Medium
(8-19), or High (20+). Video results use the peak simultaneous count from the
analysed frames for that volume category and also report the average count per
analysed frame; these are frame counts, not unique vehicle counts across the
whole clip.

To test emergency priority, enable **Emergency intersection simulation** before
uploading. Choose the road
(north/south/east/west) the camera shows. If YOLO detects an ambulance or fire
truck, the authenticated backend verifies the saved detection and runs paired
fixed-time versus emergency-priority SUMO simulations for that approach. The
signal page shows the comparison and the dashboard retains its summary. The
browser intersection also visualizes the selected emergency, but it remains a
separate frontend demo—not a live traffic controller. If neither emergency
class is detected, no SUMO emergency simulation is started. Approach selection
is manual because a video or image alone does not establish cardinal direction
without camera calibration.

This upload-triggered comparison runs a fixed-time baseline against the trained
Q-learning controller with an emergency-priority override. The
**Live Feed & Simulation** page uses the same Q-learning-plus-priority behavior
with camera-derived traffic-count proxies.

For a frontend served from another origin, add that origin to the comma-separated
`CORS_ORIGINS` setting in `backend\.env`, then restart the API.

## Stage 3: run the SUMO intersection

The scenario has a four-way junction, two lanes per approach, a generated
two-phase fixed-time traffic light, passenger-car routes for straight/left/right
movements, and 30 minutes of traffic flows. From the project root in PowerShell,
build the network and start the simulation:

```powershell
.\sumo\scripts\build_network.ps1
sumo -c .\sumo\config\intersection.sumocfg
```

To view it instead of running headlessly, use `sumo-gui` with the same config:

```powershell
sumo-gui -c .\sumo\config\intersection.sumocfg
```

The network source is in `sumo\network\intersection.nod.xml` and
`sumo\network\intersection.edg.xml`; traffic demand is in
`sumo\routes\intersection.rou.xml`, including routes for four emergency
approaches. The scenario runs independently or through the Python TraCI monitor
below.

## Stage 4: connect Python through TraCI

Close any separately running SUMO GUI, then run the TraCI monitor from the
project root. It starts SUMO itself and prints JSON snapshots of vehicle counts,
queued vehicles on each approach, and the traffic-light phase/state:

```powershell
.\.venv\Scripts\python.exe .\sumo\scripts\traci_monitor.py --interval 10
```

Add `--gui` to open SUMO's GUI while the Python monitor is connected. To test
Python signal control, select phase `0` (north/south) or `2` (east/west) and set
its green duration; for example:

```powershell
.\.venv\Scripts\python.exe .\sumo\scripts\traci_monitor.py --phase 2 --green-seconds 45
```

Use `--steps 20` for a short test run. The phase option demonstrates direct
TraCI control; it is not an adaptive policy. For a paired emergency test,
fixed-time is compared with the trained Q-learning controller plus emergency
priority:

```powershell
.\.venv\Scripts\python.exe .\sumo\scripts\simulate_emergency.py --approach north
```

## Stage 5: train a Q-learning signal controller

Close any separately running SUMO GUI, then train the tabular controller from
the project root. Training runs 50 SUMO episodes by default and saves the learned
Q-table and per-episode CSV metrics:

```powershell
.\.venv\Scripts\python.exe .\sumo\scripts\train_q_learning.py
```

The learned values are saved in `sumo\models\q_table.json`; episode rewards,
queue metrics, and arrivals are recorded in
`sumo\results\q_learning_training.csv`. Subsequent runs resume from the saved
table and continue the episode numbering and exploration decay.

For a quick smoke test, use two shortened episodes and separate output files:

```powershell
.\.venv\Scripts\python.exe .\sumo\scripts\train_q_learning.py --episodes 2 --max-sim-time 120 --q-table .\sumo\models\q_table_test.json --metrics .\sumo\results\q_learning_test.csv
```

The state uses north/south and east/west queue buckets plus the active green
phase. Actions hold the current green or switch through its SUMO yellow phase;
minimum and maximum green times are enforced. When one opposing group has more
than two additional queued vehicles, a queue-pressure safeguard favors that
group after the minimum green; the maximum green prevents starvation. The
reward penalizes queued vehicles each simulation second. The saved policy is
used by the live-feed SUMO controller and emergency comparison. Emergency
priority temporarily serves the detected approach, then returns signal
decisions to the saved Q-table.

## Stage 6: compare fixed-time and Q-learning controllers

Run paired SUMO simulations with identical traffic seeds for both controllers.
The benchmark reports completed trips' mean SUMO waiting time and travel time,
time-averaged queue length, throughput, and estimated CO₂ emissions. It writes
per-run data and controller averages to CSV, which the authenticated API and
dashboard display:

```powershell
.\.venv\Scripts\python.exe .\sumo\scripts\compare_controllers.py
```

By default, this uses five matched traffic seeds, the trained
`sumo\models\q_table.json`, and writes
`sumo\results\controller_comparison_runs.csv` and
`sumo\results\controller_comparison.csv`. Use `--replications 1` for a quicker
single-seed run. The Q policy acts greedily (ties hold the current phase), with the same
queue-pressure safeguard and minimum/maximum green limits as training. Compare
averages over multiple seeds; one run is not enough to claim a general
improvement. Results include throughput and SUMO-reported CO₂ emissions; these
emissions are simulation estimates, not measured real-world exhaust.

The seeded administrator account uses `ADMIN_EMAIL` and `ADMIN_PASSWORD` from the
backend environment file. Do not use sample/default credentials outside local
development.

## Detection flow

1. Sign in through the frontend; the backend returns a bearer token.
2. Upload a JPG/PNG image or MP4/AVI/MOV video from **Traffic Input**.
3. The backend runs the configured YOLO weights, saves an annotated result, and
   stores summary history in MongoDB.
4. To simulate the detected regular vehicles, enable **Simulate detected
   regular vehicles in ASTRA adaptive control** and select their approach.
   The detected count is dispatched into both browser intersection demos so
   their fixed-time/adaptive behavior sees the same arrivals. Video simulations
   use the peak-frame count rather than unique tracked vehicles.
5. The frontend displays detections and reads saved runs from **Reports**.

On **AI Signal Control**, browser-generated arrivals are drawn blue and
YOLO-scanned arrivals purple; emergency vehicles flash red/white. Per-controller
source totals are shown separately and reset with the browser simulation.
These are browser-demo vehicles, not vehicles in SUMO. Use **Manual SUMO** to
configure lane-by-lane traffic and run the actual SUMO comparison.

If reports cannot load, the page shows the backend/API error instead of presenting
it as an empty history. Video uploads are capped at 200 MB, image uploads at 10 MB,
and detection confidence must be between 0.1 and 0.9.
