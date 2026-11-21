from pathlib import Path
import shutil
import random

# ============================================================
# ASTRA FINAL 9K DATASET MERGE
#
# 8,000 traffic images
# +
# 1,000 emergency images
# =
# 9,000 final images
#
# Final classes: 10
# ============================================================


# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

TRAFFIC = Path(
    r"D:\ASTRA\dataset\traffic_8k"
)

EMERGENCY = Path(
    r"D:\ASTRA\dataset\emergency_2k"
)

FINAL = Path(
    r"D:\ASTRA\dataset\final_9k"
)


# ------------------------------------------------------------
# CREATE FINAL FOLDERS
# ------------------------------------------------------------

for folder in [
    FINAL / "images" / "train",
    FINAL / "images" / "val",
    FINAL / "labels" / "train",
    FINAL / "labels" / "val"
]:

    folder.mkdir(
        parents=True,
        exist_ok=True
    )


# ------------------------------------------------------------
# COPY EXISTING 8K TRAFFIC DATASET
# ------------------------------------------------------------

print("Copying 8K traffic dataset...")

traffic_train_images = list(
    (TRAFFIC / "images" / "train").glob("*")
)

traffic_val_images = list(
    (TRAFFIC / "images" / "val").glob("*")
)


for image in traffic_train_images:

    shutil.copy2(
        image,
        FINAL / "images" / "train" / image.name
    )

    label = (
        TRAFFIC /
        "labels" /
        "train" /
        f"{image.stem}.txt"
    )

    if label.exists():

        shutil.copy2(
            label,
            FINAL / "labels" /
            "train" /
            label.name
        )


for image in traffic_val_images:

    shutil.copy2(
        image,
        FINAL / "images" / "val" / image.name
    )

    label = (
        TRAFFIC /
        "labels" /
        "val" /
        f"{image.stem}.txt"
    )

    if label.exists():

        shutil.copy2(
            label,
            FINAL / "labels" /
            "val" /
            label.name
        )


print(
    f"Traffic train images copied: "
    f"{len(traffic_train_images)}"
)

print(
    f"Traffic val images copied: "
    f"{len(traffic_val_images)}"
)


# ------------------------------------------------------------
# GET EMERGENCY IMAGES
# ------------------------------------------------------------

emergency_images = []

for extension in [
    "*.jpg",
    "*.jpeg",
    "*.png"
]:

    emergency_images.extend(
        (EMERGENCY / "images").glob(extension)
    )


print(
    f"Emergency images found: "
    f"{len(emergency_images)}"
)


# ------------------------------------------------------------
# RANDOM EMERGENCY TRAIN/VAL SPLIT
# ------------------------------------------------------------

random.seed(42)

random.shuffle(
    emergency_images
)

emergency_train = emergency_images[:800]

emergency_val = emergency_images[800:]


# ------------------------------------------------------------
# COPY EMERGENCY TRAIN
# ------------------------------------------------------------

for image in emergency_train:

    shutil.copy2(
        image,
        FINAL / "images" /
        "train" /
        image.name
    )

    label = (
        EMERGENCY /
        "labels" /
        f"{image.stem}.txt"
    )

    if label.exists():

        shutil.copy2(
            label,
            FINAL / "labels" /
            "train" /
            label.name
        )


# ------------------------------------------------------------
# COPY EMERGENCY VALIDATION
# ------------------------------------------------------------

for image in emergency_val:

    shutil.copy2(
        image,
        FINAL / "images" /
        "val" /
        image.name
    )

    label = (
        EMERGENCY /
        "labels" /
        f"{image.stem}.txt"
    )

    if label.exists():

        shutil.copy2(
            label,
            FINAL / "labels" /
            "val" /
            label.name
        )


# ------------------------------------------------------------
# FINAL DATA COUNTS
# ------------------------------------------------------------

final_train_images = list(
    (FINAL / "images" / "train").glob("*")
)

final_val_images = list(
    (FINAL / "images" / "val").glob("*")
)

final_train_labels = list(
    (FINAL / "labels" / "train").glob("*.txt")
)

final_val_labels = list(
    (FINAL / "labels" / "val").glob("*.txt")
)


# ------------------------------------------------------------
# CREATE DATA.YAML
# ------------------------------------------------------------

yaml_content = """path: D:/ASTRA/dataset/final_9k

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


(FINAL / "data.yaml").write_text(
    yaml_content,
    encoding="utf-8"
)


# ------------------------------------------------------------
# FINAL REPORT
# ------------------------------------------------------------

report = f"""ASTRA FINAL DATASET REPORT

Traffic Dataset:
8000 images

Emergency Dataset:
1000 images

FINAL DATASET:
9000 images

Train:
{len(final_train_images)} images
{len(final_train_labels)} labels

Validation:
{len(final_val_images)} images
{len(final_val_labels)} labels

Classes:
10

0 Car
1 Bus
2 Truck
3 2-Wheeler
4 3-Wheeler
5 Tempo/Van
6 Bicycle
7 Other
8 Ambulance
9 Fire Truck

Emergency split:
800 train
200 validation

Random seed:
42
"""


(FINAL / "merge_report.txt").write_text(
    report,
    encoding="utf-8"
)


# ------------------------------------------------------------
# RESULT
# ------------------------------------------------------------

print()
print("===================================")
print("ASTRA FINAL DATASET MERGE COMPLETE")
print("===================================")

print()
print(
    f"Train images : "
    f"{len(final_train_images)}"
)

print(
    f"Train labels : "
    f"{len(final_train_labels)}"
)

print(
    f"Val images   : "
    f"{len(final_val_images)}"
)

print(
    f"Val labels   : "
    f"{len(final_val_labels)}"
)

print(
    f"Total images : "
    f"{len(final_train_images) + len(final_val_images)}"
)

print()
print(
    f"Final dataset:"
)

print(
    FINAL
)

print()
print(
    "data.yaml created successfully."
)