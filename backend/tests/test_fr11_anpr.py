"""FR11 – number-plate recognition, normalisation and manual verification."""
import os

import cv2
import numpy as np
import pytest

from app.enforcement import plates
from app.enforcement.anpr import AnprService, join_lines


# --------------------------------------------------------------- plate format
@pytest.mark.parametrize("raw,expected,fixes", [
    ("KA 01 AB 1234", "KA01AB1234", 0),
    ("ka-01-ab-1234", "KA01AB1234", 0),
    ("KAO1AB1234", "KA01AB1234", 1),        # O read instead of 0
    ("KA01A81234", "KA01AB1234", 1),        # 8 read instead of B
    ("DL3CAB1234", "DL3CAB1234", 0),        # Delhi 1-digit RTO + 3-letter series
    ("MH12DE4321", "MH12DE4321", 0),
    ("22 BH 1234 AB", "22BH1234AB", 0),     # Bharat series
    ("TN09Z5678", "TN09Z5678", 0),
])
def test_normalize_valid(raw, expected, fixes):
    p = plates.normalize(raw)
    assert p is not None and p.number == expected and p.corrections == fixes


@pytest.mark.parametrize("raw", ["", "1234", "XX01AB1234", "KA01AB12345678", "HELLO WORLD", "KA01AB12"])
def test_normalize_invalid(raw):
    assert plates.normalize(raw) is None


def test_format_and_validity():
    assert plates.format_plate("ka01ab1234") == "KA 01 AB 1234"
    assert plates.is_valid("KA01AB1234") and not plates.is_valid("KAO1AB1234")


def test_join_lines_two_row_plate():
    rows = [("DE4321", 0.8, (10, 50, 100, 80)), ("MH12", 0.9, (20, 5, 80, 35))]
    text, conf = join_lines(rows)
    assert text == "MH12DE4321" and 0.8 < conf < 0.9


# ------------------------------------------------------------ service (fakes)
class FakeDetector:
    def __init__(self, boxes):
        self.boxes = boxes

    def detect(self, img):
        return self.boxes


class FakeOcr:
    def __init__(self, rows):
        self.rows = rows

    def read(self, img):
        return self.rows


IMG = np.zeros((120, 200, 3), np.uint8)


def svc(det_boxes, ocr_rows, thr=0.8):
    return AnprService(FakeDetector(det_boxes), FakeOcr(ocr_rows), min_confidence=thr)


def test_confident_valid_reading_auto_verified():
    r = svc([((10, 60, 150, 100), 0.9)], [("KA01AB1234", 0.95, (0, 0, 100, 20))]).recognize([IMG])
    assert r.auto_verified and r.best.number == "KA01AB1234" and r.review_reasons == []
    assert r.best.crop is not None and r.best.ocr_confidence == 0.95


def test_low_confidence_goes_to_review():
    r = svc([((10, 60, 150, 100), 0.9)], [("KA01AB1234", 0.55, (0, 0, 100, 20))]).recognize([IMG])
    assert not r.auto_verified and r.review_reasons == ["low_confidence"]


def test_corrections_reduce_confidence():
    r = svc([((10, 60, 150, 100), 0.9)], [("KAO1A81234", 0.85, (0, 0, 100, 20))]).recognize([IMG])
    assert r.best.number == "KA01AB1234" and r.best.corrections == 2
    assert r.best.confidence < 0.8 and not r.auto_verified


def test_invalid_format_goes_to_review():
    r = svc([((10, 60, 150, 100), 0.9)], [("HELLO", 0.99, (0, 0, 100, 20))]).recognize([IMG])
    assert not r.auto_verified and "invalid_indian_format" in r.review_reasons


def test_no_plate_detected_never_auto_verified():
    r = svc([], [("KA01AB1234", 0.99, (0, 0, 100, 20))]).recognize([IMG])
    assert not r.auto_verified and "plate_not_detected" in r.review_reasons
    assert r.best.number == "KA01AB1234"  # kept as a suggestion for the reviewer


def test_conflicting_readings_go_to_review():
    class SeqOcr:
        def __init__(self):
            self.n = 0

        def read(self, img):
            self.n += 1
            return [("KA01AB1234" if self.n == 1 else "KA01AB9999", 0.97, (0, 0, 100, 20))]

    s = AnprService(FakeDetector([((10, 60, 150, 100), 0.9)]), SeqOcr(), 0.8)
    r = s.recognize([IMG, IMG])
    assert "conflicting_readings" in r.review_reasons


# ---------------------------------------------------------- real ANPR models
def _plate_img(lines):
    h = 70 * len(lines) + 20
    img = np.full((h, 360, 3), 255, np.uint8)
    cv2.rectangle(img, (2, 2), (357, h - 3), (0, 0, 0), 3)
    for i, t in enumerate(lines):
        cv2.putText(img, t, (18, 68 + 70 * i), cv2.FONT_HERSHEY_DUPLEX, 1.6, (0, 0, 0), 3, cv2.LINE_AA)
    return img


def test_real_detector_and_easyocr():
    pytest.importorskip("easyocr")
    from app.enforcement.anpr import EasyOcrEngine, YoloPlateDetector
    from app.enforcement.config import enforcement_settings as es

    if not os.path.isfile(es.plate_detector_path):
        pytest.skip("plate detector weights not downloaded")
    ocr = EasyOcrEngine(gpu=False)
    whole = FakeDetector([((0, 0, 360, 90), 0.9)])
    r = AnprService(whole, ocr).recognize([_plate_img(["KA 01 AB 1234"])])
    assert r.best.number == "KA01AB1234"
    car = np.full((420, 560, 3), 90, np.uint8)
    cv2.rectangle(car, (60, 80), (500, 380), (30, 30, 160), -1)
    car[300:345, 190:370] = cv2.resize(_plate_img(["KA 05 MN 2024"]), (180, 45))
    boxes = YoloPlateDetector().detect(car)
    assert boxes, "pretrained plate detector found no plate"
    (x1, y1, x2, y2), conf = boxes[0]
    assert abs(x1 - 190) < 25 and abs(y1 - 300) < 25 and conf > 0.3


# -------------------------------------------------------- pipeline + API
from tests.test_fr10_red_light import FakeTracker, VIDEO_CFG, _make_video  # noqa: E402


@pytest.fixture
def fake_anpr(monkeypatch):
    from app.enforcement import anpr

    def install(rows, boxes=((10, 10, 60, 30), 0.9)):
        monkeypatch.setattr(anpr, "_service", svc([boxes] if boxes else [], rows))
    return install


def upload_video(client, headers, tmp_path, monkeypatch, vehicles=None):
    import json
    from app.enforcement import video

    vpath = str(tmp_path / "clip.avi")
    _make_video(vpath)
    monkeypatch.setattr(video, "_default_model_factory",
                        lambda: FakeTracker(vehicles or {2: (80, 120)}))
    with open(vpath, "rb") as fh:
        r = client.post("/api/violations/detect/video", headers=headers,
                        files={"file": ("clip.avi", fh, "video/x-msvideo")},
                        data={"config": json.dumps(VIDEO_CFG)})
    assert r.status_code == 200, r.text
    return r.json()["violations"]


def test_pipeline_auto_verified(client, operator_headers, tmp_path, monkeypatch, fake_anpr):
    fake_anpr([("KA01AB1234", 0.97, (0, 0, 50, 20))])
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    assert v["status"] not in ("pending_review", "detected")  # later stages may advance it
    assert any(h["action"] == "plate_auto_verified" for h in v["history"])
    p = v["plate"]
    assert p["number"] == "KA01AB1234" and p["source"] == "anpr" and p["verified"]
    assert p["ocr_confidence"] == 0.97 and v["evidence"]["plate_crops"]
    r = client.get(f"/api/violations/{v['violation_id']}/evidence/plate_crops?index=0",
                   headers=operator_headers)
    assert r.status_code == 200


def test_manual_review_flow(client, operator_headers, tmp_path, monkeypatch, fake_anpr):
    fake_anpr([("KA01AB1Z34", 0.5, (0, 0, 50, 20))])
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    vid = v["violation_id"]
    assert v["status"] == "pending_review" and v["plate"]["review_reasons"]
    q = client.get("/api/violations/review/queue", headers=operator_headers).json()
    assert [i["violation_id"] for i in q["items"]] == [vid]

    bad = client.post(f"/api/violations/{vid}/verify-plate", headers=operator_headers,
                      json={"plate_number": "NOTAPLATE"})
    assert bad.status_code == 422
    ok = client.post(f"/api/violations/{vid}/verify-plate", headers=operator_headers,
                     json={"plate_number": "ka 01 ab 1234", "note": "checked evidence"})
    assert ok.status_code == 200, ok.text
    data = ok.json()
    assert data["plate"]["number"] == "KA01AB1234" and data["plate"]["source"] == "manual"
    assert data["plate"]["verified_by"] == "operator@test.local"
    assert data["plate"]["anpr_number"] == "KA01AB1234" or data["plate"]["raw_text"]
    assert any(h["action"] == "plate_verified_manually" for h in data["history"])


def test_reject_and_status_conflict(client, operator_headers, tmp_path, monkeypatch, fake_anpr):
    fake_anpr([], boxes=None)
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    vid = v["violation_id"]
    assert v["status"] == "pending_review"
    assert "plate_not_detected" in v["plate"]["review_reasons"]
    r = client.post(f"/api/violations/{vid}/reject", headers=operator_headers,
                    json={"reason": "Ambulance with siren on"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    r = client.post(f"/api/violations/{vid}/verify-plate", headers=operator_headers,
                    json={"plate_number": "KA01AB1234"})
    assert r.status_code == 409


def test_anpr_failure_routes_to_review(client, operator_headers, tmp_path, monkeypatch):
    from app.enforcement import anpr

    class Broken:
        def recognize(self, images):
            raise anpr.AnprUnavailable("weights missing")

    monkeypatch.setattr(anpr, "_service", Broken())
    v = upload_video(client, operator_headers, tmp_path, monkeypatch)[0]
    assert v["status"] == "pending_review"
    assert v["plate"]["review_reasons"][0].startswith("anpr_unavailable")


def test_simulated_plate_is_deterministic_and_valid():
    from app.enforcement.pipeline import simulated_plate

    a = simulated_plate("north_flow.3", "sumo-seed1")
    assert a == simulated_plate("north_flow.3", "sumo-seed1")
    assert plates.is_valid(a)
