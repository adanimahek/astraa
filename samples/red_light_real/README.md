# Red-light violation demo clip with a visible signal and a demo plate

* `red_light_real.mp4`: 16.9 s, 1536×864, 12.5 fps, about 3.5 MB (MPEG-4 Part 2).
  It plays in VLC. Some browsers will not preview it, but uploading works.
* `config.json`: paste this into **Violations → Uploaded video**.

What is real and what is composited:

* **Real camera footage:** Intel IoT DevKit sample video `car-detection.mp4`
  (https://github.com/intel-iot-devkit/sample-videos, CC-BY-4.0). It shows model
  cars filmed from above.
* **Composited by ASTRA for the demo:**
  * The traffic light and the "SIGNAL" label. Its timing matches `config.json`:
    green 0–8 s, yellow 8–10.5 s, red from 10.5 s.
  * The painted stop line.
  * The CCTV caption.
  * Two fictional demo plates, tracked onto each car at the position where the
    pretrained plate detector finds the car's real plate:
    * `TN09BX4521` on the first car, which passes during green.
    * `KA01AB1234` on the red car, which jumps the red light.

Both plates exist only in ASTRA's synthetic demo registry, which you can seed
from the E-Challans page. ASTRA reads the signal state from `config.json`; the
light drawn in the video is for people watching, not for the detector.

Verified result (2026-11-22, model ASTRA_YOLO11s_5plus50_best.pt, confidence 0.4,
demo data seeded):

* 1 violation at 14.4 s (09:30:14 IST), 3.8 s after the light turned red, class Car.
* ANPR read `KA01AB1234` with OCR confidence 0.998, so it was auto-verified with no
  manual review.
* The owner lookup matched *Aarav Sharma (Demo)*, owner1.
* Challan issued automatically: ₹1,000, unpaid, due in 30 days.
* `owner1@example.com` / `owner123` sees the challan, the evidence and the Pay button.
* Uploading the same clip again gives "0 stored, 1 duplicate skipped".
