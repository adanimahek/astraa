# Red-light violation test clip

* `red_light_test.mp4`: 30 s, 768×432, 12.5 fps, about 2.8 MB.
  * Source: Intel IoT DevKit sample videos, `car-detection.mp4`
    (https://github.com/intel-iot-devkit/sample-videos), licensed CC-BY-4.0.
  * It shows toy cars on a mat, filmed from above.
* `config.json`: the configuration to paste into **Violations → Uploaded video**.
  * Stop line: horizontal at 55 % of the frame height. Cars moving up are approaching it.
  * Signal timeline: green 0–10 s, yellow 10–13 s, red 13–31 s.

Expected result (checked with ASTRA_YOLO11s_FINAL_9833_best.pt, confidence 0.4):

* 2 stop-line crossings.
* About 6 s: a car crosses on **green**. It is not flagged.
* About 17.6 s: a red car crosses on **red**, 4.6 s into red. It is flagged as **1 violation**.
* The toy car has no readable Indian plate, so the violation goes to **Needs review**.
  To finish the flow, verify it there with a demo plate such as `KA01AB1234`. This
  requires the demo data to be seeded. The owner lookup then runs and an e-challan is
  issued to *Aarav Sharma (Demo)*. Log in as `owner1@example.com` / `owner123` to see it.
* Uploading the same clip again stores nothing: "1 duplicate skipped".
