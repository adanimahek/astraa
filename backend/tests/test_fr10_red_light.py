"""FR10 – red-light violation detection (rule, signal config, video, SUMO, API)."""
import json
import os

import cv2
import numpy as np
import pytest

from app.enforcement.red_light import RedLightRule, Side, TrackObservation
from app.enforcement.signal import SignalState, SignalTimeline

R, Y, G, U = SignalState.RED, SignalState.YELLOW, SignalState.GREEN, SignalState.UNKNOWN


def obs(tid, t, side, state, lane="n", bbox=None, cls="Car"):
    return TrackObservation(tid, t, Side(side), state, lane, cls, 0.9, bbox)


# --------------------------------------------------------------------- signal
def test_timeline_gaps_and_outside_are_unknown():
    tl = SignalTimeline.from_config({"mode": "timeline", "intervals": [
        {"start": 0, "end": 10, "state": "green"}, {"start": 12, "end": 20, "state": "red"}]})
    assert tl.state_at(5) is G
    assert tl.state_at(11) is U          # gap is never assumed red
    assert tl.state_at(15) is R
    assert tl.state_at(25) is U          # after the configured range
    assert tl.state_at(-1) is U


def test_cycle_and_fixed_and_missing():
    tl = SignalTimeline.from_config({"mode": "cycle", "start": 0, "end": 70, "phases": [
        {"state": "green", "duration": 30}, {"state": "yellow", "duration": 5},
        {"state": "red", "duration": 30}]})
    assert [tl.state_at(t) for t in (0, 31, 40, 66, 71)] == [G, Y, R, G, U]
    assert SignalTimeline.from_config({"mode": "fixed", "state": "red", "end": 5}).state_at(3) is R
    assert SignalTimeline.from_config(None).state_at(3) is U
    assert SignalTimeline.from_config({"mode": "unknown"}).state_at(3) is U


@pytest.mark.parametrize("bad", [
    {"mode": "timeline", "intervals": [{"start": 0, "end": 10, "state": "green"},
                                       {"start": 5, "end": 12, "state": "red"}]},
    {"mode": "timeline", "intervals": [{"start": 0, "end": 10, "state": "purple"}]},
    {"mode": "cycle", "phases": []},
    {"mode": "blink"},
])
def test_invalid_signal_config(bad):
    with pytest.raises(ValueError):
        SignalTimeline.from_config(bad)


def test_sumo_state_mapping():
    assert [SignalState.from_sumo(c) for c in "rGgyYuoO"] == [R, G, G, Y, Y, Y, U, U]


# ----------------------------------------------------------------------- rule
def test_crossing_on_red_is_violation():
    rule = RedLightRule(grace_seconds=0.5)
    rule.update_signal("n", 0.0, R)
    assert rule.observe(obs("1", 1.0, "before", R)) is None
    ev = rule.observe(obs("1", 1.2, "after", R))
    assert ev and ev.track_id == "1" and ev.time_into_red == pytest.approx(1.2)


def test_entered_before_red_not_flagged():
    rule = RedLightRule(grace_seconds=0.0)
    # crossed on green, then light turned red while vehicle inside the junction
    rule.observe(obs("a", 0.0, "before", G))
    assert rule.observe(obs("a", 0.5, "after", G)) is None
    assert rule.observe(obs("a", 1.0, "after", R)) is None
    # crossing straddles yellow -> red between samples: benefit of doubt
    rule.observe(obs("b", 2.0, "before", Y))
    assert rule.observe(obs("b", 2.5, "after", R)) is None
    # first seen already past the stop line during red
    assert rule.observe(obs("c", 3.0, "after", R)) is None
    assert rule.stats["violations"] == 0


def test_unknown_signal_never_red():
    rule = RedLightRule(grace_seconds=0.0)
    rule.observe(obs("1", 0.0, "before", U))
    assert rule.observe(obs("1", 0.5, "after", U)) is None
    rule.observe(obs("2", 1.0, "before", R))
    assert rule.observe(obs("2", 1.5, "after", U)) is None
    assert rule.stats["skipped_unknown_signal"] == 2


def test_grace_period():
    rule = RedLightRule(grace_seconds=1.0)
    rule.update_signal("n", 10.0, R)
    rule.observe(obs("1", 10.4, "before", R))
    assert rule.observe(obs("1", 10.6, "after", R)) is None
    assert rule.stats["skipped_grace"] == 1
    rule.observe(obs("2", 11.2, "before", R))
    assert rule.observe(obs("2", 11.4, "after", R)) is not None


def test_no_duplicates_same_track_or_id_switch():
    rule = RedLightRule(grace_seconds=0.0, duplicate_window_seconds=2.0)
    rule.update_signal("n", 0, R)
    rule.observe(obs("1", 1.0, "before", R, bbox=(0, 0, 10, 10)))
    assert rule.observe(obs("1", 1.2, "after", R, bbox=(0, 2, 10, 12)))
    # jitter back and forth across the line
    rule.observe(obs("1", 1.4, "before", R, bbox=(0, 0, 10, 10)))
    assert rule.observe(obs("1", 1.6, "after", R, bbox=(0, 2, 10, 12))) is None
    # tracker re-assigns a new ID to the same vehicle
    rule.observe(obs("9", 1.7, "before", R, bbox=(0, 1, 10, 11)))
    assert rule.observe(obs("9", 1.8, "after", R, bbox=(0, 3, 10, 13))) is None
    assert rule.stats["violations"] == 1 and rule.stats["suppressed_duplicates"] == 1


def test_exempt_emergency_vehicle():
    rule = RedLightRule(grace_seconds=0.0, exempt_classes=["Ambulance"])
    rule.update_signal("n", 0, R)
    rule.observe(obs("1", 1.0, "before", R, cls="Ambulance"))
    assert rule.observe(obs("1", 1.5, "after", R, cls="Ambulance")) is None
    assert rule.stats["skipped_exempt"] == 1


# ---------------------------------------------------------------------- video
class _T:
    def __init__(self, data):
        self._d = data

    def tolist(self):
        return list(self._d)


class _Boxes:
    def __init__(self, rows):
        self.id = _T([r[0] for r in rows]) if rows else None
        self.xyxy = _T([r[1] for r in rows])
        self.cls = _T([0] * len(rows))
        self.conf = _T([0.9] * len(rows))


class _Res:
    names = {0: "Car"}

    def __init__(self, rows):
        self.boxes = _Boxes(rows)


class FakeTracker:
    """Scripted tracker: vehicles move down the frame at fixed speed (pixels/frame)."""

    def __init__(self, vehicles):
        self.vehicles = vehicles  # tid -> (start_frame, x)
        self.frame = 0

    def track(self, frame, **kw):
        rows = []
        for tid, (start, x) in self.vehicles.items():
            k = self.frame - start
            if 0 <= k < 30:
                y2 = 20 + k * 6  # bottom edge; stop line at y=120 -> crosses near k=17
                rows.append((tid, [x, y2 - 30, x + 40, y2]))
        self.frame += 1
        return [_Res(rows)]


def _make_video(path, frames=200, fps=10):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
    for i in range(frames):
        img = np.full((240, 320, 3), 40, np.uint8)
        cv2.putText(img, str(i), (5, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        writer.write(img)
    writer.release()


VIDEO_CFG = {
    "coordinates": "pixels",
    "zones": [{"name": "north", "stop_line": [[0, 120], [320, 120]], "before_point": [160, 0],
               "margin": 2,
               "signal": {"mode": "timeline", "intervals": [
                   {"start": 0, "end": 5, "state": "green"},
                   {"start": 5, "end": 6, "state": "yellow"},
                   {"start": 6, "end": 15, "state": "red"}]}}],  # >15 s: UNKNOWN
}


def test_video_pipeline_flags_only_red_crossings(tmp_path, evidence_dir):
    from app.enforcement.evidence import EvidenceStore
    from app.enforcement.video import detect_red_light_video

    video = str(tmp_path / "clip.avi")
    _make_video(video)
    # 1: crosses ~1.7 s (green); 2: crosses ~9.7 s (red); 3: crosses ~17.7 s (unknown)
    tracker = FakeTracker({1: (0, 20), 2: (80, 120), 3: (160, 220)})
    store = EvidenceStore(evidence_dir)
    out = detect_red_light_video(video, VIDEO_CFG, analyse_fps=10,
                                 model_factory=lambda: tracker, evidence=store)
    assert [e["track_id"] for e in out["events"]] == ["2"]
    ev = out["events"][0]
    assert ev["lane"] == "north" and ev["signal_state"] == "red"
    assert 9.0 < ev["timestamp"] < 10.5
    assert store.resolve(ev["evidence"]["scene"]) is not None
    assert store.resolve(ev["evidence"]["pre_crossing"]) is not None
    assert len(ev["evidence"]["vehicle_crops"]) == 2
    assert out["rule_stats"]["skipped_not_red"] == 1
    assert out["rule_stats"]["skipped_unknown_signal"] == 1
    assert out["unknown_signal_frames"] > 0


def test_video_config_validation():
    from app.enforcement.video import parse_video_config

    with pytest.raises(ValueError):
        parse_video_config({"zones": []}, 100, 100)
    with pytest.raises(ValueError):
        parse_video_config({"zones": [{"stop_line": [[0, 0.5], [0, 0.5]]}]}, 100, 100)
    with pytest.raises(ValueError):
        parse_video_config({"zones": [{"stop_line": [[0, 0.5], [1, 0.5]],
                                       "before_point": [0.3, 0.5]}]}, 100, 100)
    cfg = parse_video_config({"zones": [{"stop_line": [[0, 0.5], [1, 0.5]]}]}, 200, 100)
    z = cfg.zones[0]
    assert z.side((100, 90)) is Side.BEFORE and z.side((100, 10)) is Side.AFTER
    assert z.side((100, 50)) is None  # dead-band
    assert z.timeline.state_at(1) is U


def test_real_yolo_tracker_smoke(tmp_path, evidence_dir):
    """Exercises the real ASTRA weights + ByteTrack path (no vehicles in frames)."""
    from app.config import settings
    from app.enforcement.evidence import EvidenceStore
    from app.enforcement.video import detect_red_light_video

    if not os.path.isfile(settings.model_path):
        pytest.skip("ASTRA YOLO weights not present")
    video = str(tmp_path / "blank.avi")
    _make_video(video, frames=12, fps=10)
    out = detect_red_light_video(video, VIDEO_CFG, analyse_fps=10,
                                 evidence=EvidenceStore(evidence_dir))
    assert out["video"]["frames_analysed"] == 12 and out["events"] == []


# ----------------------------------------------------------------------- SUMO
class FakeTraci:
    """Minimal TraCI stand-in: one approach lane feeding link 0 of TLS 'center'."""

    def __init__(self):
        self.t = 0.0
        self.tls = "r"
        self.veh = {}  # vid -> lane
        outer = self

        class _TL:
            def getControlledLinks(self, tls):
                return [[("north_in_0", "south_out_0", ":center_1_0")]]

            def getRedYellowGreenState(self, tls):
                return outer.tls

        class _Sim:
            def getTime(self):
                return outer.t

        class _Veh:
            def getIDList(self):
                return list(outer.veh)

            def getLaneID(self, v):
                return outer.veh[v]

            def getNextTLS(self, v):
                return [("center", 0, 5.0, outer.tls)] if outer.veh[v] == "north_in_0" else []

            def getTypeID(self, v):
                return "passenger"

            def getPosition(self, v):
                return (295.0, 320.0)

            def getSpeed(self, v):
                return 12.0

        self.trafficlight, self.simulation, self.vehicle = _TL(), _Sim(), _Veh()


def test_sumo_monitor():
    from app.enforcement.sumo import SumoRedLightMonitor

    tr = FakeTraci()
    mon = SumoRedLightMonitor(tr, "center", RedLightRule(grace_seconds=0.0))
    # t=0 green: 'early' approaching; t=1 crosses on green, then light goes red
    tr.tls, tr.veh = "G", {"early": "north_in_0"}
    mon.step()
    tr.t, tr.veh = 1.0, {"early": ":center_1_0"}
    mon.step()
    tr.t, tr.tls = 2.0, "r"
    tr.veh = {"early": ":center_1_0", "runner": "north_in_0", "inside": ":center_1_0"}
    mon.step()
    tr.t, tr.veh = 3.0, {"runner": ":center_1_0", "inside": "south_out_0"}
    events = mon.step()
    assert [e["track_id"] for e in events] == ["runner"]
    assert events[0]["meta"]["approach"] == "north"
    assert [e["track_id"] for e in mon.events] == ["runner"]


# ------------------------------------------------------------------------ API
def test_video_api_stores_and_dedupes(client, operator_headers, tmp_path, monkeypatch):
    from app.enforcement import video

    vpath = str(tmp_path / "clip.avi")
    _make_video(vpath)
    monkeypatch.setattr(video, "_default_model_factory",
                        lambda: FakeTracker({1: (0, 20), 2: (80, 120), 3: (160, 220)}))

    def upload():
        with open(vpath, "rb") as fh:
            return client.post("/api/violations/detect/video", headers=operator_headers,
                               files={"file": ("clip.avi", fh, "video/x-msvideo")},
                               data={"config": json.dumps(VIDEO_CFG)})

    r = upload()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["violations_stored"] == 1 and body["duplicates_skipped"] == 0
    vid = body["violations"][0]["violation_id"]
    assert body["violations"][0]["occurred_at_basis"] == "upload_time"

    r2 = upload()  # same file again -> no duplicate violation
    assert r2.json()["violations_stored"] == 0 and r2.json()["duplicates_skipped"] == 1

    lst = client.get("/api/violations", headers=operator_headers).json()
    assert lst["total"] == 1
    img = client.get(f"/api/violations/{vid}/evidence/scene", headers=operator_headers)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/violations/{vid}/evidence/scene").status_code == 401
    assert client.get(f"/api/violations/{vid}/evidence/../../x",
                      headers=operator_headers).status_code == 404


def test_video_api_rejects_bad_config(client, operator_headers, tmp_path):
    vpath = str(tmp_path / "clip.avi")
    _make_video(vpath, frames=3)
    with open(vpath, "rb") as fh:
        r = client.post("/api/violations/detect/video", headers=operator_headers,
                        files={"file": ("clip.avi", fh, "video/x-msvideo")},
                        data={"config": json.dumps({"zones": []})})
    assert r.status_code == 400


def test_sumo_api_end_to_end(client, operator_headers):
    """Runs the real SUMO script through the API (skipped if SUMO/traci are absent)."""
    import shutil
    pytest.importorskip("traci")
    if not shutil.which("sumo"):
        pytest.skip("sumo binary not on PATH")
    body = {"seed": 101, "duration_seconds": 600, "violation_probability": 0.15}
    r = client.post("/api/violations/detect/sumo", headers=operator_headers, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["violations_stored"] >= 1
    v = data["violations"][0]
    assert v["source"]["kind"] == "sumo" and v["evidence"]["scene_zoom"]
    r2 = client.post("/api/violations/detect/sumo", headers=operator_headers, json=body)
    assert r2.json()["violations_stored"] == 0          # same run -> no duplicates
    assert r2.json()["duplicates_skipped"] == data["violations_stored"]
