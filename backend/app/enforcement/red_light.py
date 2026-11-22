"""Source-agnostic red-light violation rule.

Adapters (uploaded video, SUMO/TraCI, future live cameras) convert their data
into :class:`TrackObservation` objects – one per tracked vehicle per time step –
and feed them to :class:`RedLightRule`.  The rule only knows about:

* a stable tracking ID,
* which side of the stop line the vehicle is on (``BEFORE`` / ``AFTER``),
* the signal state controlling that vehicle at that instant.

A violation is raised when a vehicle moves from BEFORE to AFTER the stop line
**and** the signal was RED both at the last observation before the line and at
the first observation after it, and the vehicle was still behind the line at
least ``grace_seconds`` after red was first observed.  Consequences:

* vehicles that crossed while green/yellow (entered before red) are never flagged;
* a crossing that straddles a yellow→red change between samples is not flagged;
* UNKNOWN signal state is never treated as red;
* vehicles first seen already past the line are never flagged;
* each track is flagged at most once, and near-identical events from a
  re-assigned tracking ID are suppressed.

This module has no third-party dependencies.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .signal import SignalState

VIOLATION_TYPE = "red_light"
BBox = Tuple[float, float, float, float]


class Side(str, Enum):
    BEFORE = "before"
    AFTER = "after"


@dataclass
class TrackObservation:
    track_id: str
    timestamp: float
    side: Side
    signal_state: SignalState
    lane: str = "default"
    vehicle_class: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[BBox] = None
    position: Optional[Tuple[float, float]] = None
    meta: dict = field(default_factory=dict)


@dataclass
class ViolationEvent:
    track_id: str
    lane: str
    timestamp: float
    previous_timestamp: float
    red_started_at: float
    time_into_red: float
    vehicle_class: Optional[str]
    confidence: Optional[float]
    bbox: Optional[BBox]
    position: Optional[Tuple[float, float]]
    meta: dict
    violation_type: str = VIOLATION_TYPE
    signal_state: str = SignalState.RED.value

    @property
    def event_key(self) -> str:
        return f"{self.violation_type}:{self.lane}:{self.track_id}"

    def to_dict(self) -> dict:
        return {
            "violation_type": self.violation_type,
            "event_key": self.event_key,
            "track_id": self.track_id,
            "lane": self.lane,
            "timestamp": round(self.timestamp, 3),
            "previous_timestamp": round(self.previous_timestamp, 3),
            "red_started_at": round(self.red_started_at, 3),
            "time_into_red": round(self.time_into_red, 3),
            "signal_state": self.signal_state,
            "vehicle_class": self.vehicle_class,
            "confidence": self.confidence,
            "bbox": list(self.bbox) if self.bbox else None,
            "position": list(self.position) if self.position else None,
            "meta": dict(self.meta),
        }


@dataclass
class _TrackState:
    side: Side
    timestamp: float
    signal_state: SignalState
    red_started_at: Optional[float]


def iou(a: Optional[Sequence[float]], b: Optional[Sequence[float]]) -> float:
    if not a or not b:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class RedLightRule:
    def __init__(
        self,
        grace_seconds: float = 0.5,
        exempt_classes: Iterable[str] = (),
        duplicate_window_seconds: float = 2.0,
        duplicate_iou: float = 0.3,
        stale_track_seconds: float = 30.0,
    ):
        if grace_seconds < 0:
            raise ValueError("grace_seconds cannot be negative")
        self.grace_seconds = grace_seconds
        self.exempt_classes = {c.lower() for c in exempt_classes}
        self.duplicate_window_seconds = duplicate_window_seconds
        self.duplicate_iou = duplicate_iou
        self.stale_track_seconds = stale_track_seconds
        self._red_since: Dict[str, float] = {}
        self._tracks: Dict[Tuple[str, str], _TrackState] = {}
        self._flagged: set = set()
        self._recent: List[ViolationEvent] = []
        self.stats = {"observations": 0, "crossings": 0, "violations": 0,
                      "skipped_unknown_signal": 0, "skipped_not_red": 0,
                      "skipped_grace": 0, "skipped_exempt": 0, "suppressed_duplicates": 0}

    # ------------------------------------------------------------------ signal
    def update_signal(self, lane: str, timestamp: float, state: SignalState) -> None:
        """Record the signal state for ``lane`` (call every step, even without vehicles)."""
        if state is SignalState.RED:
            self._red_since.setdefault(lane, timestamp)
        else:
            self._red_since.pop(lane, None)

    def red_since(self, lane: str) -> Optional[float]:
        return self._red_since.get(lane)

    # ------------------------------------------------------------- observation
    def observe(self, obs: TrackObservation) -> Optional[ViolationEvent]:
        self.stats["observations"] += 1
        self.update_signal(obs.lane, obs.timestamp, obs.signal_state)
        key = (obs.lane, obs.track_id)
        prev = self._tracks.get(key)
        self._tracks[key] = _TrackState(obs.side, obs.timestamp, obs.signal_state,
                                        self._red_since.get(obs.lane))
        if prev is None or key in self._flagged:
            return None
        if not (prev.side is Side.BEFORE and obs.side is Side.AFTER):
            return None
        self.stats["crossings"] += 1

        if SignalState.UNKNOWN in (prev.signal_state, obs.signal_state):
            self.stats["skipped_unknown_signal"] += 1
            return None
        if prev.signal_state is not SignalState.RED or obs.signal_state is not SignalState.RED:
            self.stats["skipped_not_red"] += 1  # vehicle entered before red
            return None
        red_start = prev.red_started_at
        if red_start is None:  # should not happen – prev was RED
            self.stats["skipped_unknown_signal"] += 1
            return None
        # Conservative: red_start is the *first observed* red instant, which is
        # never earlier than the true onset.
        if prev.timestamp - red_start < self.grace_seconds:
            self.stats["skipped_grace"] += 1
            return None
        if obs.vehicle_class and obs.vehicle_class.lower() in self.exempt_classes:
            self.stats["skipped_exempt"] += 1
            self._flagged.add(key)
            return None

        event = ViolationEvent(
            track_id=obs.track_id, lane=obs.lane, timestamp=obs.timestamp,
            previous_timestamp=prev.timestamp, red_started_at=red_start,
            time_into_red=obs.timestamp - red_start, vehicle_class=obs.vehicle_class,
            confidence=obs.confidence, bbox=obs.bbox, position=obs.position, meta=dict(obs.meta),
        )
        self._flagged.add(key)
        if self._is_duplicate(event):
            self.stats["suppressed_duplicates"] += 1
            return None
        self._recent.append(event)
        self.stats["violations"] += 1
        return event

    def _is_duplicate(self, event: ViolationEvent) -> bool:
        """Suppress a second event for the same physical vehicle (tracker ID switch)."""
        self._recent = [e for e in self._recent
                        if event.timestamp - e.timestamp <= self.duplicate_window_seconds]
        for other in self._recent:
            if other.lane != event.lane:
                continue
            if event.bbox and other.bbox and iou(event.bbox, other.bbox) >= self.duplicate_iou:
                return True
        return False

    def forget_stale(self, now: float) -> None:
        """Drop per-track memory for tracks not seen recently (bounded memory)."""
        stale = [k for k, s in self._tracks.items() if now - s.timestamp > self.stale_track_seconds]
        for k in stale:
            del self._tracks[k]
            self._flagged.discard(k)

    def is_flagged(self, lane: str, track_id: str) -> bool:
        return (lane, track_id) in self._flagged
