"""Traffic-signal state handling.

The key safety property: **a state that is not explicitly known is UNKNOWN,
never RED.**  Rules must treat UNKNOWN as "cannot enforce".
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence


class SignalState(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value) -> "SignalState":
        if isinstance(value, SignalState):
            return value
        text = str(value or "").strip().lower()
        aliases = {"r": "red", "amber": "yellow", "y": "yellow", "g": "green"}
        text = aliases.get(text, text)
        try:
            return cls(text)
        except ValueError:
            return cls.UNKNOWN

    @classmethod
    def from_sumo(cls, char: str) -> "SignalState":
        """Map one character of a SUMO ``getRedYellowGreenState`` string."""
        if char in ("r",):
            return cls.RED
        if char in ("y", "Y", "u"):  # u = red+yellow (pre-green)
            return cls.YELLOW
        if char in ("G", "g", "s"):
            return cls.GREEN
        # 'o' / 'O' = signal off, anything else is not enforceable.
        return cls.UNKNOWN


@dataclass(frozen=True)
class SignalInterval:
    start: float
    end: float
    state: SignalState


class SignalTimeline:
    """Piece-wise constant signal state over media time (seconds).

    Any instant not covered by an interval returns ``UNKNOWN``.
    """

    def __init__(self, intervals: Sequence[SignalInterval]):
        ordered = sorted(intervals, key=lambda i: i.start)
        for item in ordered:
            if item.end <= item.start:
                raise ValueError(f"Signal interval end must be after start: {item}")
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt.start < prev.end:
                raise ValueError(
                    f"Signal intervals overlap: {prev.start}-{prev.end} and {nxt.start}-{nxt.end}"
                )
        self.intervals: List[SignalInterval] = list(ordered)

    def state_at(self, t: float) -> SignalState:
        for item in self.intervals:
            if item.start <= t < item.end:
                return item.state
        return SignalState.UNKNOWN

    # ---- construction helpers -------------------------------------------------
    @classmethod
    def from_config(cls, cfg: Optional[dict]) -> "SignalTimeline":
        """Build a timeline from the JSON config accepted by the video endpoint.

        Supported shapes::

            {"mode": "timeline", "intervals": [{"start": 0, "end": 12, "state": "green"}, ...]}
            {"mode": "cycle", "start": 0, "end": 120,
             "phases": [{"state": "green", "duration": 30}, {"state": "yellow", "duration": 3},
                        {"state": "red", "duration": 27}]}
            {"mode": "fixed", "state": "red", "start": 0, "end": 60}
            {"mode": "unknown"}           # or a missing config

        ``end`` may be omitted for ``cycle``/``fixed`` (then it extends to
        ``max_duration`` seconds, default 24h).
        """
        if not cfg:
            return cls([])
        mode = str(cfg.get("mode", "timeline")).lower()
        if mode == "unknown":
            return cls([])
        if mode == "timeline":
            items = cfg.get("intervals") or []
            return cls([
                SignalInterval(float(i["start"]), float(i["end"]), _strict_state(i["state"]))
                for i in items
            ])
        start = float(cfg.get("start", 0.0))
        end = cfg.get("end")
        end = float(end) if end is not None else start + float(cfg.get("max_duration", 86400))
        if end <= start:
            raise ValueError("Signal config end must be after start")
        if mode == "fixed":
            return cls([SignalInterval(start, end, _strict_state(cfg["state"]))])
        if mode == "cycle":
            phases = cfg.get("phases") or []
            if not phases:
                raise ValueError("Cycle signal config needs at least one phase")
            parsed = [(_strict_state(p["state"]), float(p["duration"])) for p in phases]
            if any(d <= 0 for _, d in parsed):
                raise ValueError("Cycle phase durations must be positive")
            intervals, t, idx = [], start, 0
            while t < end:
                state, dur = parsed[idx % len(parsed)]
                intervals.append(SignalInterval(t, min(t + dur, end), state))
                t += dur
                idx += 1
            return cls(intervals)
        raise ValueError(f"Unknown signal mode {mode!r}")


def _strict_state(value) -> SignalState:
    state = SignalState.parse(value)
    if state is SignalState.UNKNOWN and str(value).strip().lower() != "unknown":
        raise ValueError(f"Invalid signal state {value!r}; use red, yellow, green or unknown")
    return state


def describe(timelines: Dict[str, SignalTimeline]) -> Dict[str, list]:
    return {
        name: [{"start": i.start, "end": i.end, "state": i.state.value} for i in tl.intervals]
        for name, tl in timelines.items()
    }
