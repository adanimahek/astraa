from pathlib import Path
from collections import Counter

SOURCE = Path(r"D:\ASTRA\dataset\emergency_raw\extracted")

CLASS_NAMES = {
    0: "Army",
    1: "Vehicle",
    2: "Ambulance",
    3: "ambulance_108",
    4: "ambulance_SOL",
    5: "ambulance_lamp",
    6: "ambulance_text",
    7: "auto",
    8: "bike",
    9: "bus",
    10: "car",
    11: "fire_truck",
    12: "fireladder",
    13: "firelamp",
    14: "firesymbol",
    15: "firewriting",
    16: "hose",
    17: "police",
    18: "police_lamp",
    19: "police_lamp_ON",
    20: "road_sign",
    21: "tempo traveller",
    22: "truck",
    23: "writing",
}

annotation_counts = Counter()
image_counts = Counter()
images_with_multiple_classes = 0

total_images = 0
total_labels = 0
empty_labels = 0

for split in ["train", "valid", "test"]:

    label_dir = SOURCE / split / "labels"

    if not label_dir.exists():
        continue

    for label_file in label_dir.glob("*.txt"):

        total_images += 1
        total_labels += 1

        text = label_file.read_text().strip()

        if not text:
            empty_labels += 1
            continue

        classes_in_image = set()

        for line in text.splitlines():

            parts = line.split()

            if len(parts) < 5:
                continue

            class_id = int(float(parts[0]))

            annotation_counts[class_id] += 1
            classes_in_image.add(class_id)

        for class_id in classes_in_image:
            image_counts[class_id] += 1

        if len(classes_in_image) > 1:
            images_with_multiple_classes += 1


print()
print("==========================================")
print("ASTRA EMERGENCY DATASET INSPECTION")
print("==========================================")
print()

print("Total image/label files:", total_images)
print("Empty labels:", empty_labels)
print("Images containing multiple classes:", images_with_multiple_classes)

print()
print("ANNOTATION COUNTS")
print("------------------------------------------")

for class_id in sorted(annotation_counts):

    print(
        f"{class_id:2d} | "
        f"{CLASS_NAMES.get(class_id, 'UNKNOWN'):20s} | "
        f"{annotation_counts[class_id]}"
    )

print()
print("IMAGE COUNTS BY CLASS")
print("------------------------------------------")

for class_id in sorted(image_counts):

    print(
        f"{class_id:2d} | "
        f"{CLASS_NAMES.get(class_id, 'UNKNOWN'):20s} | "
        f"{image_counts[class_id]}"
    )

print()
print("ASTRA-RELEVANT CLASSES")
print("------------------------------------------")

astra_classes = {
    2: "Ambulance",
    7: "3-Wheeler",
    8: "2-Wheeler",
    9: "Bus",
    10: "Car",
    11: "Fire Truck",
    21: "Tempo/Van",
    22: "Truck",
}

for class_id, name in astra_classes.items():

    print(
        f"{name:12s} | "
        f"annotations: {annotation_counts.get(class_id, 0):5d} | "
        f"images: {image_counts.get(class_id, 0):5d}"
    )

print()
print("==========================================")
print("INSPECTION COMPLETE")
print("==========================================")
print()
print("Original emergency dataset was NOT modified.")