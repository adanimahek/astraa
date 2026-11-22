# ASTRA backend (FastAPI + MongoDB + YOLO11s)

See the repository [README](../README.md) for the complete setup and frontend
connection steps.

Quick start from PowerShell:

```powershell
Set-Location D:\Astra\backend
Copy-Item .env.example .env
# Edit .env with your MongoDB URI and secure JWT/admin credentials.
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API checks the database and loads the YOLO weights on startup. Visit
`http://localhost:8000/docs` for interactive API documentation.

## E-Challan & Penalty Management (FR10–FR15)

Code lives in `app/enforcement/` (detectors, ANPR, registry, challans,
payments) with routers `violations`, `registry`, `challans`, `owner` and
`enforcement_dashboard`. New settings are optional; see the e-challan block in
`.env.example`.

Pipeline: **detect** (video or SUMO) → **ANPR** (or simulated plate for SUMO) →
**manual review** if uncertain → **owner lookup** → **challan** → **notify** →
**pay (simulated)** / **overdue**.

* **Red-light detection**
  * `POST /api/violations/detect/video`: upload a video plus a JSON config
    with the stop line(s) and signal timeline. Time not covered by the config
    is UNKNOWN and is never enforced. `GET /api/violations/config/example`
    returns an example config.
  * `POST /api/violations/detect/sumo`: runs
    `sumo/scripts/detect_red_light_violations.py`. Needs `sumo` on `PATH` and
    `traci`; `pip install eclipse-sumo traci` provides both.
* **ANPR** uses a separate pretrained plate detector
  (`models/anpr/license_plate_yolo11n.pt`, from
  `morsetechlab/yolov11-license-plate-detection`, AGPL-3.0) and EasyOCR. The
  ASTRA vehicle model is unchanged. EasyOCR downloads its weights on first use.
  Uncertain readings appear in `GET /api/violations/review/queue`.
* **Demo data**: run `python scripts/seed_demo_data.py`, or use
  `POST /api/registry/demo/seed` (admin). It creates fictional owners and
  vehicles plus owner logins `owner1..8@example.com` / `owner123`. Remove them
  with `--remove`; only records tagged `demo: true` are deleted.
* **Roles**
  * `Vehicle Owner` users only reach `/api/owner/*` and only see their own
    records.
  * Administrator and Traffic Operator keep all existing access.
* **Payments** are simulated. No gateway is contacted and no card or bank data
  is collected.
* **Overdue**: a background task flags overdue challans every
  `OVERDUE_CHECK_MINUTES`. Admins can also trigger it with
  `POST /api/challans/overdue/run`.

Tests (they use an in-memory mongomock DB, never Atlas):

```bash
pip install pytest mongomock
python -m pytest tests -q
```
