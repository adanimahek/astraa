import os

DATASET = r"D:\ASTRA\dataset\traffic_8k"

VALID_CLASSES = set(range(8))

errors = []
empty_files = []
total_labels = 0

for split in ["train", "val"]:

    label_dir = os.path.join(
        DATASET,
        "labels",
        split
    )

    for filename in os.listdir(label_dir):

        if not filename.endswith(".txt"):
            continue

        path = os.path.join(
            label_dir,
            filename
        )

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            lines = [
                line.strip()
                for line in f
                if line.strip()
            ]

        if not lines:

            empty_files.append(
                f"{split}/{filename}"
            )

            continue

        for line_number, line in enumerate(
            lines,
            start=1
        ):

            parts = line.split()

            if len(parts) != 5:

                errors.append(
                    f"{split}/{filename}: "
                    f"line {line_number} "
                    f"must contain 5 values"
                )

                continue

            try:

                class_id = int(parts[0])

                values = [
                    float(x)
                    for x in parts[1:]
                ]

            except ValueError:

                errors.append(
                    f"{split}/{filename}: "
                    f"non-numeric value"
                )

                continue

            if class_id not in VALID_CLASSES:

                errors.append(
                    f"{split}/{filename}: "
                    f"invalid class {class_id}"
                )

            x, y, w, h = values

            if not all(
                0.0 <= value <= 1.0
                for value in values
            ):

                errors.append(
                    f"{split}/{filename}: "
                    f"coordinates outside 0-1"
                )

            if w <= 0 or h <= 0:

                errors.append(
                    f"{split}/{filename}: "
                    f"invalid width/height"
                )

            total_labels += 1


print("=" * 60)
print("ASTRA 8K YOLO LABEL VERIFICATION")
print("=" * 60)

print(
    "\nTotal annotation objects:",
    total_labels
)

print(
    "Empty label files:",
    len(empty_files)
)

print(
    "Label errors:",
    len(errors)
)


if empty_files:

    print("\nEMPTY LABEL FILES:")

    for item in empty_files[:20]:

        print(item)


if errors:

    print("\nLABEL ERRORS:")

    for error in errors[:50]:

        print(error)


print("\n" + "=" * 60)

if not empty_files and not errors:

    print("RESULT: PASS")
    print("All YOLO labels are valid.")
    print("Classes are within 0-7.")
    print("Coordinates are within 0-1.")

else:

    print("RESULT: CHECK REQUIRED")

print("=" * 60)