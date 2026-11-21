from pathlib import Path
import shutil

# ============================================================
# ASTRA - MERGE FINAL 9K + 833 FIRE TRUCK IMAGES
# ============================================================

BASE = Path(r"D:\ASTRA\dataset\final_9k")
FIRETRUCK = Path(r"D:\ASTRA\dataset\firetruck_processed")
OUTPUT = Path(r"D:\ASTRA\dataset\final_9833")


# ============================================================
# STEP 1 - Check source datasets
# ============================================================

print()
print("==========================================")
print("CHECKING SOURCE DATASETS")
print("==========================================")

if not BASE.exists():
    raise RuntimeError(f"Missing dataset:\n{BASE}")

if not FIRETRUCK.exists():
    raise RuntimeError(f"Missing dataset:\n{FIRETRUCK}")

print("ASTRA 9K dataset found.")
print("Fire Truck dataset found.")


# ============================================================
# STEP 2 - Remove old output if it exists
# ============================================================

if OUTPUT.exists():

    print()
    print("Removing previous final_9833 folder...")

    shutil.rmtree(OUTPUT)


# ============================================================
# STEP 3 - Create output structure
# ============================================================

for folder in [
    OUTPUT / "images" / "train",
    OUTPUT / "images" / "val",
    OUTPUT / "labels" / "train",
    OUTPUT / "labels" / "val",
]:
    folder.mkdir(parents=True, exist_ok=True)


# ============================================================
# STEP 4 - Copy existing ASTRA 9K
# ============================================================

print()
print("==========================================")
print("COPYING EXISTING ASTRA 9K")
print("==========================================")

base_images = 0
base_labels = 0

for split in ["train", "val"]:

    source_images = BASE / "images" / split
    source_labels = BASE / "labels" / split

    destination_images = OUTPUT / "images" / split
    destination_labels = OUTPUT / "labels" / split

    for image in source_images.iterdir():

        if image.is_file():

            destination = destination_images / image.name

            if destination.exists():
                raise RuntimeError(
                    f"Filename collision:\n{destination}"
                )

            shutil.copy2(image, destination)

            base_images += 1

    for label in source_labels.glob("*.txt"):

        destination = destination_labels / label.name

        if destination.exists():
            raise RuntimeError(
                f"Label filename collision:\n{destination}"
            )

        shutil.copy2(label, destination)

        base_labels += 1


print("Base images copied:", base_images)
print("Base labels copied:", base_labels)


# ============================================================
# STEP 5 - Add Fire Truck dataset
# ============================================================

print()
print("==========================================")
print("ADDING FIRE TRUCK DATASET")
print("==========================================")

firetruck_images = 0
firetruck_labels = 0

for split in ["train", "val"]:

    source_images = FIRETRUCK / "images" / split
    source_labels = FIRETRUCK / "labels" / split

    destination_images = OUTPUT / "images" / split
    destination_labels = OUTPUT / "labels" / split

    for image in source_images.iterdir():

        if not image.is_file():
            continue

        # Prefix prevents filename collisions
        new_image_name = "extra_firetruck_" + image.name

        destination_image = (
            destination_images / new_image_name
        )

        if destination_image.exists():
            raise RuntimeError(
                f"Fire Truck image collision:\n"
                f"{destination_image}"
            )

        # Find corresponding label
        source_label = (
            source_labels /
            f"{image.stem}.txt"
        )

        if not source_label.exists():
            raise RuntimeError(
                f"Missing Fire Truck label:\n"
                f"{source_label}"
            )

        new_label_name = (
            Path(new_image_name).stem + ".txt"
        )

        destination_label = (
            destination_labels /
            new_label_name
        )

        if destination_label.exists():
            raise RuntimeError(
                f"Fire Truck label collision:\n"
                f"{destination_label}"
            )

        shutil.copy2(
            image,
            destination_image
        )

        shutil.copy2(
            source_label,
            destination_label
        )

        firetruck_images += 1
        firetruck_labels += 1


print("Fire Truck images added:", firetruck_images)
print("Fire Truck labels added:", firetruck_labels)


# ============================================================
# STEP 6 - Create data.yaml
# ============================================================

yaml_content = """path: D:/ASTRA/dataset/final_9833
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

(OUTPUT / "data.yaml").write_text(yaml_content)


# ============================================================
# STEP 7 - Count final dataset
# ============================================================

train_images = list(
    (OUTPUT / "images" / "train").glob("*")
)

val_images = list(
    (OUTPUT / "images" / "val").glob("*")
)

train_labels = list(
    (OUTPUT / "labels" / "train").glob("*.txt")
)

val_labels = list(
    (OUTPUT / "labels" / "val").glob("*.txt")
)

total_images = (
    len(train_images) +
    len(val_images)
)

total_labels = (
    len(train_labels) +
    len(val_labels)
)


# ============================================================
# STEP 8 - Validate all labels
# ============================================================

empty_labels = []
invalid_labels = []
class_counts = {}

all_labels = train_labels + val_labels

for label_file in all_labels:

    text = label_file.read_text().strip()

    if not text:

        empty_labels.append(
            label_file
        )

        continue

    for line in text.splitlines():

        parts = line.split()

        if len(parts) != 5:

            invalid_labels.append(
                label_file
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
                label_file
            )

            continue

        # Count classes
        class_counts[class_id] = (
            class_counts.get(class_id, 0) + 1
        )

        # Class must be 0-9
        if class_id < 0 or class_id > 9:

            invalid_labels.append(
                label_file
            )

        # YOLO coordinates must be valid
        if not (
            0 <= x <= 1
            and 0 <= y <= 1
            and 0 < w <= 1
            and 0 < h <= 1
        ):

            invalid_labels.append(
                label_file
            )


# ============================================================
# STEP 9 - Final verification
# ============================================================

print()
print("==========================================")
print("FINAL 9833 DATASET VERIFICATION")
print("==========================================")
print()

print("Existing ASTRA images:", base_images)
print("Existing ASTRA labels:", base_labels)

print()

print("New Fire Truck images:", firetruck_images)
print("New Fire Truck labels:", firetruck_labels)

print()

print("Train images:", len(train_images))
print("Validation images:", len(val_images))

print()

print("TOTAL IMAGES:", total_images)
print("TOTAL LABELS:", total_labels)

print()

print("Empty labels:", len(empty_labels))
print("Invalid labels:", len(invalid_labels))

print()

print("CLASS COUNTS")
print("------------------------------------------")

for class_id in sorted(class_counts):

    print(
        f"Class {class_id}: "
        f"{class_counts[class_id]}"
    )


# ============================================================
# PASS / FAIL
# ============================================================

if (
    base_images == 9000
    and base_labels == 9000
    and firetruck_images == 833
    and firetruck_labels == 833
    and total_images == 9833
    and total_labels == 9833
    and len(empty_labels) == 0
    and len(invalid_labels) == 0
):

    print()
    print("==========================================")
    print("RESULT: PASS")
    print("==========================================")
    print()
    print("ASTRA FINAL DATASET = 9,833 IMAGES")
    print()
    print("Original final_9k was NOT modified.")

else:

    print()
    print("==========================================")
    print("RESULT: FAIL")
    print("==========================================")
    print()
    print("DO NOT TRAIN THIS DATASET.")


# ============================================================
# STEP 10 - Save report
# ============================================================

report = f"""
ASTRA FINAL 9833 DATASET
========================

Existing ASTRA dataset:
Images: {base_images}
Labels: {base_labels}

Additional Fire Truck dataset:
Images: {firetruck_images}
Labels: {firetruck_labels}

Final dataset:
Images: {total_images}
Labels: {total_labels}

Train images:
{len(train_images)}

Validation images:
{len(val_images)}

Empty labels:
{len(empty_labels)}

Invalid labels:
{len(invalid_labels)}

Class counts:
{class_counts}

Original final_9k modified:
NO
"""

(OUTPUT / "merge_report.txt").write_text(report)

print()
print("Output:")
print(OUTPUT)