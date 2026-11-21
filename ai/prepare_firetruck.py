from pathlib import Path
import shutil
import random
import hashlib

# ============================================================
# ASTRA - FIRE TRUCK DATASET PREPARATION
# Handles:
#   615 YOLO bounding-box annotations
#   218 YOLO polygon/segmentation annotations
#
# Original dataset is NEVER modified.
# ============================================================

SOURCE = Path(r"D:\ASTRA\dataset\firetruck_raw")
OUTPUT = Path(r"D:\ASTRA\dataset\firetruck_processed")

random.seed(42)


# ============================================================
# STEP 1 - Read and validate source dataset
# ============================================================

print()
print("==========================================")
print("VALIDATING SOURCE DATASET")
print("==========================================")

all_items = []

bbox_files = 0
polygon_files = 0
total_objects = 0

for split in ["train", "valid", "test"]:

    image_dir = SOURCE / split / "images"
    label_dir = SOURCE / split / "labels"

    images = [
        f for f in image_dir.iterdir()
        if f.is_file()
    ]

    print()
    print(split.upper())
    print("Images:", len(images))

    for image_path in images:

        # Exact matching label filename
        label_path = label_dir / (image_path.stem + ".txt")

        if not label_path.exists():
            raise RuntimeError(
                f"\nSTOP: Missing label\n{image_path}"
            )

        text = label_path.read_text().strip()

        if not text:
            raise RuntimeError(
                f"\nSTOP: Empty label\n{label_path}"
            )

        file_format = None

        for line_number, line in enumerate(
            text.splitlines(), start=1
        ):

            parts = line.strip().split()

            # ------------------------------------------------
            # Normal YOLO bounding box
            # class x_center y_center width height
            # ------------------------------------------------
            if len(parts) == 5:

                current_format = "bbox"

                try:
                    class_id = int(float(parts[0]))
                    values = [float(x) for x in parts[1:]]
                except ValueError:
                    raise RuntimeError(
                        f"\nSTOP: Invalid numbers\n"
                        f"File: {label_path}\n"
                        f"Line: {line_number}"
                    )

                if class_id != 0:
                    raise RuntimeError(
                        f"\nSTOP: Unexpected class {class_id}\n"
                        f"File: {label_path}\n"
                        f"Expected class 0"
                    )

                x, y, w, h = values

                if not (
                    0 <= x <= 1
                    and 0 <= y <= 1
                    and 0 < w <= 1
                    and 0 < h <= 1
                ):
                    raise RuntimeError(
                        f"\nSTOP: Invalid bounding box\n"
                        f"File: {label_path}\n"
                        f"Line: {line}"
                    )

            # ------------------------------------------------
            # YOLO segmentation/polygon
            # class x1 y1 x2 y2 x3 y3 ...
            # ------------------------------------------------
            elif (
                len(parts) >= 7
                and (len(parts) - 1) % 2 == 0
            ):

                current_format = "polygon"

                try:
                    class_id = int(float(parts[0]))
                    coords = [
                        float(x) for x in parts[1:]
                    ]
                except ValueError:
                    raise RuntimeError(
                        f"\nSTOP: Invalid polygon numbers\n"
                        f"File: {label_path}\n"
                        f"Line: {line_number}"
                    )

                if class_id != 0:
                    raise RuntimeError(
                        f"\nSTOP: Unexpected polygon class {class_id}\n"
                        f"File: {label_path}\n"
                        f"Expected class 0"
                    )

                if not all(0 <= x <= 1 for x in coords):
                    raise RuntimeError(
                        f"\nSTOP: Polygon coordinate outside 0-1\n"
                        f"File: {label_path}\n"
                        f"Line: {line}"
                    )

            else:
                raise RuntimeError(
                    f"\nSTOP: Unknown annotation format\n"
                    f"File: {label_path}\n"
                    f"Line: {line}"
                )

            # All lines in one file must use the same format
            if file_format is None:
                file_format = current_format

            elif current_format != file_format:
                raise RuntimeError(
                    f"\nSTOP: Mixed annotation formats in one file\n"
                    f"File: {label_path}"
                )

            total_objects += 1

        if file_format == "bbox":
            bbox_files += 1

        elif file_format == "polygon":
            polygon_files += 1

        all_items.append(
            (split, image_path, label_path, file_format)
        )


# ============================================================
# Source validation result
# ============================================================

print()
print("==========================================")
print("SOURCE VALIDATION PASSED")
print("==========================================")
print()
print("Total images:", len(all_items))
print("Bounding-box files:", bbox_files)
print("Polygon files:", polygon_files)
print("Total objects:", total_objects)
print()
print("Expected:")
print("Bounding-box files: 615")
print("Polygon files: 218")
print("Total images: 833")


if len(all_items) != 833:
    raise RuntimeError(
        f"STOP: Expected 833 images but found {len(all_items)}"
    )

if bbox_files != 615:
    raise RuntimeError(
        f"STOP: Expected 615 bbox files but found {bbox_files}"
    )

if polygon_files != 218:
    raise RuntimeError(
        f"STOP: Expected 218 polygon files but found {polygon_files}"
    )


# ============================================================
# STEP 2 - Remove previous processed dataset
# ============================================================

if OUTPUT.exists():

    print()
    print("Removing previous firetruck_processed folder...")

    shutil.rmtree(OUTPUT)


# ============================================================
# STEP 3 - Create output folders
# ============================================================

for folder in [
    OUTPUT / "images" / "train",
    OUTPUT / "images" / "val",
    OUTPUT / "labels" / "train",
    OUTPUT / "labels" / "val",
]:
    folder.mkdir(parents=True, exist_ok=True)


# ============================================================
# STEP 4 - Shuffle and split 80/20
# ============================================================

random.shuffle(all_items)

split_index = int(len(all_items) * 0.80)

train_items = all_items[:split_index]
val_items = all_items[split_index:]

print()
print("Split:")
print("Train:", len(train_items))
print("Validation:", len(val_items))


# ============================================================
# STEP 5 - Convert annotations
# ============================================================

def convert_label(label_path):

    output_lines = []

    for line in label_path.read_text().strip().splitlines():

        parts = line.strip().split()

        class_id = int(float(parts[0]))

        # ----------------------------------------------------
        # Bounding box
        # ----------------------------------------------------

        if len(parts) == 5:

            x = float(parts[1])
            y = float(parts[2])
            w = float(parts[3])
            h = float(parts[4])

        # ----------------------------------------------------
        # Polygon -> bounding box
        # ----------------------------------------------------

        else:

            coords = [
                float(x) for x in parts[1:]
            ]

            xs = coords[0::2]
            ys = coords[1::2]

            min_x = min(xs)
            max_x = max(xs)

            min_y = min(ys)
            max_y = max(ys)

            x = (min_x + max_x) / 2
            y = (min_y + max_y) / 2

            w = max_x - min_x
            h = max_y - min_y

        # ----------------------------------------------------
        # Convert Fire Truck class 0 -> ASTRA class 9
        # ----------------------------------------------------

        new_class = 9

        output_lines.append(
            f"{new_class} "
            f"{x:.6f} "
            f"{y:.6f} "
            f"{w:.6f} "
            f"{h:.6f}"
        )

    return output_lines


# ============================================================
# STEP 6 - Process images
# ============================================================

def process_split(items, split_name):

    image_count = 0
    object_count = 0

    for source_split, image_path, label_path, file_format in items:

        # Unique filename
        unique_id = hashlib.sha1(
            str(image_path).encode("utf-8")
        ).hexdigest()[:10]

        new_name = (
            f"firetruck_{unique_id}_{image_path.name}"
        )

        output_image = (
            OUTPUT
            / "images"
            / split_name
            / new_name
        )

        output_label = (
            OUTPUT
            / "labels"
            / split_name
            / f"{Path(new_name).stem}.txt"
        )

        # Convert annotation
        converted_lines = convert_label(label_path)

        if not converted_lines:
            raise RuntimeError(
                f"STOP: Converted label became empty\n"
                f"{label_path}"
            )

        # Copy image
        shutil.copy2(
            image_path,
            output_image
        )

        # Write converted label
        output_label.write_text(
            "\n".join(converted_lines) + "\n"
        )

        image_count += 1
        object_count += len(converted_lines)

    return image_count, object_count


# ============================================================
# Process train and validation
# ============================================================

train_images, train_objects = process_split(
    train_items,
    "train"
)

val_images, val_objects = process_split(
    val_items,
    "val"
)


# ============================================================
# STEP 7 - Create ASTRA data.yaml
# ============================================================

yaml_content = """path: D:/ASTRA/dataset/firetruck_processed
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

(OUTPUT / "data.yaml").write_text(
    yaml_content
)


# ============================================================
# STEP 8 - FINAL VERIFICATION
# ============================================================

train_image_files = list(
    (OUTPUT / "images" / "train").glob("*")
)

val_image_files = list(
    (OUTPUT / "images" / "val").glob("*")
)

train_label_files = list(
    (OUTPUT / "labels" / "train").glob("*.txt")
)

val_label_files = list(
    (OUTPUT / "labels" / "val").glob("*.txt")
)

all_label_files = (
    train_label_files + val_label_files
)

empty_labels = []
invalid_labels = []
class_counts = {}

for label_file in all_label_files:

    text = label_file.read_text().strip()

    if not text:
        empty_labels.append(label_file)
        continue

    for line in text.splitlines():

        parts = line.split()

        if len(parts) != 5:
            invalid_labels.append(label_file)
            continue

        class_id = int(parts[0])

        x = float(parts[1])
        y = float(parts[2])
        w = float(parts[3])
        h = float(parts[4])

        class_counts[class_id] = (
            class_counts.get(class_id, 0) + 1
        )

        if class_id != 9:
            invalid_labels.append(label_file)

        if not (
            0 <= x <= 1
            and 0 <= y <= 1
            and 0 < w <= 1
            and 0 < h <= 1
        ):
            invalid_labels.append(label_file)


# ============================================================
# FINAL RESULT
# ============================================================

total_output_images = (
    len(train_image_files)
    + len(val_image_files)
)

total_output_labels = len(all_label_files)

print()
print("==========================================")
print("FINAL FIRE TRUCK DATASET VERIFICATION")
print("==========================================")
print()
print("Train images:", len(train_image_files))
print("Train labels:", len(train_label_files))
print()
print("Validation images:", len(val_image_files))
print("Validation labels:", len(val_label_files))
print()
print("Total images:", total_output_images)
print("Total labels:", total_output_labels)
print()
print("Empty labels:", len(empty_labels))
print("Invalid labels:", len(invalid_labels))
print("Class counts:", class_counts)
print()
print("Bounding-box source files:", bbox_files)
print("Polygon source files:", polygon_files)
print()
print("Train objects:", train_objects)
print("Validation objects:", val_objects)
print("Total objects:", train_objects + val_objects)


# ============================================================
# PASS / FAIL
# ============================================================

if (
    total_output_images == 833
    and total_output_labels == 833
    and len(empty_labels) == 0
    and len(invalid_labels) == 0
    and set(class_counts.keys()) == {9}
):

    print()
    print("==========================================")
    print("RESULT: PASS")
    print("==========================================")
    print()
    print("All 833 Fire Truck images are valid.")
    print("615 bounding-box files were handled.")
    print("218 polygon files were converted to boxes.")
    print("All annotations are ASTRA class 9.")
    print("No empty labels.")
    print("No invalid labels.")
    print()
    print("Original dataset was NOT modified.")

else:

    print()
    print("==========================================")
    print("RESULT: FAIL")
    print("==========================================")
    print()
    print("DO NOT MERGE THIS DATASET.")


# ============================================================
# Report
# ============================================================

report = f"""
ASTRA FIRE TRUCK DATASET REPORT
================================

Source:
{SOURCE}

Output:
{OUTPUT}

Total source images:
{len(all_items)}

Bounding-box source files:
{bbox_files}

Polygon source files:
{polygon_files}

Total output images:
{total_output_images}

Total output labels:
{total_output_labels}

Empty labels:
{len(empty_labels)}

Invalid labels:
{len(invalid_labels)}

ASTRA class:
9 = Fire Truck

Train images:
{len(train_image_files)}

Validation images:
{len(val_image_files)}

Total objects:
{train_objects + val_objects}

Original dataset modified:
NO
"""

(OUTPUT / "processing_report.txt").write_text(report)

print()
print("Output:")
print(OUTPUT)