from pathlib import Path
from collections import Counter
import random
import shutil
import hashlib

# ============================================================
# ASTRA - CORRECTED EMERGENCY DATASET
# 875 Ambulance + ALL 125 Fire Truck images
# Keeps normal vehicles inside those images
# ============================================================

SOURCE = Path(r"D:\ASTRA\dataset\emergency_raw\extracted")
OUTPUT = Path(r"D:\ASTRA\dataset\emergency_corrected")

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# Original Roboflow classes -> ASTRA classes
#
# ASTRA:
# 0 Car
# 1 Bus
# 2 Truck
# 3 2-Wheeler
# 4 3-Wheeler
# 5 Tempo/Van
# 6 Bicycle
# 7 Other
# 8 Ambulance
# 9 Fire Truck

CLASS_MAPPING = {
    2: 8,    # ambulance -> Ambulance
    7: 4,    # auto -> 3-Wheeler
    8: 3,    # bike -> 2-Wheeler
    9: 1,    # bus -> Bus
    10: 0,   # car -> Car
    11: 9,   # fire_truck -> Fire Truck
    21: 5,   # tempo traveller -> Tempo/Van
    22: 2,   # truck -> Truck
}

# Classes we want to keep
KEEP_CLASSES = set(CLASS_MAPPING.keys())

N_AMBULANCE = 875
ALL_FIRE_TRUCK = True

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# ------------------------------------------------------------
# Find all source images and labels
# ------------------------------------------------------------

records = []

for split in ["train", "valid", "test"]:

    image_dir = SOURCE / split / "images"
    label_dir = SOURCE / split / "labels"

    if not image_dir.exists() or not label_dir.exists():
        continue

    for image_path in image_dir.iterdir():

        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        label_path = label_dir / f"{image_path.stem}.txt"

        if not label_path.exists():
            continue

        classes_found = set()

        with open(label_path, "r", encoding="utf-8") as f:

            for line in f:
                parts = line.strip().split()

                if not parts:
                    continue

                try:
                    class_id = int(parts[0])
                except ValueError:
                    continue

                if class_id in KEEP_CLASSES:
                    classes_found.add(class_id)

        if classes_found:
            records.append({
                "split": split,
                "image": image_path,
                "label": label_path,
                "classes": classes_found
            })

print("=" * 70)
print("ASTRA - EMERGENCY SOURCE ANALYSIS")
print("=" * 70)

ambulance_records = [
    r for r in records if 2 in r["classes"]
]

fire_records = [
    r for r in records if 11 in r["classes"]
]

print(f"\nRelevant source images: {len(records)}")
print(f"Ambulance candidate images: {len(ambulance_records)}")
print(f"Fire Truck candidate images: {len(fire_records)}")

# ------------------------------------------------------------
# Select ALL fire truck images
# ------------------------------------------------------------

fire_selected = fire_records.copy()

# Remove fire-truck images from ambulance selection
# so we don't count the same image twice.
ambulance_only = [
    r for r in ambulance_records
    if 11 not in r["classes"]
]

if len(ambulance_only) < N_AMBULANCE:
    raise RuntimeError(
        f"Not enough unique ambulance images. "
        f"Found {len(ambulance_only)}, need {N_AMBULANCE}."
    )

random.shuffle(ambulance_only)

ambulance_selected = ambulance_only[:N_AMBULANCE]

selected = ambulance_selected + fire_selected

print("\nSelection:")
print(f"Ambulance selected: {len(ambulance_selected)}")
print(f"Fire Truck selected: {len(fire_selected)}")
print(f"Total selected: {len(selected)}")

# ------------------------------------------------------------
# Shuffle and split 80/20
# ------------------------------------------------------------

random.shuffle(selected)

train_count = int(len(selected) * 0.80)

train_records = selected[:train_count]
val_records = selected[train_count:]

print("\nSplit:")
print(f"Train: {len(train_records)}")
print(f"Validation: {len(val_records)}")

# ------------------------------------------------------------
# Prepare output folders
# ------------------------------------------------------------

if OUTPUT.exists():
    print("\nRemoving previous corrected dataset...")
    shutil.rmtree(OUTPUT)

(OUTPUT / "images" / "train").mkdir(parents=True)
(OUTPUT / "images" / "val").mkdir(parents=True)
(OUTPUT / "labels" / "train").mkdir(parents=True)
(OUTPUT / "labels" / "val").mkdir(parents=True)

# ------------------------------------------------------------
# Convert annotation
# Handles:
# 1. Normal YOLO bounding boxes
# 2. YOLO polygon/segmentation annotations
# ------------------------------------------------------------

def convert_annotation(line):

    parts = line.strip().split()

    if len(parts) < 5:
        return None

    try:
        original_class = int(parts[0])
    except ValueError:
        return None

    if original_class not in KEEP_CLASSES:
        return None

    new_class = CLASS_MAPPING[original_class]

    values = []

    try:
        values = [float(x) for x in parts[1:]]
    except ValueError:
        return None

    # --------------------------------------------------------
    # Normal YOLO bounding box:
    # class x_center y_center width height
    # --------------------------------------------------------

    if len(values) == 4:

        x, y, w, h = values

        return f"{new_class} {x:.6f} {y:.6f} {w:.6f} {h:.6f}"

    # --------------------------------------------------------
    # Polygon:
    # class x1 y1 x2 y2 x3 y3 ...
    # Convert polygon to bounding box
    # --------------------------------------------------------

    if len(values) >= 6 and len(values) % 2 == 0:

        xs = values[0::2]
        ys = values[1::2]

        x_min = min(xs)
        x_max = max(xs)
        y_min = min(ys)
        y_max = max(ys)

        x_center = (x_min + x_max) / 2
        y_center = (y_min + y_max) / 2

        width = x_max - x_min
        height = y_max - y_min

        return (
            f"{new_class} "
            f"{x_center:.6f} {y_center:.6f} "
            f"{width:.6f} {height:.6f}"
        )

    return None


# ------------------------------------------------------------
# Copy selected images + labels
# ------------------------------------------------------------

class_counts = Counter()
image_counts = Counter()

def process_records(records_list, split_name):

    for index, record in enumerate(records_list):

        image_path = record["image"]
        label_path = record["label"]

        # Unique filename
        unique_id = hashlib.sha1(
            str(image_path).encode("utf-8")
        ).hexdigest()[:10]

        new_name = f"{split_name}_{unique_id}{image_path.suffix.lower()}"

        destination_image = (
            OUTPUT / "images" / split_name / new_name
        )

        destination_label = (
            OUTPUT / "labels" / split_name /
            f"{Path(new_name).stem}.txt"
        )

        new_lines = []

        with open(label_path, "r", encoding="utf-8") as f:

            for line in f:

                converted = convert_annotation(line)

                if converted:

                    new_lines.append(converted)

                    class_id = int(converted.split()[0])
                    class_counts[class_id] += 1

        if not new_lines:
            continue

        shutil.copy2(image_path, destination_image)

        with open(destination_label, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

        image_counts[split_name] += 1

        if (index + 1) % 100 == 0:
            print(
                f"{split_name}: "
                f"{index + 1}/{len(records_list)} processed"
            )


process_records(train_records, "train")
process_records(val_records, "val")

# ------------------------------------------------------------
# Create data.yaml
# ------------------------------------------------------------

yaml_text = """path: D:/ASTRA/dataset/emergency_corrected
train: images/train
val: images/val

nc: 10

names:
  0: Car
  1: Bus
  2: Truck
  3: 2-Wheeler
  4: 3-Wheeler
  5: Tempo/Van
  6: Bicycle
  7: Other
  8: Ambulance
  9: Fire Truck
"""

with open(OUTPUT / "data.yaml", "w", encoding="utf-8") as f:
    f.write(yaml_text)

# ------------------------------------------------------------
# Final report
# ------------------------------------------------------------

print("\n" + "=" * 70)
print("CORRECTED EMERGENCY DATASET COMPLETE")
print("=" * 70)

print(f"\nTrain images: {image_counts['train']}")
print(f"Validation images: {image_counts['val']}")
print(f"Total images: {image_counts['train'] + image_counts['val']}")

print("\nASTRA annotation counts:")

names = {
    0: "Car",
    1: "Bus",
    2: "Truck",
    3: "2-Wheeler",
    4: "3-Wheeler",
    5: "Tempo/Van",
    8: "Ambulance",
    9: "Fire Truck",
}

for class_id in sorted(class_counts):
    print(
        f"{class_id}: {names[class_id]} "
        f"-> {class_counts[class_id]}"
    )

print("\nOutput:")
print(OUTPUT)

print("\nOriginal emergency dataset was NOT modified.")