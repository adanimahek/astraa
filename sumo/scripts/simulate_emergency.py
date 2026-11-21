import argparse
import json
import math
import shutil
import statistics
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Tuple

import traci


SUMO_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = SUMO_DIR / "config" / "intersection.sumocfg"
DEFAULT_Q_TABLE = SUMO_DIR / "models" / "q_table.json"
TRAFFIC_LIGHT_ID = "center"
EMERGENCY_VEHICLE_ID = "astra_emergency"
QUEUE_BUCKETS = {"0": "0", "1": "1-3", "2": "4-7", "3": "8+"}
EMERGENCY_ROUTE_IDS = {
    "north": "emergency_north",
    "south": "emergency_south",
    "east": "emergency_east",
    "west": "emergency_west",
}
APPROACH_EDGES = ("north_in", "south_in", "east_in", "west_in")
GREEN_PHASES = (0, 2)


def load_policy(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("format_version") != 1
        or payload.get("algorithm") != "tabular_q_learning"
        or payload.get("actions") != ["hold", "switch"]
        or payload.get("queue_buckets") != QUEUE_BUCKETS
    ):
        raise ValueError(f"Incompatible Q-learning policy: {path}")
    q_values = payload.get("q_values")
    if not isinstance(q_values, dict) or not q_values:
        raise ValueError(f"Q-learning policy has no states: {path}")
    return q_values


def queue_bucket(count: int) -> int:
    if count == 0:
        return 0
    if count <= 3:
        return 1
    if count <= 7:
        return 2
    return 3


def observe_state() -> tuple:
    north_south_queue, east_west_queue = observe_queues()
    phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
    if phase not in GREEN_PHASES:
        raise RuntimeError(f"Cannot observe a decision state during phase {phase}")
    return (
        queue_bucket(north_south_queue),
        queue_bucket(east_west_queue),
        GREEN_PHASES.index(phase),
    )


def observe_queues() -> Tuple[int, int]:
    return (
        traci.edge.getLastStepHaltingNumber("north_in")
        + traci.edge.getLastStepHaltingNumber("south_in"),
        traci.edge.getLastStepHaltingNumber("east_in")
        + traci.edge.getLastStepHaltingNumber("west_in"),
    )


def apply_queue_pressure(
    action: int,
    current_phase: int,
    north_south_queue: int,
    east_west_queue: int,
    green_elapsed: float,
    min_green: float,
    max_green: float,
) -> int:
    preferred_phase = None
    if north_south_queue > east_west_queue + 2:
        preferred_phase = 0
    elif east_west_queue > north_south_queue + 2:
        preferred_phase = 1

    if green_elapsed >= max_green:
        return 1
    if green_elapsed < min_green:
        return 0
    if preferred_phase is not None:
        return int(preferred_phase != current_phase)
    return action


def choose_greedy_action(q_values: dict, state: tuple) -> int:
    values = q_values.get(",".join(str(value) for value in state), [0.0, 0.0])
    return 1 if values[1] > values[0] else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare fixed-time against Q-learning with an emergency-priority "
            "override in SUMO using the same traffic seed."
        )
    )
    parser.add_argument(
        "--approach", choices=tuple(EMERGENCY_ROUTE_IDS), required=True
    )
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--inject-time", type=float, default=300.0)
    parser.add_argument("--priority-green", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--min-green", type=float, default=10.0)
    parser.add_argument("--max-green", type=float, default=45.0)
    parser.add_argument("--q-table", type=Path, default=DEFAULT_Q_TABLE)
    return parser.parse_args()


def configured_time(path: Path, element_path: str) -> float:
    config = ET.parse(path).getroot()
    element = config.find(element_path)
    if element is None or element.get("value") is None:
        raise ValueError(f"SUMO config has no {element_path}: {path}")
    value = float(element.get("value"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Invalid {element_path} in {path}")
    return value


def run_trial(
    binary: str,
    approach: str,
    seed: int,
    q_learning_priority: bool,
    q_values: dict,
    inject_time: float,
    priority_green: float,
    interval: float,
    min_green: float,
    max_green: float,
    end_time: float,
    step_length: float,
    tripinfo_path: Path,
) -> dict:
    traci.start(
        [
            binary,
            "-c",
            str(CONFIG_FILE),
            "--seed",
            str(seed),
            "--tripinfo-output",
            str(tripinfo_path),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
        ]
    )
    try:
        if TRAFFIC_LIGHT_ID not in traci.trafficlight.getIDList():
            raise RuntimeError(
                f"Expected traffic light {TRAFFIC_LIGHT_ID!r}; "
                "rebuild the SUMO network."
            )
        if EMERGENCY_ROUTE_IDS[approach] not in traci.route.getIDList():
            raise RuntimeError(
                f"Expected emergency route {EMERGENCY_ROUTE_IDS[approach]!r}; "
                "check the SUMO route file."
            )
        if "astra_emergency_type" not in traci.vehicletype.getIDList():
            raise RuntimeError(
                "Emergency vehicle type is missing from the SUMO route file."
            )

        target_phase = 0 if approach in ("north", "south") else 2
        destination_edge = {
            "north": "south_out",
            "south": "north_out",
            "east": "west_out",
            "west": "east_out",
        }[approach]
        injection_requested = False
        emergency_seen = False
        priority_was_active = False
        priority_activation_time = None
        emergency_arrival_time = None
        queue_total = 0
        co2_emissions_mg = 0.0
        steps = 0
        current_green_phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
        if current_green_phase not in GREEN_PHASES:
            raise RuntimeError(
                f"Expected initial green phase {GREEN_PHASES}; got {current_green_phase}"
            )
        green_started_at = traci.simulation.getTime()
        next_decision = traci.simulation.getTime()

        while traci.simulation.getTime() < end_time:
            simulation_time = traci.simulation.getTime()
            if not injection_requested and simulation_time >= inject_time:
                traci.vehicle.add(
                    vehID=EMERGENCY_VEHICLE_ID,
                    routeID=EMERGENCY_ROUTE_IDS[approach],
                    typeID="astra_emergency_type",
                    depart="now",
                    departLane="best",
                    departPos="base",
                    departSpeed="max",
                )
                traci.vehicle.setColor(
                    EMERGENCY_VEHICLE_ID, (255, 40, 40, 255)
                )
                injection_requested = True

            vehicle_ids = traci.vehicle.getIDList()
            emergency_in_network = EMERGENCY_VEHICLE_ID in vehicle_ids
            if emergency_in_network:
                emergency_seen = True

            emergency_on_approach = (
                emergency_in_network
                and traci.vehicle.getRoadID(EMERGENCY_VEHICLE_ID)
                != destination_edge
            )
            simulation_time = traci.simulation.getTime()
            phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
            if phase in GREEN_PHASES and phase != current_green_phase:
                current_green_phase = phase
                green_started_at = simulation_time

            if q_learning_priority and emergency_on_approach:
                if phase in GREEN_PHASES:
                    if phase != target_phase:
                        traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, phase + 1)
                    else:
                        remaining = max(
                            0.0,
                            traci.trafficlight.getNextSwitch(TRAFFIC_LIGHT_ID)
                            - simulation_time,
                        )
                        traci.trafficlight.setPhaseDuration(
                            TRAFFIC_LIGHT_ID,
                            max(remaining, priority_green),
                        )
                        if priority_activation_time is None:
                            priority_activation_time = simulation_time
                priority_was_active = True
            elif q_learning_priority:
                if priority_was_active:
                    next_decision = simulation_time
                    priority_was_active = False
                if phase in GREEN_PHASES and simulation_time >= next_decision:
                    queues = observe_queues()
                    state = observe_state()
                    action = choose_greedy_action(q_values, state)
                    green_elapsed = simulation_time - green_started_at
                    action = apply_queue_pressure(
                        action,
                        GREEN_PHASES.index(phase),
                        queues[0],
                        queues[1],
                        green_elapsed,
                        min_green,
                        max_green,
                    )
                    if action == 1:
                        traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, phase + 1)
                    else:
                        traci.trafficlight.setPhaseDuration(
                            TRAFFIC_LIGHT_ID, interval
                        )
                    next_decision = simulation_time + interval

            traci.simulationStep()
            steps += 1
            queue_total += sum(
                traci.edge.getLastStepHaltingNumber(edge_id)
                for edge_id in APPROACH_EDGES
            )
            co2_emissions_mg += sum(
                traci.lane.getCO2Emission(lane_id)
                for lane_id in traci.lane.getIDList()
            ) * step_length
            if EMERGENCY_VEHICLE_ID in traci.simulation.getArrivedIDList():
                emergency_arrival_time = traci.simulation.getTime()

        if not emergency_seen or emergency_arrival_time is None:
            raise RuntimeError(
                f"Emergency vehicle from {approach} did not complete its trip "
                f"by simulation time {end_time:g}s."
            )
    finally:
        traci.close()

    tripinfo = ET.parse(tripinfo_path).getroot()
    trips = tripinfo.findall("tripinfo")
    emergency_trip = next(
        (
            trip
            for trip in trips
            if trip.get("id") == EMERGENCY_VEHICLE_ID
        ),
        None,
    )
    if emergency_trip is None:
        raise RuntimeError("SUMO did not write the emergency vehicle trip record.")
    waiting_times = [
        float(trip.get("waitingTime", "0")) for trip in trips
    ]
    travel_times = [float(trip.get("duration", "0")) for trip in trips]
    return {
        "controller": (
            "q_learning_with_emergency_priority"
            if q_learning_priority
            else "fixed_time"
        ),
        "approach": approach,
        "seed": seed,
        "arrived_vehicles": len(trips),
        "emergency_waiting_time_seconds": float(
            emergency_trip.get("waitingTime", "0")
        ),
        "emergency_travel_time_seconds": float(
            emergency_trip.get("duration", "0")
        ),
        "priority_activated_at_seconds": priority_activation_time,
        "average_waiting_time_seconds": (
            statistics.fmean(waiting_times) if waiting_times else 0.0
        ),
        "average_travel_time_seconds": (
            statistics.fmean(travel_times) if travel_times else 0.0
        ),
        "average_queue_vehicles": queue_total / max(1, steps),
        "queue_vehicle_seconds": queue_total,
        "throughput_vehicles_per_minute": len(trips) / (end_time / 60),
        "co2_emissions_grams": co2_emissions_mg / 1000,
        "simulation_seconds": end_time,
    }


def main() -> None:
    args = parse_args()
    if not math.isfinite(args.inject_time) or args.inject_time < 0:
        raise ValueError("--inject-time must be a non-negative number")
    if not math.isfinite(args.priority_green) or args.priority_green <= 0:
        raise ValueError("--priority-green must be a positive number")
    if not math.isfinite(args.interval) or args.interval <= 0:
        raise ValueError("--interval must be a positive number")
    if not math.isfinite(args.min_green) or not math.isfinite(args.max_green):
        raise ValueError("Green durations must be finite numbers")
    if args.min_green <= 0 or args.max_green <= args.min_green:
        raise ValueError("--max-green must be greater than positive --min-green")
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(f"SUMO config not found: {CONFIG_FILE}")
    if not args.q_table.is_file():
        raise FileNotFoundError(f"Q-learning table not found: {args.q_table}")
    binary = shutil.which("sumo")
    if binary is None:
        raise RuntimeError(
            "Could not find 'sumo' on PATH. Add the SUMO bin directory to PATH."
        )

    end_time = configured_time(CONFIG_FILE, "./time/end")
    step_length = configured_time(CONFIG_FILE, "./time/step-length")
    if args.inject_time >= end_time:
        raise ValueError("--inject-time must be earlier than the simulation end")
    q_values = load_policy(args.q_table)

    results = []
    with tempfile.TemporaryDirectory(prefix="astra-emergency-") as temp_dir:
        temp_path = Path(temp_dir)
        for q_learning_priority, label in (
            (False, "fixed_time"),
            (True, "q_learning_with_emergency_priority"),
        ):
            result = run_trial(
                binary=binary,
                approach=args.approach,
                seed=args.seed,
                q_learning_priority=q_learning_priority,
                q_values=q_values,
                inject_time=args.inject_time,
                priority_green=args.priority_green,
                interval=args.interval,
                min_green=args.min_green,
                max_green=args.max_green,
                end_time=end_time,
                step_length=step_length,
                tripinfo_path=temp_path / f"{label}.xml",
            )
            results.append(result)
            print(json.dumps(result), flush=True)

    fixed, q_learning_priority = results
    if fixed["arrived_vehicles"] != q_learning_priority["arrived_vehicles"]:
        raise RuntimeError(
            "The fixed-time and Q-learning priority trials completed different "
            "trip counts."
        )
    print(
        json.dumps(
            {
                "approach": args.approach,
                "comparison": "fixed_time_vs_q_learning_with_emergency_priority",
                "q_table": (
                    str(args.q_table.relative_to(SUMO_DIR.parent))
                    if args.q_table.is_relative_to(SUMO_DIR.parent)
                    else args.q_table.name
                ),
                "fixed_time_emergency_wait_seconds": fixed[
                    "emergency_waiting_time_seconds"
                ],
                "q_learning_priority_emergency_wait_seconds": q_learning_priority[
                    "emergency_waiting_time_seconds"
                ],
                "fixed_time_emergency_travel_seconds": fixed[
                    "emergency_travel_time_seconds"
                ],
                "q_learning_priority_emergency_travel_seconds": q_learning_priority[
                    "emergency_travel_time_seconds"
                ],
                "emergency_wait_reduction_percent": (
                    (fixed["emergency_waiting_time_seconds"]
                     - q_learning_priority["emergency_waiting_time_seconds"])
                    / fixed["emergency_waiting_time_seconds"] * 100
                    if fixed["emergency_waiting_time_seconds"]
                    else 0.0
                ),
                "q_learning_priority_activated_at_seconds": q_learning_priority[
                    "priority_activated_at_seconds"
                ],
                "fixed_time_co2_grams": fixed["co2_emissions_grams"],
                "q_learning_priority_co2_grams": q_learning_priority[
                    "co2_emissions_grams"
                ],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
