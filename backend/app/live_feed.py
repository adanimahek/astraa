import base64
import copy
import json
import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2

from . import yolo_service
from .config import settings


logger = logging.getLogger(__name__)
APPROACHES = ("north", "south", "east", "west")
GREEN_PHASES = (0, 2)
TRAFFIC_LIGHT_ID = "center"
SUMO_DIR = Path(__file__).resolve().parents[2] / "sumo"
SUMO_CONFIG = SUMO_DIR / "config" / "intersection.sumocfg"
Q_TABLE = SUMO_DIR / "models" / "q_table.json"


def _queue_bucket(count: int) -> int:
    if count == 0:
        return 0
    if count <= 3:
        return 1
    if count <= 7:
        return 2
    return 3


def _queue_aware_action(
    q_action: int,
    current_phase: int,
    north_south_count: int,
    east_west_count: int,
    green_elapsed: float,
) -> tuple[int, str]:
    preferred_phase = None
    preferred_name = None
    if north_south_count > east_west_count + 2:
        preferred_phase = 0
        preferred_name = "North + South"
    elif east_west_count > north_south_count + 2:
        preferred_phase = 1
        preferred_name = "East + West"

    if green_elapsed >= 45.0:
        return 1, "Maximum green reached; switch phase."
    if green_elapsed < 10.0:
        return 0, "Minimum green is active; hold the current phase."
    if preferred_phase is not None:
        action = int(preferred_phase != current_phase)
        return action, f"Queue pressure favors {preferred_name}."
    return q_action, "Q-learning policy decision."


def _load_q_values() -> dict:
    payload = json.loads(Q_TABLE.read_text(encoding="utf-8"))
    if (
        payload.get("format_version") != 1
        or payload.get("algorithm") != "tabular_q_learning"
        or payload.get("actions") != ["hold", "switch"]
    ):
        raise ValueError(f"Incompatible Q-learning policy: {Q_TABLE}")
    values = payload.get("q_values")
    if not isinstance(values, dict) or not values:
        raise ValueError(f"Q-learning policy has no states: {Q_TABLE}")
    return values


class LiveFeedManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None
        self._status = self._empty_status()

    @staticmethod
    def _empty_status() -> dict:
        return {
            "state": "idle",
            "message": "Live cameras and SUMO are not running.",
            "simulation_time_seconds": 0.0,
            "simulation_end_seconds": None,
            "controller": "trained Q-learning with emergency-priority override",
            "controller_decision": "Waiting for camera traffic counts.",
            "signal": {
                "phase": None,
                "state": "unknown",
                "green_approaches": [],
            },
            "priority_active_approach": None,
            "cameras": {
                approach: {
                    "connected": False,
                    "last_frame_at": None,
                    "counts": {},
                    "emergency_detected": False,
                    "annotated_frame": None,
                }
                for approach in APPROACHES
            },
            "metrics": {
                "average_waiting_time_seconds": 0.0,
                "average_travel_time_seconds": 0.0,
                "average_queue_vehicles": 0.0,
                "queue_vehicle_seconds": 0.0,
                "throughput_vehicles_per_minute": 0.0,
                "arrived_vehicles": 0,
                "co2_emissions_grams": 0.0,
                "emergency_vehicle_dispatches": 0,
                "emergency_priority_override_steps": 0,
            },
        }

    def status(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._status)

    def start(self) -> dict:
        missing = [
            approach
            for approach, url in settings.live_feed_urls.items()
            if not url
        ]
        if missing:
            raise ValueError(
                "Configure all four LIVE_FEED_URL_NORTH/SOUTH/EAST/WEST "
                "values in backend\\.env before starting the live system."
            )
        if not SUMO_CONFIG.is_file():
            raise FileNotFoundError(f"SUMO config not found: {SUMO_CONFIG}")
        if not Q_TABLE.is_file():
            raise FileNotFoundError(f"Trained Q-learning policy not found: {Q_TABLE}")
        if shutil.which("sumo") is None:
            raise RuntimeError("Could not find 'sumo' on PATH.")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("The live feed system is already running.")
            self._stop_event = threading.Event()
            self._status = self._empty_status()
            self._status.update(
                state="starting",
                message="Connecting to the four cameras and starting SUMO.",
            )
            self._thread = threading.Thread(
                target=self._run, name="astra-live-feed", daemon=True
            )
            self._thread.start()
            return copy.deepcopy(self._status)

    def stop(self) -> dict:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=10)
        with self._lock:
            if thread and thread.is_alive():
                self._status["message"] = (
                    "Stop requested; waiting for the camera or SUMO step to finish."
                )
            elif self._status["state"] not in ("error", "completed"):
                self._status["state"] = "stopped"
                self._status["message"] = "Live camera processing and SUMO stopped."
            return copy.deepcopy(self._status)

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status["state"] = "error"
            self._status["message"] = message

    @staticmethod
    def _signal_status(phase: int) -> dict:
        if phase == 0:
            return {
                "phase": phase,
                "state": "North + South green",
                "green_approaches": ["north", "south"],
            }
        if phase == 2:
            return {
                "phase": phase,
                "state": "East + West green",
                "green_approaches": ["east", "west"],
            }
        return {
            "phase": phase,
            "state": "Yellow / safe transition",
            "green_approaches": [],
        }

    def _run(self) -> None:
        caps = {}
        traci = None
        traci_started = False
        try:
            q_values = _load_q_values()
            for approach in APPROACHES:
                cap = cv2.VideoCapture(
                    settings.live_feed_urls[approach],
                    cv2.CAP_FFMPEG,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                        5000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        5000,
                    ],
                )
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    cap.release()
                    raise RuntimeError(
                        f"Could not open the {approach} RTSP camera. Check its "
                        "URL, credentials, network access, and backend FFmpeg support."
                    )
                caps[approach] = cap

            import traci as traci_module

            traci = traci_module
            traci.start(
                [
                    shutil.which("sumo"),
                    "-c",
                    str(SUMO_CONFIG),
                    "--no-step-log",
                    "true",
                    "--duration-log.disable",
                    "true",
                ]
            )
            traci_started = True
            if TRAFFIC_LIGHT_ID not in traci.trafficlight.getIDList():
                raise RuntimeError(
                    "SUMO network is missing the expected 'center' traffic light."
                )
            if "astra_emergency_type" not in traci.vehicletype.getIDList():
                raise RuntimeError("SUMO route file is missing the emergency vehicle type.")

            sumo_config = ET.parse(SUMO_CONFIG).getroot()
            end_element = sumo_config.find("./time/end")
            step_element = sumo_config.find("./time/step-length")
            if end_element is None or end_element.get("value") is None:
                raise ValueError("SUMO config has no simulation end time.")
            end_time = float(end_element.get("value"))
            step_length = 1.0
            if step_element is not None and step_element.get("value") is not None:
                step_length = float(step_element.get("value"))

            next_decision = traci.simulation.getTime()
            current_green = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
            green_started_at = traci.simulation.getTime()
            with self._lock:
                self._status["signal"] = self._signal_status(current_green)
            latest_counts = {approach: 0 for approach in APPROACHES}
            last_emergency = {approach: False for approach in APPROACHES}
            last_frame_time = {approach: 0.0 for approach in APPROACHES}
            camera_start_time = time.monotonic()
            next_camera_capture = 0.0
            queue_total = 0
            co2_mg = 0.0
            travel_time_total = 0.0
            departure_times = {}
            steps = 0
            arrived = 0
            emergency_sequence = 0
            emergency_dispatches = 0
            emergency_priority_steps = 0
            with self._lock:
                self._status.update(
                    state="running",
                    message="YOLO camera analysis and SUMO Q-learning are running.",
                    simulation_end_seconds=end_time,
                )

            while (
                traci.simulation.getTime() < end_time
                and not self._stop_event.is_set()
            ):
                wall_time = time.monotonic()
                if wall_time >= next_camera_capture:
                    for approach, cap in caps.items():
                        ok, frame = cap.read()
                        if not ok:
                            last_received = (
                                last_frame_time[approach] or camera_start_time
                            )
                            if wall_time - last_received > 8:
                                raise RuntimeError(
                                    f"The {approach} RTSP camera stopped providing frames."
                                )
                            continue
                        observation = yolo_service.detect_live_frame(frame)
                        latest_counts[approach] = sum(
                            observation["counts"].values()
                        )
                        emergency = observation["emergency_detected"]
                        if emergency and not last_emergency[approach]:
                            route_id = f"emergency_{approach}"
                            if route_id not in traci.route.getIDList():
                                raise RuntimeError(
                                    f"SUMO route {route_id!r} is missing."
                                )
                            emergency_sequence += 1
                            vehicle_id = f"astra_live_emergency_{emergency_sequence}"
                            traci.vehicle.add(
                                vehID=vehicle_id,
                                routeID=route_id,
                                typeID="astra_emergency_type",
                                depart="now",
                                departLane="best",
                                departPos="base",
                                departSpeed="max",
                            )
                            traci.vehicle.setColor(
                                vehicle_id, (255, 40, 40, 255)
                            )
                            emergency_dispatches += 1
                        last_emergency[approach] = emergency
                        last_frame_time[approach] = wall_time
                        frame_data = base64.b64encode(
                            observation["annotated_frame"]
                        ).decode("ascii")
                        with self._lock:
                            self._status["cameras"][approach] = {
                                "connected": True,
                                "last_frame_at": datetime.now(
                                    timezone.utc
                                ).isoformat(),
                                "counts": observation["counts"],
                                "total_vehicles": latest_counts[approach],
                                "emergency_detected": emergency,
                                "annotated_frame": frame_data,
                            }
                    next_camera_capture = wall_time + 1.0

                simulation_time = traci.simulation.getTime()
                phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
                if phase in GREEN_PHASES:
                    if phase != current_green:
                        current_green = phase
                        green_started_at = simulation_time

                    emergency_approaches = [
                        approach
                        for approach in APPROACHES
                        if last_emergency[approach]
                    ]
                    with self._lock:
                        self._status["priority_active_approach"] = (
                            emergency_approaches[0]
                            if emergency_approaches
                            else None
                        )
                    if emergency_approaches:
                        emergency_priority_steps += 1
                        approach = emergency_approaches[0]
                        target_phase = 0 if approach in ("north", "south") else 2
                        with self._lock:
                            self._status["controller_decision"] = (
                                f"Emergency override: serve {approach} approach."
                            )
                        if phase != target_phase:
                            traci.trafficlight.setPhase(
                                TRAFFIC_LIGHT_ID, phase + 1
                            )
                        else:
                            remaining = max(
                                0.0,
                                traci.trafficlight.getNextSwitch(TRAFFIC_LIGHT_ID)
                                - simulation_time,
                            )
                            traci.trafficlight.setPhaseDuration(
                                TRAFFIC_LIGHT_ID, max(remaining, 15.0)
                            )
                        next_decision = simulation_time + 5.0
                    elif simulation_time >= next_decision:
                        north_south_count = (
                            latest_counts["north"] + latest_counts["south"]
                        )
                        east_west_count = (
                            latest_counts["east"] + latest_counts["west"]
                        )
                        state = (
                            _queue_bucket(north_south_count),
                            _queue_bucket(east_west_count),
                            GREEN_PHASES.index(phase),
                        )
                        q_values_for_state = q_values.get(
                            ",".join(str(value) for value in state), [0.0, 0.0]
                        )
                        action = 1 if q_values_for_state[1] > q_values_for_state[0] else 0
                        green_elapsed = simulation_time - green_started_at
                        action, decision_reason = _queue_aware_action(
                            action,
                            GREEN_PHASES.index(phase),
                            north_south_count,
                            east_west_count,
                            green_elapsed,
                        )
                        next_phase = phase if action == 0 else (2 if phase == 0 else 0)
                        next_approaches = (
                            "North + South" if next_phase == 0 else "East + West"
                        )
                        with self._lock:
                            self._status["controller_decision"] = (
                                f"{decision_reason} "
                                f"Q-learning {'holds' if action == 0 else 'switches'}; "
                                f"{next_approaches} green."
                            )
                        if action == 1:
                            traci.trafficlight.setPhase(
                                TRAFFIC_LIGHT_ID, phase + 1
                            )
                        else:
                            traci.trafficlight.setPhaseDuration(
                                TRAFFIC_LIGHT_ID, 5.0
                            )
                        next_decision = simulation_time + 5.0

                traci.simulationStep()
                steps += 1
                queue_total += sum(
                    traci.edge.getLastStepHaltingNumber(edge)
                    for edge in (
                        "north_in",
                        "south_in",
                        "east_in",
                        "west_in",
                    )
                )
                co2_mg += sum(
                    traci.lane.getCO2Emission(lane)
                    for lane in traci.lane.getIDList()
                ) * step_length
                arrived += traci.simulation.getArrivedNumber()
                for vehicle_id in traci.simulation.getDepartedIDList():
                    departure_times[vehicle_id] = traci.simulation.getTime()
                for vehicle_id in traci.simulation.getArrivedIDList():
                    departure_time = departure_times.pop(vehicle_id, None)
                    if departure_time is not None:
                        travel_time_total += (
                            traci.simulation.getTime() - departure_time
                        )
                with self._lock:
                    elapsed = traci.simulation.getTime()
                    signal_phase = traci.trafficlight.getPhase(TRAFFIC_LIGHT_ID)
                    self._status["signal"] = self._signal_status(signal_phase)
                    self._status["approach_vehicle_counts"] = latest_counts.copy()
                    queue_vehicle_seconds = queue_total * step_length
                    self._status["metrics"] = {
                        "average_waiting_time_seconds": (
                            queue_vehicle_seconds / arrived if arrived else 0.0
                        ),
                        "average_travel_time_seconds": (
                            travel_time_total / arrived if arrived else 0.0
                        ),
                        "average_queue_vehicles": queue_total / max(1, steps),
                        "queue_vehicle_seconds": queue_vehicle_seconds,
                        "throughput_vehicles_per_minute": (
                            arrived / (elapsed / 60) if elapsed else 0.0
                        ),
                        "arrived_vehicles": arrived,
                        "co2_emissions_grams": co2_mg / 1000,
                        "emergency_vehicle_dispatches": emergency_dispatches,
                        "emergency_priority_override_steps": emergency_priority_steps,
                    }
                    self._status["simulation_time_seconds"] = elapsed
                time.sleep(0.1)

            with self._lock:
                if self._stop_event.is_set():
                    self._status.update(
                        state="stopped",
                        message="Live camera processing and SUMO stopped.",
                    )
                else:
                    self._status.update(
                        state="completed",
                        message="The configured SUMO simulation completed.",
                    )
        except Exception as exc:
            logger.exception("ASTRA live camera/SUMO session failed")
            self._set_error(str(exc))
        finally:
            for cap in caps.values():
                cap.release()
            if traci_started and traci is not None:
                traci.close()


live_feed = LiveFeedManager()
