from pathlib import Path
from PIL import Image
import hashlib
import math


# ============================================================
# ASTRA - FINAL DATASET PREPROCESSING / QUALITY CHECK
# Dataset: final_9833
# ============================================================

DATASET = Path(r"D:\ASTRA\dataset\final_9833")

IMAGE_DIR = DATASET / "images"
LABEL_DIR = DATASET / "labels"

REPORT_FILE = DATASET / "preprocessing_report.txt"
DUPLICATE_FILE = DATASET / "duplicate_images.txt"

EXPECTED_CLASSES = {
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

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp"
}


# ============================================================
# STEP 1 - Check dataset
# ============================================================

print()
print("============================================================")
print("ASTRA FINAL DATASET PREPROCESSING")
print("============================================================")
print()

if not DATASET.exists():
    raise RuntimeError(
        f"Dataset not found:\n{DATASET}"
    )

print("Dataset found:")
print(DATASET)


# ============================================================
# STEP 2 - Collect images and labels
# ============================================================

print()
print("============================================================")
print("STEP 1 - COLLECTING IMAGES AND LABELS")
print("============================================================")

train_images = [
    p for p in (IMAGE_DIR / "train").iterdir()
    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
]

val_images = [
    p for p in (IMAGE_DIR / "val").iterdir()
    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
]

train_labels = list(
    (LABEL_DIR / "train").glob("*.txt")
)

val_labels = list(
    (LABEL_DIR / "val").glob("*.txt")
)

print("Train images:", len(train_images))
print("Validation images:", len(val_images))

print("Train labels:", len(train_labels))
print("Validation labels:", len(val_labels))

all_images = train_images + val_images
all_labels = train_labels + val_labels

print("Total images:", len(all_images))
print("Total labels:", len(all_labels))


# ============================================================
# STEP 3 - Image / Label matching
# ============================================================

print()
print("============================================================")
print("STEP 2 - IMAGE / LABEL MATCHING")
print("============================================================")

missing_labels = []
missing_images = []


for image in all_images:

    expected_label = (
        LABEL_DIR
        / ("train" if image in train_images else "val")
        / f"{image.stem}.txt"
    )

    if not expected_label.exists():
        missing_labels.append(image)


image_stems_train = {
    image.stem for image in train_images
}

image_stems_val = {
    image.stem for image in val_images
}

for label in train_labels:

    if label.stem not in image_stems_train:
        missing_images.append(label)


for label in val_labels:

    if label.stem not in image_stems_val:
        missing_images.append(label)


print("Missing labels:", len(missing_labels))
print("Missing images:", len(missing_images))


# ============================================================
# STEP 4 - Check image integrity
# ============================================================

print()
print("============================================================")
print("STEP 3 - IMAGE INTEGRITY CHECK")
print("============================================================")

corrupted_images = []
unreadable_images = []
image_sizes = {}

print("Checking images...")

for index, image_path in enumerate(all_images, start=1):

    try:

        with Image.open(image_path) as img:

            img.verify()

        # Open again because verify() closes image data
        with Image.open(image_path) as img:

            width, height = img.size

            if width <= 0 or height <= 0:
                unreadable_images.append(image_path)

            else:
                image_sizes[image_path] = (width, height)

    except Exception:

        corrupted_images.append(image_path)

    if index % 500 == 0:
        print(
            f"Checked {index}/{len(all_images)} images..."
        )


print("Corrupted images:", len(corrupted_images))
print("Unreadable images:", len(unreadable_images))


# ============================================================
# STEP 5 - Exact duplicate image detection
# ============================================================

print()
print("============================================================")
print("STEP 4 - EXACT DUPLICATE IMAGE CHECK")
print("============================================================")

hash_map = {}

print("Calculating image hashes...")

for index, image_path in enumerate(all_images, start=1):

    try:

        sha256 = hashlib.sha256()

        with open(image_path, "rb") as file:

            while True:

                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                sha256.update(chunk)

        image_hash = sha256.hexdigest()

        if image_hash not in hash_map:

            hash_map[image_hash] = []

        hash_map[image_hash].append(image_path)

    except Exception:

        pass

    if index % 500 == 0:
        print(
            f"Hashed {index}/{len(all_images)} images..."
        )


duplicate_groups = [
    paths
    for paths in hash_map.values()
    if len(paths) > 1
]

duplicate_count = sum(
    len(group) - 1
    for group in duplicate_groups
)

print("Duplicate groups:", len(duplicate_groups))
print("Duplicate images:", duplicate_count)


# ============================================================
# STEP 6 - Train / Validation duplicate check
# ============================================================

print()
print("============================================================")
print("STEP 5 - TRAIN / VALIDATION DUPLICATE CHECK")
print("============================================================")

train_hashes = {}
val_hashes = {}

for image_path in train_images:

    try:

        sha256 = hashlib.sha256()

        with open(image_path, "rb") as file:

            while True:

                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                sha256.update(chunk)

        train_hashes[sha256.hexdigest()] = image_path

    except Exception:

        pass


for image_path in val_images:

    try:

        sha256 = hashlib.sha256()

        with open(image_path, "rb") as file:

            while True:

                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                sha256.update(chunk)

        val_hashes[sha256.hexdigest()] = image_path

    except Exception:

        pass


train_val_duplicate_hashes = (
    set(train_hashes.keys())
    &
    set(val_hashes.keys())
)

train_val_duplicates = []

for image_hash in train_val_duplicate_hashes:

    train_val_duplicates.append(
        (
            train_hashes[image_hash],
            val_hashes[image_hash]
        )
    )


print(
    "Train/Validation duplicate groups:",
    len(train_val_duplicates)
)


# ============================================================
# STEP 7 - YOLO label validation
# ============================================================

print()
print("============================================================")
print("STEP 6 - YOLO LABEL VALIDATION")
print("============================================================")

empty_labels = []
invalid_labels = []
invalid_lines = []

class_counts = {
    class_id: 0
    for class_id in EXPECTED_CLASSES
}


for label_file in all_labels:

    try:

        text = label_file.read_text(
            encoding="utf-8"
        ).strip()

    except Exception:

        invalid_labels.append(label_file)

        continue


    if not text:

        empty_labels.append(label_file)

        continue


    for line_number, line in enumerate(
        text.splitlines(),
        start=1
    ):

        parts = line.split()

        if len(parts) != 5:

            invalid_labels.append(label_file)

            invalid_lines.append(
                (
                    label_file,
                    line_number,
                    "Wrong number of values"
                )
            )

            continue


        try:

            class_id = int(parts[0])

            x = float(parts[1])
            y = float(parts[2])
            w = float(parts[3])
            h = float(parts[4])

        except ValueError:

            invalid_labels.append(label_file)

            invalid_lines.append(
                (
                    label_file,
                    line_number,
                    "Non-numeric value"
                )
            )

            continue


        # Check finite values

        if not all(
            math.isfinite(value)
            for value in [x, y, w, h]
        ):

            invalid_labels.append(label_file)

            invalid_lines.append(
                (
                    label_file,
                    line_number,
                    "Non-finite coordinate"
                )
            )

            continue


        # Check class ID

        if class_id not in EXPECTED_CLASSES:

            invalid_labels.append(label_file)

            invalid_lines.append(
                (
                    label_file,
                    line_number,
                    f"Invalid class ID: {class_id}"
                )
            )

            continue


        # Count valid object

        class_counts[class_id] += 1


        # Check YOLO coordinates

        valid_box = (
            0 <= x <= 1
            and
            0 <= y <= 1
            and
            0 < w <= 1
            and
            0 < h <= 1
        )

        if not valid_box:

            invalid_labels.append(label_file)

            invalid_lines.append(
                (
                    label_file,
                    line_number,
                    "Invalid YOLO bounding box"
                )
            )


# Remove duplicate filenames from invalid label list

invalid_labels = list(
    dict.fromkeys(invalid_labels)
)


print("Empty labels:", len(empty_labels))
print("Invalid label files:", len(invalid_labels))
print("Invalid label lines:", len(invalid_lines))


# ============================================================
# STEP 8 - Check duplicate label names
# ============================================================

print()
print("============================================================")
print("STEP 7 - LABEL NAME CHECK")
print("============================================================")

duplicate_label_names = []

for split in ["train", "val"]:

    labels = list(
        (LABEL_DIR / split).glob("*.txt")
    )

    names = {}

    for label in labels:

        if label.name in names:

            duplicate_label_names.append(
                label
            )

        names[label.name] = True


print(
    "Duplicate label filenames:",
    len(duplicate_label_names)
)


# ============================================================
# STEP 9 - Class distribution
# ============================================================

print()
print("============================================================")
print("STEP 8 - CLASS DISTRIBUTION")
print("============================================================")

for class_id in EXPECTED_CLASSES:

    class_name = EXPECTED_CLASSES[class_id]

    count = class_counts[class_id]

    print(
        f"Class {class_id}: "
        f"{class_name:<15} "
        f"{count}"
    )


missing_classes = []

for class_id in EXPECTED_CLASSES:

    if class_counts[class_id] == 0:

        missing_classes.append(
            EXPECTED_CLASSES[class_id]
        )


# ============================================================
# STEP 10 - Dataset split check
# ============================================================

print()
print("============================================================")
print("STEP 9 - TRAIN / VALIDATION SPLIT")
print("============================================================")

total_images = (
    len(train_images)
    +
    len(val_images)
)

train_percentage = (
    len(train_images)
    /
    total_images
    *
    100
)

val_percentage = (
    len(val_images)
    /
    total_images
    *
    100
)

print(
    f"Train: {len(train_images)} "
    f"({train_percentage:.2f}%)"
)

print(
    f"Validation: {len(val_images)} "
    f"({val_percentage:.2f}%)"
)


# ============================================================
# STEP 11 - Save duplicate report
# ============================================================

with open(
    DUPLICATE_FILE,
    "w",
    encoding="utf-8"
) as file:

    file.write(
        "ASTRA DUPLICATE IMAGE REPORT\n"
    )

    file.write(
        "============================\n\n"
    )


    file.write(
        f"Duplicate groups: "
        f"{len(duplicate_groups)}\n"
    )

    file.write(
        f"Duplicate images: "
        f"{duplicate_count}\n\n"
    )


    if duplicate_groups:

        file.write(
            "EXACT DUPLICATE GROUPS\n"
        )

        file.write(
            "----------------------\n\n"
        )

        for number, group in enumerate(
            duplicate_groups,
            start=1
        ):

            file.write(
                f"GROUP {number}\n"
            )

            for path in group:

                file.write(
                    f"{path}\n"
                )

            file.write("\n")


    file.write(
        "\nTRAIN / VALIDATION DUPLICATES\n"
    )

    file.write(
        "-----------------------------\n\n"
    )

    if train_val_duplicates:

        for train_path, val_path in train_val_duplicates:

            file.write(
                f"TRAIN: {train_path}\n"
            )

            file.write(
                f"VAL:   {val_path}\n\n"
            )

    else:

        file.write(
            "No train/validation duplicates found.\n"
        )


# ============================================================
# STEP 12 - Create final report
# ============================================================

report_lines = []

report_lines.append(
    "ASTRA FINAL DATASET PREPROCESSING REPORT"
)

report_lines.append(
    "========================================="
)

report_lines.append("")

report_lines.append(
    f"Dataset: {DATASET}"
)

report_lines.append("")

report_lines.append(
    f"Train images: {len(train_images)}"
)

report_lines.append(
    f"Validation images: {len(val_images)}"
)

report_lines.append(
    f"Total images: {total_images}"
)

report_lines.append("")

report_lines.append(
    f"Train labels: {len(train_labels)}"
)

report_lines.append(
    f"Validation labels: {len(val_labels)}"
)

report_lines.append(
    f"Total labels: {len(all_labels)}"
)

report_lines.append("")

report_lines.append(
    "IMAGE / LABEL CHECK"
)

report_lines.append(
    "-------------------"
)

report_lines.append(
    f"Missing labels: {len(missing_labels)}"
)

report_lines.append(
    f"Missing images: {len(missing_images)}"
)

report_lines.append("")

report_lines.append(
    "IMAGE INTEGRITY"
)

report_lines.append(
    "---------------"
)

report_lines.append(
    f"Corrupted images: {len(corrupted_images)}"
)

report_lines.append(
    f"Unreadable images: {len(unreadable_images)}"
)

report_lines.append("")

report_lines.append(
    "DUPLICATES"
)

report_lines.append(
    "----------"
)

report_lines.append(
    f"Duplicate groups: {len(duplicate_groups)}"
)

report_lines.append(
    f"Duplicate images: {duplicate_count}"
)

report_lines.append(
    f"Train/Validation duplicates: "
    f"{len(train_val_duplicates)}"
)

report_lines.append("")

report_lines.append(
    "LABEL VALIDATION"
)

report_lines.append(
    "----------------"
)

report_lines.append(
    f"Empty labels: {len(empty_labels)}"
)

report_lines.append(
    f"Invalid label files: "
    f"{len(invalid_labels)}"
)

report_lines.append(
    f"Invalid label lines: "
    f"{len(invalid_lines)}"
)

report_lines.append("")

report_lines.append(
    "CLASS DISTRIBUTION"
)

report_lines.append(
    "------------------"
)

for class_id in EXPECTED_CLASSES:

    report_lines.append(
        f"{class_id}: "
        f"{EXPECTED_CLASSES[class_id]} = "
        f"{class_counts[class_id]}"
    )


report_lines.append("")

report_lines.append(
    "MISSING CLASSES"
)

report_lines.append(
    "---------------"
)

if missing_classes:

    for class_name in missing_classes:

        report_lines.append(
            class_name
        )

else:

    report_lines.append(
        "None"
    )


# ============================================================
# STEP 13 - Final PASS / REVIEW
# ============================================================

structural_errors = (
    len(missing_labels)
    +
    len(missing_images)
    +
    len(corrupted_images)
    +
    len(unreadable_images)
    +
    len(empty_labels)
    +
    len(invalid_labels)
    +
    len(duplicate_label_names)
)

print()
print("============================================================")
print("FINAL PREPROCESSING RESULT")
print("============================================================")
print()

print(
    "Duplicate image groups:",
    len(duplicate_groups)
)

print(
    "Train/Validation duplicates:",
    len(train_val_duplicates)
)

print(
    "Corrupted images:",
    len(corrupted_images)
)

print(
    "Missing labels:",
    len(missing_labels)
)

print(
    "Missing images:",
    len(missing_images)
)

print(
    "Empty labels:",
    len(empty_labels)
)

print(
    "Invalid labels:",
    len(invalid_labels)
)

print(
    "Missing classes:",
    len(missing_classes)
)

print()

if structural_errors == 0 and len(train_val_duplicates) == 0:

    print("==========================================")
    print("RESULT: PASS")
    print("==========================================")
    print()
    print(
        "Dataset passed final preprocessing."
    )

elif structural_errors == 0:

    print("==========================================")
    print("RESULT: REVIEW DUPLICATES")
    print("==========================================")
    print()
    print(
        "Dataset structure is valid, "
        "but duplicate images require review."
    )

else:

    print("==========================================")
    print("RESULT: FAIL")
    print("==========================================")
    print()
    print(
        "Dataset has preprocessing errors."
    )


report_lines.append("")

if structural_errors == 0 and len(train_val_duplicates) == 0:

    report_lines.append(
        "FINAL RESULT: PASS"
    )

elif structural_errors == 0:

    report_lines.append(
        "FINAL RESULT: REVIEW DUPLICATES"
    )

else:

    report_lines.append(
        "FINAL RESULT: FAIL"
    )


report_lines.append("")
report_lines.append(
    f"Duplicate details: {DUPLICATE_FILE}"
)


with open(
    REPORT_FILE,
    "w",
    encoding="utf-8"
) as file:

    file.write(
        "\n".join(report_lines)
    )


# ============================================================
# STEP 14 - Final output
# ============================================================

print()
print("Report saved:")
print(REPORT_FILE)

print()
print("Duplicate report saved:")
print(DUPLICATE_FILE)

print()
print("============================================================")
print("PREPROCESSING CHECK COMPLETE")
print("============================================================")