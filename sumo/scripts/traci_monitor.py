import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import traci


SUMO_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = SUMO_DIR / "config" / "intersection.sumocfg"
APPROACHES = {
    "north": "north_in",
    "south": "south_in",
    "east": "east_in",
    "west": "west_in",
}
TRAFFIC_LIGHT_ID = "center"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


def configured_end_time() -> float:
    config = ET.parse(CONFIG_FILE).getroot()
    end = config.find("./time/end")
    if end is None or end.get("value") is None:
        raise ValueError(f"SUMO config has no simulation end time: {CONFIG_FILE}")
    return float(end.get("value"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor the ASTRA SUMO intersection through TraCI."
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="launch sumo-gui instead of the headless SUMO simulator",
    )
    parser.add_argument(
        "--interval",
        type=positive_int,
        default=10,
        help="report traffic conditions every N simulation seconds (default: 10)",
    )
    parser.add_argument(
        "--steps",
        type=positive_int,
        help="stop after this many simulation steps (useful for a short test run)",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=(0, 2),
        help="set the signal to phase 0 (north/south) or phase 2 (east/west)",
    )
    parser.add_argument(
        "--green-seconds",
        type=positive_float,
        default=30,
        help="duration for the selected phase in seconds (default: 30)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    binary_name = "sumo-gui" if args.gui else "sumo"
    binary = shutil.which(binary_name)
    if binary is None:
        raise RuntimeError(
            f"Could not find {binary_name!r} on PATH. Add the SUMO bin directory "
            "to PATH and try again."
        )
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(
            f"SUMO config not found at {CONFIG_FILE}. "
            "Build the network with sumo\\scripts\\build_network.ps1 first."
        )
    end_time = configured_end_time()

    traci.start(
        [
            binary,
            "-c",
            str(CONFIG_FILE),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
        ]
    )
    try:
        traffic_lights = traci.trafficlight.getIDList()
        if TRAFFIC_LIGHT_ID not in traffic_lights:
            raise RuntimeError(
                f"Expected traffic light {TRAFFIC_LIGHT_ID!r}; "
                f"found {traffic_lights!r}. Rebuild the SUMO network."
            )

        if args.phase is not None:
            traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, args.phase)
            traci.trafficlight.setPhaseDuration(
                TRAFFIC_LIGHT_ID, args.green_seconds
            )
            print(
                f"Set signal {TRAFFIC_LIGHT_ID} to phase {args.phase} "
                f"for {args.green_seconds:g} seconds."
            )

        step_count = 0
        next_report = 0.0
        last_report_time = None
        while (
            traci.simulation.getMinExpectedNumber() > 0
            or traci.simulation.getTime() < end_time
        ):
            if args.steps is not None and step_count >= args.steps:
                break

            traci.simulationStep()
            step_count += 1
            simulation_time = traci.simulation.getTime()
            if simulation_time < next_report:
                continue

            print(json.dumps(snapshot(simulation_time)), flush=True)
            last_report_time = simulation_time
            next_report = simulation_time + args.interval

        final_time = traci.simulation.getTime()
        if final_time != last_report_time:
            print(json.dumps(snapshot(final_time)), flush=True)
    finally:
        traci.close()


def snapshot(simulation_time: float) -> dict:
    approaches = {
        name: {
            "vehicles": traci.edge.getLastStepVehicleNumber(edge_id),
            "queued": traci.edge.getLastStepHaltingNumber(edge_id),
        }
        for name, edge_id in APPROACHES.items()
    }
    return {
        "time": simulation_time,
        "active_vehicles": traci.vehicle.getIDCount(),
        "traffic_light": {
            "id": TRAFFIC_LIGHT_ID,
            "phase": traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID),
            "state": traci.trafficlight.getRedYellowGreenState(TRAFFIC_LIGHT_ID),
            "next_switch": traci.trafficlight.getNextSwitch(TRAFFIC_LIGHT_ID),
        },
        "approaches": approaches,
    }


if __name__ == "__main__":
    main()
