from pathlib import Path
from ultralytics import YOLO
import shutil

# ============================================================
# ASTRA - Fire Truck Dataset Audit
# ============================================================

DATASET = Path(r"D:\ASTRA\dataset\firetruck_processed")
MODEL_PATH = r"D:\ASTRA\training\ASTRA_YOLO11s_5plus50_best.pt"

OUTPUT = DATASET / "audit"

FLAGGED = OUTPUT / "flagged_other_vehicles"
CLEAN = OUTPUT / "clean_firetruck"

FLAGGED.mkdir(parents=True, exist_ok=True)
CLEAN.mkdir(parents=True, exist_ok=True)

model = YOLO(MODEL_PATH)

# ASTRA classes
CLASS_NAMES = {
    0: "Car",
    1: "Bus",
    2: "Truck",
    3: "2-Wheeler",
    4: "3-Wheeler",
    5: "Tempo/Van",
    6: "Bicycle",
    7: "Other",
    8: "Ambulance",
    9: "Fire Truck"
}

# Classes that we want to flag
OTHER_CLASSES = set(range(0, 9))

images = list(
    (DATASET / "images" / "train").glob("*")
)

images += list(
    (DATASET / "images" / "val").glob("*")
)

print()
print("==========================================")
print("ASTRA FIRE TRUCK DATASET AUDIT")
print("==========================================")
print()

print("Images to audit:", len(images))
print()

clean_count = 0
flagged_count = 0

for index, image_path in enumerate(images, start=1):

    results = model.predict(
        source=str(image_path),
        imgsz=640,
        conf=0.25,
        device=0,
        verbose=False
    )

    detected_other = set()

    for result in results:

        if result.boxes is None:
            continue

        for cls in result.boxes.cls.tolist():

            class_id = int(cls)

            if class_id in OTHER_CLASSES:
                detected_other.add(class_id)

    if detected_other:

        destination = FLAGGED / image_path.name
        shutil.copy2(image_path, destination)

        flagged_count += 1

    else:

        destination = CLEAN / image_path.name
        shutil.copy2(image_path, destination)

        clean_count += 1

    if index % 50 == 0:
        print(
            f"Processed {index}/{len(images)} | "
            f"Clean: {clean_count} | "
            f"Flagged: {flagged_count}"
        )


print()
print("==========================================")
print("AUDIT COMPLETE")
print("==========================================")
print()

print("Total images:", len(images))
print("Potentially clean:", clean_count)
print("Needs manual review:", flagged_count)

print()
print("Clean folder:")
print(CLEAN)

print()
print("Flagged folder:")
print(FLAGGED)

print()
print("IMPORTANT:")
print("This is only an automatic screening.")
print("It does NOT prove that unflagged images contain no other vehicles.")