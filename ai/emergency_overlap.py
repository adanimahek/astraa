from pathlib import Path
from collections import Counter
from itertools import combinations

SOURCE = Path(r"D:\ASTRA\dataset\emergency_raw\extracted")

CLASS_NAMES = {
    2: "Ambulance",
    7: "3-Wheeler",
    8: "2-Wheeler",
    9: "Bus",
    10: "Car",
    11: "Fire Truck",
    21: "Tempo/Van",
    22: "Truck",
}

EMERGENCY_CLASSES = {
    2: "Ambulance",
    11: "Fire Truck",
}

ASTRA_CLASSES = set(CLASS_NAMES.keys())

pair_counts = Counter()

ambulance_images = 0
firetruck_images = 0
both_emergency_images = 0

# Count emergency images containing other ASTRA vehicles
ambulance_with_other = Counter()
firetruck_with_other = Counter()

for split in ["train", "valid", "test"]:

    label_dir = SOURCE / split / "labels"

    if not label_dir.exists():
        continue

    for label_file in label_dir.glob("*.txt"):

        text = label_file.read_text().strip()

        if not text:
            continue

        classes = set()

        for line in text.splitlines():

            parts = line.split()

            if len(parts) < 5:
                continue

            class_id = int(float(parts[0]))

            if class_id in ASTRA_CLASSES:
                classes.add(class_id)

        # Need at least one ASTRA class
        if not classes:
            continue

        # Count class pairs in each image
        for a, b in combinations(sorted(classes), 2):
            pair_counts[(a, b)] += 1

        # Ambulance image
        if 2 in classes:

            ambulance_images += 1

            for class_id in classes:
                if class_id != 2:
                    ambulance_with_other[class_id] += 1

        # Fire truck image
        if 11 in classes:

            firetruck_images += 1

            for class_id in classes:
                if class_id != 11:
                    firetruck_with_other[class_id] += 1

        # Both ambulance + fire truck
        if 2 in classes and 11 in classes:
            both_emergency_images += 1


print()
print("==========================================")
print("ASTRA EMERGENCY OVERLAP ANALYSIS")
print("==========================================")
print()

print("Ambulance images:", ambulance_images)
print("Fire Truck images:", firetruck_images)
print("Images containing BOTH:", both_emergency_images)

print()
print("AMBULANCE + OTHER ASTRA VEHICLES")
print("------------------------------------------")

for class_id in sorted(ambulance_with_other):

    print(
        f"Ambulance + "
        f"{CLASS_NAMES[class_id]:12s}: "
        f"{ambulance_with_other[class_id]}"
    )

print()
print("FIRE TRUCK + OTHER ASTRA VEHICLES")
print("------------------------------------------")

for class_id in sorted(firetruck_with_other):

    print(
        f"Fire Truck + "
        f"{CLASS_NAMES[class_id]:12s}: "
        f"{firetruck_with_other[class_id]}"
    )

print()
print("ALL ASTRA CLASS PAIRS")
print("------------------------------------------")

for (a, b), count in sorted(pair_counts.items()):

    print(
        f"{CLASS_NAMES[a]:12s} + "
        f"{CLASS_NAMES[b]:12s}: "
        f"{count}"
    )

print()
print("==========================================")
print("ANALYSIS COMPLETE")
print("==========================================")
print()
print("Original emergency dataset was NOT modified.")