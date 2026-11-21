import argparse
import csv
import json
import math
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import traci


SUMO_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = SUMO_DIR / "config" / "intersection.sumocfg"
DEFAULT_Q_TABLE = SUMO_DIR / "models" / "q_table.json"
DEFAULT_METRICS = SUMO_DIR / "results" / "q_learning_training.csv"
APPROACHES = {
    "north": "north_in",
    "south": "south_in",
    "east": "east_in",
    "west": "west_in",
}
TRAFFIC_LIGHT_ID = "center"
GREEN_PHASES = (0, 2)
ACTIONS = ("hold", "switch")
METRIC_FIELDS = (
    "episode",
    "epsilon",
    "return",
    "average_queue",
    "queue_vehicle_seconds",
    "arrived_vehicles",
    "simulation_seconds",
    "hold_actions",
    "switch_actions",
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


def probability(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def configured_end_time() -> float:
    config = ET.parse(CONFIG_FILE).getroot()
    end = config.find("./time/end")
    if end is None or end.get("value") is None:
        raise ValueError(f"SUMO config has no simulation end time: {CONFIG_FILE}")
    return float(end.get("value"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a tabular Q-learning signal controller in SUMO."
    )
    parser.add_argument("--episodes", type=positive_int, default=50)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--interval", type=positive_int, default=5)
    parser.add_argument("--min-green", type=positive_float, default=10)
    parser.add_argument("--max-green", type=positive_float, default=45)
    parser.add_argument("--alpha", type=probability, default=0.15)
    parser.add_argument("--gamma", type=probability, default=0.95)
    parser.add_argument("--epsilon-start", type=probability, default=1.0)
    parser.add_argument("--epsilon-min", type=probability, default=0.05)
    parser.add_argument("--epsilon-decay", type=probability, default=0.97)
    parser.add_argument(
        "--max-sim-time",
        type=positive_float,
        help="optional episode cutoff in simulation seconds; defaults to SUMO config end",
    )
    parser.add_argument("--q-table", type=Path, default=DEFAULT_Q_TABLE)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    args = parser.parse_args()
    if args.min_green >= args.max_green:
        parser.error("--min-green must be less than --max-green")
    if args.epsilon_min > args.epsilon_start:
        parser.error("--epsilon-min must not exceed --epsilon-start")
    return args


def queue_bucket(count: int) -> int:
    if count == 0:
        return 0
    if count <= 3:
        return 1
    if count <= 7:
        return 2
    return 3


def observe_queues() -> dict:
    return {
        name: traci.edge.getLastStepHaltingNumber(edge_id)
        for name, edge_id in APPROACHES.items()
    }


def observe_state(queues: Optional[dict] = None) -> tuple:
    queues = queues or observe_queues()
    phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
    if phase not in GREEN_PHASES:
        raise RuntimeError(f"Cannot observe a decision state during phase {phase}")
    north_south_queue = queues["north"] + queues["south"]
    east_west_queue = queues["east"] + queues["west"]
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


def state_key(state: tuple) -> str:
    return ",".join(str(value) for value in state)


def choose_action(
    q_table: dict, state: tuple, epsilon: float, rng: random.Random
) -> int:
    if rng.random() < epsilon:
        return rng.randrange(len(ACTIONS))
    values = q_table.get(state_key(state), [0.0] * len(ACTIONS))
    best_value = max(values)
    best_actions = [i for i, value in enumerate(values) if value == best_value]
    return rng.choice(best_actions)


def save_q_table(path: Path, q_table: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": 1,
        "algorithm": "tabular_q_learning",
        "state": "north_south_queue_bucket,east_west_queue_bucket,green_phase_index",
        "queue_buckets": {"0": "0", "1": "1-3", "2": "4-7", "3": "8+"},
        "actions": list(ACTIONS),
        "q_values": q_table,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_q_table(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format_version") != 1 or payload.get("actions") != list(ACTIONS):
        raise ValueError(f"Incompatible Q-table format: {path}")
    q_table = payload.get("q_values")
    if not isinstance(q_table, dict):
        raise ValueError(f"Q-table has no valid q_values mapping: {path}")
    for key, values in q_table.items():
        if (
            not isinstance(key, str)
            or len(key.split(",")) != 3
            or not isinstance(values, list)
            or len(values) != len(ACTIONS)
            or not all(isinstance(value, (int, float)) for value in values)
        ):
            raise ValueError(f"Invalid Q-table entry for state {key!r}")
    return q_table


def run_episode(
    binary: str,
    episode: int,
    epsilon: float,
    args: argparse.Namespace,
    q_table: dict,
    rng: random.Random,
    end_time: float,
) -> dict:
    traci.start(
        [
            binary,
            "-c",
            str(CONFIG_FILE),
            "--seed",
            str(args.seed + episode),
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
                "rebuild the SUMO network before training."
            )

        pending_state = None
        pending_action = None
        pending_reward = 0.0
        next_decision = 0.0
        current_green_phase = None
        green_started_at = 0.0
        total_queue = 0
        queue_vehicle_seconds = 0
        arrived_vehicles = 0
        hold_actions = 0
        switch_actions = 0
        steps = 0

        while traci.simulation.getTime() < end_time:
            simulation_time = traci.simulation.getTime()
            phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)

            if phase in GREEN_PHASES:
                if phase != current_green_phase:
                    current_green_phase = phase
                    green_started_at = simulation_time

                if simulation_time >= next_decision:
                    queues = observe_queues()
                    state = observe_state(queues)
                    if pending_state is not None:
                        values = q_table.setdefault(
                            state_key(pending_state), [0.0, 0.0]
                        )
                        next_values = q_table.get(
                            state_key(state), [0.0, 0.0]
                        )
                        values[pending_action] += args.alpha * (
                            pending_reward
                            + args.gamma * max(next_values)
                            - values[pending_action]
                        )

                    selected_action = choose_action(q_table, state, epsilon, rng)
                    green_elapsed = simulation_time - green_started_at
                    selected_action = apply_queue_pressure(
                        selected_action,
                        GREEN_PHASES.index(phase),
                        queues["north"] + queues["south"],
                        queues["east"] + queues["west"],
                        green_elapsed,
                        args.min_green,
                        args.max_green,
                    )

                    if selected_action == 1:
                        traci.trafficlight.setPhase(
                            TRAFFIC_LIGHT_ID, phase + 1
                        )
                        switch_actions += 1
                        next_decision = simulation_time + args.interval
                    else:
                        traci.trafficlight.setPhaseDuration(
                            TRAFFIC_LIGHT_ID, args.interval
                        )
                        hold_actions += 1
                        next_decision = simulation_time + args.interval

                    pending_state = state
                    pending_action = selected_action
                    pending_reward = 0.0

            traci.simulationStep()
            steps += 1
            queue = sum(
                traci.edge.getLastStepHaltingNumber(edge_id)
                for edge_id in APPROACHES.values()
            )
            total_queue += queue
            queue_vehicle_seconds += queue
            arrived_vehicles += traci.simulation.getArrivedNumber()
            if pending_state is not None:
                pending_reward -= queue

        if pending_state is not None:
            values = q_table.setdefault(state_key(pending_state), [0.0, 0.0])
            values[pending_action] += args.alpha * (
                pending_reward - values[pending_action]
            )

        elapsed = traci.simulation.getTime()
        return {
            "episode": episode,
            "epsilon": epsilon,
            "return": -queue_vehicle_seconds,
            "average_queue": total_queue / max(1, steps),
            "queue_vehicle_seconds": queue_vehicle_seconds,
            "arrived_vehicles": arrived_vehicles,
            "simulation_seconds": elapsed,
            "hold_actions": hold_actions,
            "switch_actions": switch_actions,
        }
    finally:
        traci.close()


def main() -> None:
    args = parse_args()
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(
            f"SUMO config not found at {CONFIG_FILE}. "
            "Build the network with sumo\\scripts\\build_network.ps1 first."
        )
    binary = shutil.which("sumo")
    if binary is None:
        raise RuntimeError(
            "Could not find 'sumo' on PATH. Add the SUMO bin directory to PATH."
        )

    q_table = load_q_table(args.q_table)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    end_time = min(args.max_sim_time or configured_end_time(), configured_end_time())
    write_header = not args.metrics.exists() or args.metrics.stat().st_size == 0
    completed_episodes = 0
    if not write_header:
        with args.metrics.open(newline="", encoding="utf-8") as metrics_file:
            rows = csv.DictReader(metrics_file)
            if "episode" not in (rows.fieldnames or []):
                raise ValueError(f"Metrics file has no episode column: {args.metrics}")
            for row in rows:
                completed_episodes = int(row["episode"])

    rng = random.Random(args.seed + completed_episodes)
    epsilon = max(
        args.epsilon_min,
        args.epsilon_start * args.epsilon_decay**completed_episodes,
    )

    with args.metrics.open("a", newline="", encoding="utf-8") as metrics_file:
        writer = csv.DictWriter(metrics_file, fieldnames=METRIC_FIELDS)
        if write_header:
            writer.writeheader()
        for episode in range(completed_episodes + 1, completed_episodes + args.episodes + 1):
            result = run_episode(
                binary,
                episode,
                epsilon,
                args,
                q_table,
                rng,
                end_time,
            )
            writer.writerow(result)
            metrics_file.flush()
            save_q_table(args.q_table, q_table)
            print(json.dumps(result), flush=True)
            epsilon = max(args.epsilon_min, epsilon * args.epsilon_decay)

    print(f"Saved Q-table: {args.q_table}")
    print(f"Saved episode metrics: {args.metrics}")


if __name__ == "__main__":
    main()
