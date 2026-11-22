"""Red-light violation monitoring for SUMO via TraCI.

``SumoRedLightMonitor`` is driven from a TraCI loop (see
``sumo/scripts/detect_red_light_violations.py``).  It takes the ``traci``
module as a constructor argument so it can be unit-tested with a fake.

* tracking ID  = SUMO vehicle ID
* BEFORE line  = vehicle on a lane controlled by the traffic light
* AFTER line   = vehicle that was approaching and is now on the junction's
  internal lane (``:<junction>_*``) or an outgoing lane
* signal state = the state of the vehicle's own link (``getNextTLS``), so
  per-movement signals (e.g. protected turns) are respected.

Vehicles already inside the junction when first observed are ignored, so a
vehicle that entered before red is never flagged.
"""
from typing import Callable, Dict, List, Optional, Tuple

from .red_light import RedLightRule, Side, TrackObservation
from .signal import SignalState


class SumoRedLightMonitor:
    def __init__(self, traci_module, tls_id: str = "center", rule: Optional[RedLightRule] = None,
                 on_violation: Optional[Callable[[dict], Optional[dict]]] = None):
        self.traci = traci_module
        self.tls_id = tls_id
        self.rule = rule or RedLightRule(grace_seconds=0.0)
        self.on_violation = on_violation
        links = self.traci.trafficlight.getControlledLinks(tls_id)
        self.controlled_lanes = {link[0] for group in links for link in group if link}
        self.link_count = len(links)
        # vehicle id -> (link index, incoming lane)
        self._approaching: Dict[str, Tuple[int, str]] = {}
        self.events: List[dict] = []

    @staticmethod
    def _lane_key(link_index: int) -> str:
        return f"link{link_index}"

    def _link_for(self, vid: str) -> Optional[Tuple[int, str]]:
        for entry in self.traci.vehicle.getNextTLS(vid):
            if entry[0] == self.tls_id:
                return int(entry[1]), entry[3]
        return None

    def step(self) -> List[dict]:
        t = float(self.traci.simulation.getTime())
        state_str = self.traci.trafficlight.getRedYellowGreenState(self.tls_id)
        for i, ch in enumerate(state_str):
            self.rule.update_signal(self._lane_key(i), t, SignalState.from_sumo(ch))
        new_events = []
        present = set(self.traci.vehicle.getIDList())
        for vid in present:
            lane = self.traci.vehicle.getLaneID(vid)
            if lane in self.controlled_lanes:
                link = self._link_for(vid)
                if link is None:
                    continue
                link_index, ch = link
                self._approaching[vid] = (link_index, lane)
                side, state = Side.BEFORE, SignalState.from_sumo(ch)
            elif vid in self._approaching:
                link_index, in_lane = self._approaching.pop(vid)
                side = Side.AFTER
                state = (SignalState.from_sumo(state_str[link_index])
                         if link_index < len(state_str) else SignalState.UNKNOWN)
                lane = in_lane
            else:
                continue
            ev = self.rule.observe(TrackObservation(
                track_id=vid, timestamp=t, side=side, signal_state=state,
                lane=self._lane_key(link_index),
                vehicle_class=self.traci.vehicle.getTypeID(vid),
                position=tuple(self.traci.vehicle.getPosition(vid)),
                meta={"incoming_lane": lane, "approach": _approach(lane),
                      "link_index": link_index, "tls_id": self.tls_id,
                      "speed_mps": round(float(self.traci.vehicle.getSpeed(vid)), 2)},
            ))
            if ev is not None:
                doc = ev.to_dict()
                if self.on_violation:
                    doc = self.on_violation(doc) or doc
                new_events.append(doc)
        # vehicles that left the network while approaching
        for vid in list(self._approaching):
            if vid not in present:
                self._approaching.pop(vid, None)
        self.events.extend(new_events)
        return new_events


def _approach(lane: str) -> Optional[str]:
    prefix = lane.split("_")[0] if lane else ""
    return prefix if prefix in ("north", "south", "east", "west") else None


def render_schematic(traci_module, tls_id: str, event: dict, size: int = 640,
                     zoom_radius: Optional[float] = None):
    """Draw a top-down evidence image of the simulation state at the violation."""
    import cv2
    import numpy as np

    tr = traci_module
    shapes = [tr.lane.getShape(l) for l in tr.lane.getIDList() if not l.startswith(":")]
    if zoom_radius:
        cx, cy = event["position"] or (0.0, 0.0)
        minx, maxx, miny, maxy = cx - zoom_radius, cx + zoom_radius, cy - zoom_radius, cy + zoom_radius
    else:
        pts = [p for s in shapes for p in s] or [(0, 0), (1, 1)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, 1.0)
    margin = 30

    def px(p):
        x = margin + (p[0] - minx) / span * (size - 2 * margin)
        y = size - margin - (p[1] - miny) / span * (size - 2 * margin)
        return int(x), int(y)

    lane_px = max(6, int(3.2 / span * (size - 2 * margin)))
    img = np.full((size, size, 3), 235, np.uint8)
    for s in shapes:
        for a, b in zip(s, s[1:]):
            cv2.line(img, px(a), px(b), (90, 90, 90), lane_px)
    state_str = tr.trafficlight.getRedYellowGreenState(tls_id)
    colours = {SignalState.RED: (0, 0, 230), SignalState.YELLOW: (0, 200, 255),
               SignalState.GREEN: (0, 180, 0)}
    for idx, group in enumerate(tr.trafficlight.getControlledLinks(tls_id)):
        if not group or idx >= len(state_str):
            continue
        shape = tr.lane.getShape(group[0][0])
        if shape:
            st = SignalState.from_sumo(state_str[idx])
            cv2.circle(img, px(shape[-1]), max(6, lane_px // 3), colours.get(st, (150, 150, 150)), -1)
    for vid in tr.vehicle.getIDList():
        pos = tr.vehicle.getPosition(vid)
        hit = vid == event["track_id"]
        cv2.circle(img, px(pos), max(9 if hit else 5, lane_px // (2 if hit else 3)), (255, 0, 255) if hit else (200, 120, 0), -1)
        if hit:
            cv2.putText(img, vid, (px(pos)[0] + 10, px(pos)[1] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 0, 255), 2, cv2.LINE_AA)
    from .evidence import banner
    return banner(img, [
        f"SUMO RED-LIGHT VIOLATION  vehicle={event['track_id']}",
        f"sim t={event['timestamp']:.1f}s  red for {event['time_into_red']:.1f}s  "
        f"approach={event['meta'].get('approach')}",
    ])
