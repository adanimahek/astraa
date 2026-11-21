from pathlib import Path
from collections import Counter

# ============================================================
# ASTRA FINAL 9K DATASET VERIFICATION
# ============================================================

DATASET = Path(
    r"D:\ASTRA\dataset\final_9k"
)

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


# ------------------------------------------------------------
# CHECK SPLITS
# ------------------------------------------------------------

splits = ["train", "val"]

total_images = 0
total_labels = 0

class_counts = Counter()

invalid_labels = []
missing_labels = []

empty_labels = []


for split in splits:

    images_dir = DATASET / "images" / split
    labels_dir = DATASET / "labels" / split

    images = []

    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        images.extend(images_dir.glob(ext))

    labels = list(
        labels_dir.glob("*.txt")
    )

    print()
    print("=" * 50)
    print(f"{split.upper()} DATA")
    print("=" * 50)

    print(
        f"Images : {len(images)}"
    )

    print(
        f"Labels : {len(labels)}"
    )


    total_images += len(images)
    total_labels += len(labels)


    # --------------------------------------------------------
    # Check every image has a label
    # --------------------------------------------------------

    label_names = {
        label.stem
        for label in labels
    }


    for image in images:

        if image.stem not in label_names:

            missing_labels.append(
                f"{split}/{image.name}"
            )


    # --------------------------------------------------------
    # Check labels
    # --------------------------------------------------------

    for label_file in labels:

        try:

            lines = label_file.read_text(
                encoding="utf-8"
            ).splitlines()

        except UnicodeDecodeError:

            lines = label_file.read_text(
                encoding="utf-8-sig"
            ).splitlines()


        if not lines:

            empty_labels.append(
                f"{split}/{label_file.name}"
            )

            continue


        for line_number, line in enumerate(
            lines,
            start=1
        ):

            parts = line.strip().split()


            # YOLO detection must have 5 values
            if len(parts) != 5:

                invalid_labels.append(
                    f"{split}/{label_file.name}: "
                    f"line {line_number} "
                    f"has {len(parts)} values"
                )

                continue


            try:

                class_id = int(parts[0])

                x = float(parts[1])
                y = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])

            except ValueError:

                invalid_labels.append(
                    f"{split}/{label_file.name}: "
                    f"invalid numeric value"
                )

                continue


            # ------------------------------------------------
            # Class range
            # ------------------------------------------------

            if class_id not in CLASS_NAMES:

                invalid_labels.append(
                    f"{split}/{label_file.name}: "
                    f"invalid class {class_id}"
                )

                continue


            class_counts[class_id] += 1


            # ------------------------------------------------
            # Coordinate range
            # ------------------------------------------------

            if not (
                0 <= x <= 1
                and
                0 <= y <= 1
                and
                0 <= w <= 1
                and
                0 <= h <= 1
            ):

                invalid_labels.append(
                    f"{split}/{label_file.name}: "
                    f"coordinate outside 0-1 range"
                )


# ============================================================
# FINAL RESULTS
# ============================================================

print()
print("=" * 50)
print("ASTRA FINAL 9K VERIFICATION")
print("=" * 50)

print()
print(
    f"Total images : {total_images}"
)

print(
    f"Total labels : {total_labels}"
)

print()
print("CLASS OBJECT COUNTS")
print("-------------------")


for class_id in range(10):

    print(
        f"{class_id}: "
        f"{CLASS_NAMES[class_id]:12s} "
        f"= {class_counts[class_id]}"
    )


print()
print("CHECKS")
print("------")

print(
    f"Missing labels : "
    f"{len(missing_labels)}"
)

print(
    f"Empty labels   : "
    f"{len(empty_labels)}"
)

print(
    f"Invalid labels : "
    f"{len(invalid_labels)}"
)


# ============================================================
# EMERGENCY CLASS CHECK
# ============================================================

print()
print("EMERGENCY CLASSES")
print("-----------------")

print(
    f"Ambulance objects : "
    f"{class_counts[8]}"
)

print(
    f"Fire Truck objects: "
    f"{class_counts[9]}"
)


# ============================================================
# FINAL RESULT
# ============================================================

print()

if (
    total_images == 9000
    and
    total_labels == 9000
    and
    len(missing_labels) == 0
    and
    len(empty_labels) == 0
    and
    len(invalid_labels) == 0
    and
    class_counts[8] > 0
    and
    class_counts[9] > 0
):

    print("RESULT: PASS")
    print(
        "Final 9K dataset is valid "
        "and ready for YOLO training."
    )

else:

    print("RESULT: CHECK REQUIRED")

    if missing_labels:
        print(
            f"Missing labels: "
            f"{missing_labels[:10]}"
        )

    if empty_labels:
        print(
            f"Empty labels: "
            f"{empty_labels[:10]}"
        )

    if invalid_labels:
        print(
            f"Invalid labels: "
            f"{invalid_labels[:10]}"
        )


# ============================================================
# SAVE REPORT
# ============================================================

report = DATASET / "verification_report.txt"

report.write_text(
    f"""ASTRA FINAL 9K DATASET VERIFICATION

Total images: {total_images}
Total labels: {total_labels}

Missing labels: {len(missing_labels)}
Empty labels: {len(empty_labels)}
Invalid labels: {len(invalid_labels)}

Class object counts:

0 Car = {class_counts[0]}
1 Bus = {class_counts[1]}
2 Truck = {class_counts[2]}
3 2-Wheeler = {class_counts[3]}
4 3-Wheeler = {class_counts[4]}
5 Tempo/Van = {class_counts[5]}
6 Bicycle = {class_counts[6]}
7 Other = {class_counts[7]}
8 Ambulance = {class_counts[8]}
9 Fire Truck = {class_counts[9]}
""",
    encoding="utf-8"
)

print()
print(
    f"Report saved to: {report}"
)