import argparse
import json
import shutil
import statistics
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import traci

from simulate_emergency import (
    APPROACH_EDGES,
    GREEN_PHASES,
    TRAFFIC_LIGHT_ID,
    apply_queue_pressure,
    choose_greedy_action,
    load_policy,
    observe_queues,
    observe_state,
)


SUMO_DIR = Path(__file__).resolve().parents[1]
NETWORK_FILE = SUMO_DIR / "network" / "intersection.net.xml"
Q_TABLE_FILE = SUMO_DIR / "models" / "q_table.json"
APPROACHES = {
    "north": ("north_in", "south_out", 0),
    "south": ("south_in", "north_out", 0),
    "east": ("east_in", "west_out", 2),
    "west": ("west_in", "east_out", 2),
}
LANE_IDS = tuple(
    f"{edge}_{lane}"
    for approach in APPROACHES.values()
    for edge in (approach[0],)
    for lane in range(2)
)
VEHICLE_TYPE = "astra_manual_car"
EMERGENCY_TYPE = "astra_manual_emergency"


def write_routes(scenario: dict, path: Path) -> tuple[int, list[str]]:
    root = ET.Element("routes")
    ET.SubElement(
        root,
        "vType",
        {
            "id": VEHICLE_TYPE,
            "vClass": "passenger",
            "color": "0,0.65,1",
            "length": "5",
            "minGap": "2.5",
            "maxSpeed": "13.89",
            "accel": "2.6",
            "decel": "4.5",
        },
    )
    ET.SubElement(
        root,
        "vType",
        {
            "id": EMERGENCY_TYPE,
            "vClass": "emergency",
            "guiShape": "emergency",
            "color": "1,0,0",
            "length": "5",
            "minGap": "2.5",
            "maxSpeed": "20",
            "accel": "3",
            "decel": "6",
        },
    )

    emergency_keys = {
        (vehicle["approach"], vehicle["lane"])
        for vehicle in scenario["emergency_vehicles"]
    }
    emergency_ids = []
    expected_vehicles = 0
    vehicles = []
    for approach, (in_edge, out_edge, _) in APPROACHES.items():
        if approach not in scenario["active_approaches"]:
            continue
        ET.SubElement(
            root,
            "route",
            {"id": f"manual_route_{approach}", "edges": f"{in_edge} {out_edge}"},
        )
        for lane in range(2):
            if (approach, lane) in emergency_keys:
                emergency_id = f"manual_emergency_{approach}_{lane}"
                vehicles.append(
                    ET.Element(
                        "vehicle",
                        {
                            "id": emergency_id,
                            "type": EMERGENCY_TYPE,
                            "route": f"manual_route_{approach}",
                            "depart": "0",
                            "departLane": str(lane),
                            "departPos": "base",
                            "departSpeed": "max",
                        },
                    )
                )
                emergency_ids.append(emergency_id)
                expected_vehicles += 1
            count = scenario["lane_counts"][approach][lane]
            for index in range(count):
                vehicles.append(
                    ET.Element(
                        "vehicle",
                        {
                            "id": f"manual_car_{approach}_{lane}_{index}",
                            "type": VEHICLE_TYPE,
                            "route": f"manual_route_{approach}",
                            "depart": str(5 + index * 3),
                            "departLane": str(lane),
                            "departPos": "base",
                            "departSpeed": "max",
                        },
                    )
                )
                expected_vehicles += 1
    for vehicle in sorted(vehicles, key=lambda item: float(item.get("depart", "0"))):
        root.append(vehicle)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return expected_vehicles, emergency_ids


def write_gui_settings(path: Path) -> None:
    settings = ET.Element("viewsettings")
    scheme = ET.SubElement(settings, "scheme", {"name": "custom_1"})
    ET.SubElement(
        scheme,
        "vehicles",
        {
            "vehicleMode": "2",
            "vehicle_exaggeration": "1.25",
            "vehicle_minSize": "1.5",
        },
    )
    ET.ElementTree(settings).write(path, encoding="utf-8", xml_declaration=True)


def run_trial(
    binary: str,
    visualize: bool,
    gui_settings_file: Path,
    route_file: Path,
    tripinfo_file: Path,
    duration: int,
    adaptive: bool,
    q_values: dict,
    emergency_ids: list[str],
    expected_vehicles: int,
    active_approaches: list[str],
) -> dict:
    command = [
        binary,
        "--net-file",
        str(NETWORK_FILE),
        "--route-files",
        str(route_file),
        "--begin",
        "0",
        "--end",
        str(duration),
        "--step-length",
        "1",
        "--tripinfo-output",
        str(tripinfo_file),
        "--no-step-log",
        "true",
        "--duration-log.disable",
        "true",
    ]
    if visualize:
        command.extend(
            [
                "--gui-settings-file",
                str(gui_settings_file),
                "--delay",
                "100",
                "--start",
                "--quit-on-end",
            ]
        )
    traci.start(command)
    queue_total = 0
    co2_emissions_mg = 0.0
    steps = 0
    active_priority = None
    extended_priorities = set()
    next_decision = 0.0
    green_started_at = 0.0
    current_green_phase = None
    colored_emergencies = set()
    signal_order = []
    last_logged_phase = None
    active_groups = {
        APPROACHES[approach][2] for approach in active_approaches
    }
    emergency_approach = {
        vehicle_id: vehicle_id.removeprefix("manual_emergency_").rsplit("_", 1)[0]
        for vehicle_id in emergency_ids
    }
    try:
        if TRAFFIC_LIGHT_ID not in traci.trafficlight.getIDList():
            raise RuntimeError(f"SUMO network is missing traffic light {TRAFFIC_LIGHT_ID!r}.")
        if any(lane_id not in traci.lane.getIDList() for lane_id in LANE_IDS):
            raise RuntimeError("SUMO network is missing one or more configured approach lanes.")

        if len(active_groups) == 1:
            only_phase = next(iter(active_groups))
            traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, only_phase)
            traci.trafficlight.setPhaseDuration(TRAFFIC_LIGHT_ID, duration + 1.0)

        while (
            traci.simulation.getTime() < duration
            and traci.simulation.getMinExpectedNumber() > 0
        ):
            now = traci.simulation.getTime()
            phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
            if phase != last_logged_phase:
                north_south_color = (
                    "GREEN" if phase == 0 else "YELLOW" if phase == 1 else "RED"
                )
                east_west_color = (
                    "GREEN" if phase == 2 else "YELLOW" if phase == 3 else "RED"
                )
                signal_order.append(
                    {
                        "time_seconds": round(now, 1),
                        "phase_index": phase,
                        "phase_name": (
                            "North-South green"
                            if phase == 0
                            else "North-South yellow"
                            if phase == 1
                            else "East-West green"
                            if phase == 2
                            else "East-West yellow"
                        ),
                        "approach_states": {
                            approach: (
                                north_south_color
                                if APPROACHES[approach][2] == 0
                                else east_west_color
                            )
                            for approach in active_approaches
                        },
                    }
                )
                last_logged_phase = phase
            if phase in GREEN_PHASES and phase != current_green_phase:
                current_green_phase = phase
                green_started_at = now
                if not adaptive and len(active_groups) > 1:
                    traci.trafficlight.setPhaseDuration(TRAFFIC_LIGHT_ID, 15.0)

            present_emergencies = [
                vehicle_id
                for vehicle_id in emergency_ids
                if vehicle_id in traci.vehicle.getIDList()
            ]
            for vehicle_id in present_emergencies:
                if vehicle_id not in colored_emergencies:
                    traci.vehicle.setColor(vehicle_id, (255, 0, 0, 255))
                    if traci.vehicle.getColor(vehicle_id) != (255, 0, 0, 255):
                        raise RuntimeError(f"SUMO did not apply the red emergency color to {vehicle_id}.")
                    colored_emergencies.add(vehicle_id)
            if adaptive and present_emergencies:
                emergency_id = present_emergencies[0]
                approach = emergency_approach[emergency_id]
                target_phase = APPROACHES[approach][2]
                priority_key = (emergency_id, target_phase)
                if phase in GREEN_PHASES and phase != target_phase:
                    traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, phase + 1)
                elif phase == target_phase and priority_key not in extended_priorities:
                    remaining = max(
                        0.0,
                        traci.trafficlight.getNextSwitch(TRAFFIC_LIGHT_ID) - now,
                    )
                    traci.trafficlight.setPhaseDuration(
                        TRAFFIC_LIGHT_ID, max(remaining, 20.0)
                    )
                    extended_priorities.add(priority_key)
                active_priority = priority_key
            elif adaptive and len(active_groups) > 1:
                if active_priority is not None:
                    next_decision = now
                    active_priority = None
                if phase in GREEN_PHASES and now >= next_decision:
                    queues = observe_queues()
                    action = choose_greedy_action(q_values, observe_state())
                    action = apply_queue_pressure(
                        action,
                        GREEN_PHASES.index(phase),
                        queues[0],
                        queues[1],
                        now - green_started_at,
                        10.0,
                        45.0,
                    )
                    if action == 1:
                        traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, phase + 1)
                    else:
                        traci.trafficlight.setPhaseDuration(
                            TRAFFIC_LIGHT_ID, 5.0
                        )
                    next_decision = now + 5.0

            traci.simulationStep()
            steps += 1
            queue_total += sum(
                traci.edge.getLastStepHaltingNumber(edge_id)
                for edge_id in APPROACH_EDGES
            )
            co2_emissions_mg += sum(
                traci.lane.getCO2Emission(lane_id)
                for lane_id in traci.lane.getIDList()
            )
    finally:
        traci.close()

    trips = ET.parse(tripinfo_file).getroot().findall("tripinfo")
    waits = [float(trip.get("waitingTime", "0")) for trip in trips]
    travel_times = [float(trip.get("duration", "0")) for trip in trips]
    emergency_trips = [
        trip for trip in trips if trip.get("id", "").startswith("manual_emergency_")
    ]
    return {
        "controller": "ASTRA adaptive" if adaptive else "Fixed-time",
        "arrived_vehicles": len(trips),
        "unfinished_vehicles": max(0, expected_vehicles - len(trips)),
        "average_waiting_time_seconds": statistics.fmean(waits) if waits else 0.0,
        "average_travel_time_seconds": (
            statistics.fmean(travel_times) if travel_times else 0.0
        ),
        "average_queue_vehicles": queue_total / max(1, steps),
        "throughput_vehicles_per_minute": len(trips) / max(1, steps) * 60,
        "co2_emissions_grams": co2_emissions_mg / 1000,
        "emergency_arrived": len(emergency_trips),
        "emergency_average_waiting_time_seconds": (
            statistics.fmean(
                float(trip.get("waitingTime", "0")) for trip in emergency_trips
            )
            if emergency_trips
            else None
        ),
        "simulation_seconds": steps,
        "signal_order": signal_order,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a manually configured SUMO intersection scenario.")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--gui", action="store_true", help="Show SUMO-GUI at a readable playback speed.")
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    duration = scenario["duration_seconds"]
    if not isinstance(duration, int) or duration < 60 or duration > 900:
        raise ValueError("Simulation duration must be from 60 to 900 seconds.")
    if not NETWORK_FILE.is_file():
        raise FileNotFoundError(f"SUMO network not found: {NETWORK_FILE}")
    if not Q_TABLE_FILE.is_file():
        raise FileNotFoundError(f"Trained Q-learning table not found: {Q_TABLE_FILE}")
    binary = shutil.which("sumo-gui" if args.gui else "sumo")
    if binary is None:
        binary_name = "sumo-gui" if args.gui else "sumo"
        raise RuntimeError(f"Could not find {binary_name!r} on PATH. Add the SUMO bin directory to PATH.")
    q_values = load_policy(Q_TABLE_FILE)

    with tempfile.TemporaryDirectory(prefix="astra-manual-sumo-") as temp_dir:
        temp_path = Path(temp_dir)
        route_file = temp_path / "manual.rou.xml"
        gui_settings_file = temp_path / "manual.gui.xml"
        expected_vehicles, emergency_ids = write_routes(scenario, route_file)
        if args.gui:
            write_gui_settings(gui_settings_file)
        if expected_vehicles < 1:
            raise ValueError("Add at least one regular or emergency vehicle to the scenario.")
        results = []
        for adaptive in (False, True):
            tripinfo_file = temp_path / (
                "adaptive.tripinfo.xml" if adaptive else "fixed.tripinfo.xml"
            )
            results.append(
                run_trial(
                    binary=binary,
                    visualize=args.gui,
                    gui_settings_file=gui_settings_file,
                    route_file=route_file,
                    tripinfo_file=tripinfo_file,
                    duration=duration,
                    adaptive=adaptive,
                    q_values=q_values,
                    emergency_ids=emergency_ids,
                    expected_vehicles=expected_vehicles,
                    active_approaches=scenario["active_approaches"],
                )
            )
    print(
        json.dumps(
            {
                "requested_vehicles": expected_vehicles,
                "active_approaches": scenario["active_approaches"],
                "results": results,
            }
        )
    )


if __name__ == "__main__":
    main()
