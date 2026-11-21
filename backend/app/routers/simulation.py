import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, conint, validator

from ..auth import current_user


router = APIRouter(prefix="/api/simulation", tags=["simulation"])
COMPARISON_FILE = (
    Path(__file__).resolve().parents[3]
    / "sumo"
    / "results"
    / "controller_comparison.csv"
)
MANUAL_SIMULATION_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "sumo"
    / "scripts"
    / "run_manual_scenario.py"
)
INTEGER_FIELDS = {"replications"}
NUMERIC_FIELDS = {
    "arrived_vehicles",
    "throughput_vehicles_per_minute",
    "average_waiting_time_seconds",
    "average_travel_time_seconds",
    "average_queue_vehicles",
    "queue_vehicle_seconds",
    "co2_emissions_grams",
}
Approach = Literal["north", "south", "east", "west"]
APPROACHES = ("north", "south", "east", "west")


class EmergencyLane(BaseModel):
    approach: Approach
    lane: conint(ge=0, le=1)


class ManualScenario(BaseModel):
    road_count: conint(ge=2, le=4) = 4
    active_approaches: List[Approach] = Field(default_factory=lambda: list(APPROACHES))
    lane_counts: Dict[Approach, List[conint(ge=0, le=50)]]
    emergency_vehicles: List[EmergencyLane] = Field(default_factory=list)
    duration_seconds: conint(ge=60, le=900) = 300
    visualize: bool = True

    @validator("active_approaches")
    def validate_active_approaches(cls, approaches, values):
        if len(approaches) != len(set(approaches)):
            raise ValueError("Each active approach can only be selected once.")
        if len(approaches) != values.get("road_count"):
            raise ValueError("Select exactly the configured number of approaches.")
        return approaches

    @validator("lane_counts")
    def validate_approach_lanes(cls, lane_counts):
        if set(lane_counts) != {"north", "south", "east", "west"}:
            raise ValueError("Provide lane counts for north, south, east, and west.")
        if any(len(counts) != 2 for counts in lane_counts.values()):
            raise ValueError("Each approach must provide counts for both lanes.")
        return lane_counts

    @validator("emergency_vehicles")
    def validate_emergency_lanes(cls, vehicles):
        lane_keys = [(vehicle.approach, vehicle.lane) for vehicle in vehicles]
        if len(lane_keys) != len(set(lane_keys)):
            raise ValueError("Only one emergency vehicle can be assigned to each lane.")
        return vehicles

    def validate_total(self):
        regular_count = sum(sum(counts) for counts in self.lane_counts.values())
        total = regular_count + len(self.emergency_vehicles)
        inactive_approaches = set(APPROACHES) - set(self.active_approaches)
        if any(any(self.lane_counts[approach]) for approach in inactive_approaches):
            raise ValueError("Inactive approaches cannot have regular vehicles.")
        if any(vehicle.approach in inactive_approaches for vehicle in self.emergency_vehicles):
            raise ValueError("Emergency vehicles must use an active approach.")
        if total < 1:
            raise ValueError("Add at least one regular or emergency vehicle.")
        if total > 100:
            raise ValueError("A manual scenario is limited to 100 vehicles.")


@router.get("/comparison")
def comparison(_: dict = Depends(current_user)):
    if not COMPARISON_FILE.is_file():
        raise HTTPException(
            404,
            "No SUMO controller comparison is available. Run "
            "sumo\\scripts\\compare_controllers.py first.",
        )

    try:
        with COMPARISON_FILE.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames or not NUMERIC_FIELDS.issubset(reader.fieldnames):
                raise ValueError("Comparison CSV is missing required metric columns")
            rows = list(reader)
        if not rows:
            raise ValueError("Comparison CSV contains no controller results")
        summary = []
        for row in rows:
            result = {"controller": row["controller"]}
            result.update(
                {
                    field: int(row[field])
                    for field in INTEGER_FIELDS
                    if field in row
                }
            )
            result.update(
                {field: float(row[field]) for field in NUMERIC_FIELDS}
            )
            summary.append(result)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(500, f"Could not read SUMO comparison results: {exc}") from exc

    return {
        "updated_at": datetime.fromtimestamp(
            COMPARISON_FILE.stat().st_mtime, timezone.utc
        ).isoformat(),
        "summary": summary,
    }


@router.post("/manual")
def run_manual_scenario(
    scenario: ManualScenario, _: dict = Depends(current_user)
):
    try:
        scenario.validate_total()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not MANUAL_SIMULATION_SCRIPT.is_file():
        raise HTTPException(
            503, f"Manual SUMO simulation script not found: {MANUAL_SIMULATION_SCRIPT}"
        )

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", delete=False
    ) as scenario_file:
        json.dump(scenario.dict(), scenario_file)
        scenario_path = scenario_file.name
    try:
        try:
            command = [
                sys.executable,
                "-B",
                str(MANUAL_SIMULATION_SCRIPT),
                "--scenario",
                scenario_path,
            ]
            if scenario.visualize:
                command.append("--gui")
            completed = subprocess.run(
                command,
                cwd=MANUAL_SIMULATION_SCRIPT.parents[2],
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504, "Manual SUMO simulation exceeded 240 seconds") from exc
        except OSError as exc:
            raise HTTPException(503, f"Could not start SUMO simulation: {exc}") from exc
    finally:
        os.remove(scenario_path)

    if completed.returncode != 0:
        details = completed.stderr.strip()[-2000:] or "SUMO exited without an error message"
        raise HTTPException(500, f"Manual SUMO simulation failed: {details}")
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "SUMO returned an invalid manual simulation result") from exc
