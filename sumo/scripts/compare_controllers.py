import argparse
import csv
import json
import math
import shutil
import statistics
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

import traci


SUMO_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = SUMO_DIR / "config" / "intersection.sumocfg"
DEFAULT_Q_TABLE = SUMO_DIR / "models" / "q_table.json"
DEFAULT_OUTPUT = SUMO_DIR / "results" / "controller_comparison.csv"
APPROACHES = ("north_in", "south_in", "east_in", "west_in")
TRAFFIC_LIGHT_ID = "center"
GREEN_PHASES = (0, 2)
QUEUE_BUCKETS = {"0": "0", "1": "1-3", "2": "4-7", "3": "8+"}
RUN_FIELDS = (
    "controller",
    "seed",
    "arrived_vehicles",
    "unfinished_vehicles",
    "throughput_vehicles_per_minute",
    "average_waiting_time_seconds",
    "average_travel_time_seconds",
    "average_queue_vehicles",
    "queue_vehicle_seconds",
    "co2_emissions_grams",
    "simulation_seconds",
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


def configured_end_time() -> float:
    config = ET.parse(CONFIG_FILE).getroot()
    end = config.find("./time/end")
    if end is None or end.get("value") is None:
        raise ValueError(f"SUMO config has no simulation end time: {CONFIG_FILE}")
    return float(end.get("value"))


def configured_step_length() -> float:
    config = ET.parse(CONFIG_FILE).getroot()
    step_length = config.find("./time/step-length")
    if step_length is None or step_length.get("value") is None:
        raise ValueError(f"SUMO config has no step length: {CONFIG_FILE}")
    return float(step_length.get("value"))


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
    for state, values in q_values.items():
        if (
            not isinstance(state, str)
            or len(state.split(",")) != 3
            or not isinstance(values, list)
            or len(values) != 2
            or not all(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in values
            )
        ):
            raise ValueError(f"Invalid Q values for state {state!r}")
    return q_values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare fixed-time and greedy Q-learning signal controllers "
            "on identical SUMO traffic seeds."
        )
    )
    parser.add_argument("--replications", type=positive_int, default=5)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--interval", type=positive_int, default=5)
    parser.add_argument("--min-green", type=positive_float, default=10)
    parser.add_argument("--max-green", type=positive_float, default=45)
    parser.add_argument("--q-table", type=Path, default=DEFAULT_Q_TABLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.min_green >= args.max_green:
        parser.error("--min-green must be less than --max-green")
    return args


def queue_bucket(count: int) -> int:
    if count == 0:
        return 0
    if count <= 3:
        return 1
    if count <= 7:
        return 2
    return 3


def observe_queues() -> Tuple[int, int]:
    north_south_queue = sum(
        traci.edge.getLastStepHaltingNumber(edge_id)
        for edge_id in ("north_in", "south_in")
    )
    east_west_queue = sum(
        traci.edge.getLastStepHaltingNumber(edge_id)
        for edge_id in ("east_in", "west_in")
    )
    return north_south_queue, east_west_queue


def observe_state(queues: Optional[Tuple[int, int]] = None) -> tuple:
    north_south_queue, east_west_queue = queues or observe_queues()
    phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
    if phase not in GREEN_PHASES:
        raise RuntimeError(f"Cannot observe a decision state during phase {phase}")
    return (
        queue_bucket(north_south_queue),
        queue_bucket(east_west_queue),
        GREEN_PHASES.index(phase),
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


def run_scenario(
    binary: str,
    controller: str,
    seed: int,
    args: argparse.Namespace,
    q_values: dict,
    tripinfo_path: Path,
    end_time: float,
    step_length: float,
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
                "rebuild the SUMO network before comparing controllers."
            )

        if controller == "q_learning":
            current_phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
            if current_phase not in GREEN_PHASES:
                raise RuntimeError(
                    f"Expected initial green phase {GREEN_PHASES}; got {current_phase}"
                )
            current_green_phase = current_phase
            green_started_at = traci.simulation.getTime()
            next_decision = traci.simulation.getTime()
        else:
            current_green_phase = None
            green_started_at = 0.0
            next_decision = 0.0

        queue_total = 0
        co2_emissions_mg = 0.0
        steps = 0
        while traci.simulation.getTime() < end_time:
            simulation_time = traci.simulation.getTime()
            if controller == "q_learning":
                phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
                if phase in GREEN_PHASES:
                    if phase != current_green_phase:
                        current_green_phase = phase
                        green_started_at = simulation_time

                    if simulation_time >= next_decision:
                        queues = observe_queues()
                        state = observe_state(queues)
                        action = choose_greedy_action(q_values, state)
                        green_elapsed = simulation_time - green_started_at
                        action = apply_queue_pressure(
                            action,
                            GREEN_PHASES.index(phase),
                            queues[0],
                            queues[1],
                            green_elapsed,
                            args.min_green,
                            args.max_green,
                        )

                        if action == 1:
                            traci.trafficlight.setPhase(
                                TRAFFIC_LIGHT_ID, phase + 1
                            )
                        else:
                            traci.trafficlight.setPhaseDuration(
                                TRAFFIC_LIGHT_ID, args.interval
                            )
                        next_decision = simulation_time + args.interval

            traci.simulationStep()
            steps += 1
            queue_total += sum(
                traci.edge.getLastStepHaltingNumber(edge_id)
                for edge_id in APPROACHES
            )
            co2_emissions_mg += sum(
                traci.lane.getCO2Emission(lane_id)
                for lane_id in traci.lane.getIDList()
            ) * step_length

        simulation_seconds = traci.simulation.getTime()
        if simulation_seconds < end_time:
            raise RuntimeError(
                f"{controller} simulation stopped early at {simulation_seconds}s"
            )
    finally:
        traci.close()

    tripinfo = ET.parse(tripinfo_path).getroot()
    trips = tripinfo.findall("tripinfo")
    waiting_times = [
        float(trip.get("waitingTime", "0")) for trip in trips
    ]
    travel_times = [float(trip.get("duration", "0")) for trip in trips]
    return {
        "controller": controller,
        "seed": seed,
        "arrived_vehicles": len(trips),
        "unfinished_vehicles": len(
            tripinfo.findall("tripinfo[@vaporized='true']")
        ),
        "throughput_vehicles_per_minute": (
            len(trips) / (simulation_seconds / 60)
            if simulation_seconds
            else 0.0
        ),
        "average_waiting_time_seconds": (
            statistics.fmean(waiting_times) if waiting_times else 0.0
        ),
        "average_travel_time_seconds": (
            statistics.fmean(travel_times) if travel_times else 0.0
        ),
        "average_queue_vehicles": queue_total / max(1, steps),
        "queue_vehicle_seconds": queue_total,
        "co2_emissions_grams": co2_emissions_mg / 1000,
        "simulation_seconds": simulation_seconds,
    }


def summarize(results: list) -> list:
    summary = []
    for controller in ("fixed_time", "q_learning"):
        runs = [row for row in results if row["controller"] == controller]
        summary_row = {"controller": controller, "replications": len(runs)}
        for field in (
            "arrived_vehicles",
            "throughput_vehicles_per_minute",
            "average_waiting_time_seconds",
            "average_travel_time_seconds",
            "average_queue_vehicles",
            "queue_vehicle_seconds",
            "co2_emissions_grams",
        ):
            summary_row[field] = statistics.fmean(
                float(row[field]) for row in runs
            )
        summary.append(summary_row)
    return summary


def write_csv(path: Path, rows: list, fields: tuple) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(
            f"SUMO config not found at {CONFIG_FILE}. "
            "Build the network with sumo\\scripts\\build_network.ps1 first."
        )
    if not args.q_table.is_file():
        raise FileNotFoundError(f"Q-learning table not found: {args.q_table}")
    binary = shutil.which("sumo")
    if binary is None:
        raise RuntimeError(
            "Could not find 'sumo' on PATH. Add the SUMO bin directory to PATH."
        )

    q_values = load_policy(args.q_table)
    end_time = configured_end_time()
    step_length = configured_step_length()
    results = []
    with tempfile.TemporaryDirectory(prefix="astra-sumo-compare-") as temp_dir:
        for replication in range(args.replications):
            seed = args.seed + replication
            for controller in ("fixed_time", "q_learning"):
                tripinfo_path = Path(temp_dir) / f"{controller}-{seed}.xml"
                result = run_scenario(
                    binary,
                    controller,
                    seed,
                    args,
                    q_values,
                    tripinfo_path,
                    end_time,
                    step_length,
                )
                results.append(result)
                print(json.dumps(result), flush=True)
            fixed_run, q_learning_run = results[-2:]
            if (
                fixed_run["arrived_vehicles"]
                != q_learning_run["arrived_vehicles"]
                or fixed_run["unfinished_vehicles"]
                or q_learning_run["unfinished_vehicles"]
            ):
                raise RuntimeError(
                    f"Seed {seed} did not complete the same traffic demand: "
                    f"fixed={fixed_run['arrived_vehicles']} arrived/"
                    f"{fixed_run['unfinished_vehicles']} unfinished, "
                    f"Q-learning={q_learning_run['arrived_vehicles']} arrived/"
                    f"{q_learning_run['unfinished_vehicles']} unfinished."
                )

    summary = summarize(results)
    run_path = args.output.with_name(f"{args.output.stem}_runs.csv")
    write_csv(run_path, results, RUN_FIELDS)
    summary_fields = (
        "controller",
        "replications",
        "arrived_vehicles",
        "throughput_vehicles_per_minute",
        "average_waiting_time_seconds",
        "average_travel_time_seconds",
        "average_queue_vehicles",
        "queue_vehicle_seconds",
        "co2_emissions_grams",
    )
    write_csv(args.output, summary, summary_fields)
    print(f"Saved per-run results: {run_path}")
    print(f"Saved controller summary: {args.output}")
    for metric in (
        "average_waiting_time_seconds",
        "average_travel_time_seconds",
        "average_queue_vehicles",
        "co2_emissions_grams",
    ):
        fixed, learned = (
            float(summary_row[metric])
            for summary_row in summary
        )
        improvement = (fixed - learned) / fixed * 100 if fixed else 0.0
        print(
            f"{metric}: fixed={fixed:.3f}, q_learning={learned:.3f}, "
            f"reduction={improvement:.2f}%"
        )


if __name__ == "__main__":
    main()
