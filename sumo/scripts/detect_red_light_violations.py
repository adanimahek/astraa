"""Run the ASTRA intersection in SUMO and detect red-light violations via TraCI.

A configurable fraction of vehicles is made to disregard red lights
(``speedMode`` bit 3 cleared) so that violations occur in the simulation.
Detection itself is done by the shared backend rule
(``backend/app/enforcement/red_light.py``) and does **not** look at which
vehicles were told to violate; that list is only reported for evaluation.

The final stdout line is a JSON object (same convention as the other ASTRA
SUMO scripts) consumed by ``POST /api/violations/detect/sumo``.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import traci

SUMO_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = SUMO_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.enforcement.evidence import EvidenceStore  # noqa: E402
from app.enforcement.red_light import RedLightRule  # noqa: E402
from app.enforcement.sumo import SumoRedLightMonitor, render_schematic  # noqa: E402

CONFIG_FILE = SUMO_DIR / "config" / "intersection.sumocfg"
TRAFFIC_LIGHT_ID = "center"
IGNORE_RED_SPEED_MODE = 7  # safe speed + accel/decel limits, ignore right of way / red


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seed", type=int, default=101)
    p.add_argument("--duration", type=float, default=600.0)
    p.add_argument("--violation-probability", type=float, default=0.05)
    p.add_argument("--grace", type=float, default=0.0)
    p.add_argument("--exempt", default="astra_emergency_type")
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--gui", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not 0 <= args.violation_probability <= 1:
        raise SystemExit("--violation-probability must be between 0 and 1")
    rng = random.Random(args.seed)
    source_id = f"sumo-seed{args.seed}-d{int(args.duration)}-p{args.violation_probability:g}"
    store = EvidenceStore(str(args.evidence_dir))
    binary = "sumo-gui" if args.gui else "sumo"
    traci.start([binary, "-c", str(CONFIG_FILE), "--seed", str(args.seed),
                 "--no-step-log", "true", "--duration-log.disable", "true",
                 "--collision.action", "warn"] + (["--start", "--quit-on-end"] if args.gui else []))
    violators = []
    try:
        if TRAFFIC_LIGHT_ID not in traci.trafficlight.getIDList():
            raise RuntimeError(f"Expected traffic light {TRAFFIC_LIGHT_ID!r}; rebuild the SUMO network.")

        def capture(doc: dict) -> dict:
            folder = store.folder("sumo", source_id, doc["track_id"])
            doc["evidence"] = {
                "scene": store.save_image(folder, "scene.jpg",
                                          render_schematic(traci, TRAFFIC_LIGHT_ID, doc)),
                "scene_zoom": store.save_image(
                    folder, "scene_zoom.jpg",
                    render_schematic(traci, TRAFFIC_LIGHT_ID, doc, zoom_radius=40.0)),
                "vehicle_crops": [],
            }
            return doc

        rule = RedLightRule(grace_seconds=args.grace,
                            exempt_classes=[c for c in args.exempt.split(",") if c])
        monitor = SumoRedLightMonitor(traci, TRAFFIC_LIGHT_ID, rule, on_violation=capture)
        while (traci.simulation.getTime() < args.duration
               and traci.simulation.getMinExpectedNumber() > 0):
            traci.simulationStep()
            for vid in traci.simulation.getDepartedIDList():
                if rng.random() < args.violation_probability:
                    traci.vehicle.setSpeedMode(vid, IGNORE_RED_SPEED_MODE)
                    violators.append(vid)
            monitor.step()
        end_time = traci.simulation.getTime()
    finally:
        traci.close()

    detected = {e["track_id"] for e in monitor.events}
    print(json.dumps({
        "source_id": source_id,
        "seed": args.seed,
        "simulated_seconds": end_time,
        "violation_probability": args.violation_probability,
        "red_light_ignoring_vehicles": len(violators),
        "detected_vehicles_not_in_ignore_list": sorted(detected - set(violators)),
        "rule_stats": rule.stats,
        "events": monitor.events,
    }))


if __name__ == "__main__":
    main()
