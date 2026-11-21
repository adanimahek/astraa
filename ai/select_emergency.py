from pathlib import Path
import random
import shutil
import hashlib

# ============================================================
# ASTRA EMERGENCY DATASET PREPROCESSING
#
# Target:
#   875 Ambulance
#   125 Fire Truck
#   Total = 1000 images
#
# Original classes:
#   2  = ambulance
#   11 = fire_truck
#
# ASTRA classes:
#   8  = Ambulance
#   9  = Fire Truck
#
# Handles:
#   1. YOLO bounding-box annotations
#   2. YOLO segmentation/polygon annotations
#
# Polygon annotations are converted to bounding boxes.
# ============================================================


# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

SOURCE = Path(
    r"D:\ASTRA\dataset\emergency_raw\extracted"
)

OUTPUT = Path(
    r"D:\ASTRA\dataset\emergency_2k"
)


# ------------------------------------------------------------
# CLASS MAPPING
# ------------------------------------------------------------

AMBULANCE_SOURCE_ID = 2
FIRE_TRUCK_SOURCE_ID = 11

AMBULANCE_ASTRA_ID = 8
FIRE_TRUCK_ASTRA_ID = 9


# ------------------------------------------------------------
# TARGET IMAGE COUNTS
# ------------------------------------------------------------

AMBULANCE_TARGET = 875
FIRE_TRUCK_TARGET = 125

RANDOM_SEED = 42

random.seed(RANDOM_SEED)


# ------------------------------------------------------------
# OUTPUT DIRECTORIES
# ------------------------------------------------------------

images_output = OUTPUT / "images"
labels_output = OUTPUT / "labels"

images_output.mkdir(
    parents=True,
    exist_ok=True
)

labels_output.mkdir(
    parents=True,
    exist_ok=True
)


# ------------------------------------------------------------
# CLEAN PREVIOUS INCOMPLETE OUTPUT
# ------------------------------------------------------------

for file in images_output.iterdir():

    if file.is_file():
        file.unlink()


for file in labels_output.iterdir():

    if file.is_file():
        file.unlink()


# ------------------------------------------------------------
# IMAGE EXTENSIONS
# ------------------------------------------------------------

IMAGE_EXTENSIONS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".JPG",
    ".JPEG",
    ".PNG"
]


# ------------------------------------------------------------
# FIND ALL LABEL FILES
# ------------------------------------------------------------

label_files = list(
    SOURCE.rglob("labels/*.txt")
)

print(
    f"Total label files found: {len(label_files)}"
)


# ------------------------------------------------------------
# FIND CORRESPONDING IMAGE
# ------------------------------------------------------------

def find_image(label_file):

    image_dir = (
        label_file.parent.parent / "images"
    )

    for extension in IMAGE_EXTENSIONS:

        image_path = (
            image_dir /
            (label_file.stem + extension)
        )

        if image_path.exists():
            return image_path

    return None


# ------------------------------------------------------------
# FIND EMERGENCY CANDIDATES
# ------------------------------------------------------------

ambulance_candidates = []

fire_truck_candidates = []


for label_file in label_files:

    try:

        lines = label_file.read_text(
            encoding="utf-8"
        ).splitlines()

    except UnicodeDecodeError:

        lines = label_file.read_text(
            encoding="utf-8-sig"
        ).splitlines()


    class_ids = set()


    for line in lines:

        parts = line.strip().split()

        if not parts:
            continue

        try:

            class_id = int(parts[0])

            class_ids.add(class_id)

        except ValueError:

            continue


    image_path = find_image(label_file)


    if image_path is None:
        continue


    # Ambulance candidate

    if AMBULANCE_SOURCE_ID in class_ids:

        ambulance_candidates.append(
            (image_path, label_file)
        )


    # Fire truck candidate

    if FIRE_TRUCK_SOURCE_ID in class_ids:

        fire_truck_candidates.append(
            (image_path, label_file)
        )


# ------------------------------------------------------------
# REMOVE DUPLICATE SOURCE PATHS
# ------------------------------------------------------------

def unique_items(items):

    seen = set()

    result = []


    for image_path, label_path in items:

        key = str(
            image_path.resolve()
        ).lower()


        if key not in seen:

            seen.add(key)

            result.append(
                (image_path, label_path)
            )


    return result


ambulance_candidates = unique_items(
    ambulance_candidates
)

fire_truck_candidates = unique_items(
    fire_truck_candidates
)


print(
    f"Ambulance candidate images: "
    f"{len(ambulance_candidates)}"
)

print(
    f"Fire Truck candidate images: "
    f"{len(fire_truck_candidates)}"
)


# ------------------------------------------------------------
# CHECK DATA AVAILABILITY
# ------------------------------------------------------------

if len(ambulance_candidates) < AMBULANCE_TARGET:

    raise RuntimeError(
        "Not enough ambulance images."
    )


if len(fire_truck_candidates) < FIRE_TRUCK_TARGET:

    raise RuntimeError(
        "Not enough fire-truck images."
    )


# ------------------------------------------------------------
# SELECT FIRE TRUCK IMAGES
# ------------------------------------------------------------

random.shuffle(
    fire_truck_candidates
)


selected_fire = (
    fire_truck_candidates[
        :FIRE_TRUCK_TARGET
    ]
)


# ------------------------------------------------------------
# REMOVE FIRE TRUCK IMAGES FROM
# AMBULANCE CANDIDATES
# ------------------------------------------------------------

fire_paths = {

    str(image_path.resolve()).lower()

    for image_path, label_path
    in selected_fire

}


remaining_ambulance = [

    item

    for item in ambulance_candidates

    if str(
        item[0].resolve()
    ).lower()
    not in fire_paths

]


# ------------------------------------------------------------
# SELECT AMBULANCE IMAGES
# ------------------------------------------------------------

if len(remaining_ambulance) < AMBULANCE_TARGET:

    raise RuntimeError(
        "Not enough unique ambulance images "
        "after removing fire-truck images."
    )


random.shuffle(
    remaining_ambulance
)


selected_ambulance = (

    remaining_ambulance[
        :AMBULANCE_TARGET
    ]

)


# ------------------------------------------------------------
# FINAL SELECTION
# ------------------------------------------------------------

selected = (

    selected_ambulance +
    selected_fire

)


random.shuffle(
    selected
)


print()
print(
    "SELECTION COMPLETE"
)

print(
    "------------------"
)

print(
    f"Ambulance selected : "
    f"{len(selected_ambulance)}"
)

print(
    f"Fire Truck selected: "
    f"{len(selected_fire)}"
)

print(
    f"Total selected     : "
    f"{len(selected)}"
)


# ------------------------------------------------------------
# PROCESS ANNOTATIONS
# ------------------------------------------------------------

processed_count = 0

skipped_count = 0


for image_path, label_path in selected:


    # --------------------------------------------------------
    # UNIQUE OUTPUT NAME
    # --------------------------------------------------------

    unique_source = str(
        image_path.resolve()
    ).encode("utf-8")


    unique_id = hashlib.sha1(
        unique_source
    ).hexdigest()[:10]


    output_stem = (

        f"{image_path.stem}_"
        f"{unique_id}"

    )


    output_image = (

        images_output /
        f"{output_stem}"
        f"{image_path.suffix.lower()}"

    )


    output_label = (

        labels_output /
        f"{output_stem}.txt"

    )


    # --------------------------------------------------------
    # READ ORIGINAL LABEL
    # --------------------------------------------------------

    try:

        lines = label_path.read_text(
            encoding="utf-8"
        ).splitlines()

    except UnicodeDecodeError:

        lines = label_path.read_text(
            encoding="utf-8-sig"
        ).splitlines()


    new_labels = []


    # --------------------------------------------------------
    # PROCESS EACH ANNOTATION
    # --------------------------------------------------------

    for line in lines:

        parts = line.strip().split()


        if len(parts) < 5:
            continue


        try:

            source_class = int(
                parts[0]
            )

            values = [

                float(value)

                for value
                in parts[1:]

            ]

        except ValueError:

            continue


        # ----------------------------------------------------
        # CLASS MAPPING
        # ----------------------------------------------------

        if source_class == AMBULANCE_SOURCE_ID:

            new_class = AMBULANCE_ASTRA_ID


        elif source_class == FIRE_TRUCK_SOURCE_ID:

            new_class = FIRE_TRUCK_ASTRA_ID


        else:

            # Ignore all other classes

            continue


        # ----------------------------------------------------
        # NORMAL YOLO BOUNDING BOX
        #
        # class x_center y_center width height
        # ----------------------------------------------------

        if len(values) == 4:

            x_center = values[0]
            y_center = values[1]
            width = values[2]
            height = values[3]


        # ----------------------------------------------------
        # YOLO SEGMENTATION POLYGON
        #
        # class x1 y1 x2 y2 x3 y3 ...
        #
        # Convert polygon into bounding box.
        # ----------------------------------------------------

        elif (
            len(values) >= 6
            and
            len(values) % 2 == 0
        ):

            xs = values[0::2]

            ys = values[1::2]


            x_min = min(xs)
            x_max = max(xs)

            y_min = min(ys)
            y_max = max(ys)


            x_center = (
                x_min + x_max
            ) / 2


            y_center = (
                y_min + y_max
            ) / 2


            width = (
                x_max - x_min
            )


            height = (
                y_max - y_min
            )


        else:

            continue


        # ----------------------------------------------------
        # CLAMP VALUES TO VALID YOLO RANGE
        # ----------------------------------------------------

        x_center = max(
            0.0,
            min(1.0, x_center)
        )

        y_center = max(
            0.0,
            min(1.0, y_center)
        )

        width = max(
            0.0,
            min(1.0, width)
        )

        height = max(
            0.0,
            min(1.0, height)
        )


        # ----------------------------------------------------
        # WRITE YOLO DETECTION LABEL
        # ----------------------------------------------------

        new_labels.append(

            f"{new_class} "
            f"{x_center:.6f} "
            f"{y_center:.6f} "
            f"{width:.6f} "
            f"{height:.6f}"

        )


    # --------------------------------------------------------
    # SKIP IF NO VALID EMERGENCY ANNOTATION
    # --------------------------------------------------------

    if not new_labels:

        skipped_count += 1

        continue


    # --------------------------------------------------------
    # COPY IMAGE
    # --------------------------------------------------------

    shutil.copy2(
        image_path,
        output_image
    )


    # --------------------------------------------------------
    # WRITE NEW LABEL
    # --------------------------------------------------------

    output_label.write_text(

        "\n".join(new_labels)
        + "\n",

        encoding="utf-8"

    )


    processed_count += 1


# ------------------------------------------------------------
# FINAL FILE COUNTS
# ------------------------------------------------------------

final_images = [

    file

    for file
    in images_output.iterdir()

    if file.is_file()

]


final_labels = [

    file

    for file
    in labels_output.iterdir()

    if file.is_file()

]


print()
print(
    "FINAL OUTPUT CHECK"
)

print(
    "------------------"
)

print(
    f"Images created : "
    f"{len(final_images)}"
)

print(
    f"Labels created : "
    f"{len(final_labels)}"
)

print(
    f"Skipped        : "
    f"{skipped_count}"
)


# ------------------------------------------------------------
# SAVE REPORT
# ------------------------------------------------------------

report = (

    OUTPUT /
    "selection_report.txt"

)


report.write_text(

f"""ASTRA EMERGENCY DATASET
PREPROCESSING REPORT

==================================================

SOURCE DATASET
==================================================

Indian Emergency Vehicles

Original images:
8,227

Original classes:
24


==================================================

ORIGINAL EMERGENCY CLASSES
==================================================

2  = ambulance
11 = fire_truck


==================================================

ASTRA CLASSES
==================================================

8 = Ambulance
9 = Fire Truck


==================================================

CANDIDATE IMAGES
==================================================

Ambulance candidates:
{len(ambulance_candidates)}

Fire Truck candidates:
{len(fire_truck_candidates)}


==================================================

SELECTED IMAGES
==================================================

Ambulance:
{len(selected_ambulance)}

Fire Truck:
{len(selected_fire)}

Total selected:
{len(selected)}


==================================================

ANNOTATION PROCESSING
==================================================

Bounding-box annotations:
Supported

Segmentation/polygon annotations:
Converted to bounding boxes

Original class 2:
Mapped to ASTRA class 8

Original class 11:
Mapped to ASTRA class 9

Other classes:
Removed


==================================================

FINAL OUTPUT
==================================================

Images created:
{len(final_images)}

Labels created:
{len(final_labels)}

Skipped:
{skipped_count}


==================================================

RANDOM SEED
==================================================

{RANDOM_SEED}


==================================================

ORIGINAL DATASET
==================================================

Original dataset modified:
NO

The source dataset remains untouched.

""",

encoding="utf-8"

)


# ------------------------------------------------------------
# FINAL RESULT
# ------------------------------------------------------------

if (

    len(final_images) == 1000

    and

    len(final_labels) == 1000

):

    print()
    print(
        "RESULT: PASS"
    )

    print(
        "Exactly 1000 images "
        "and 1000 labels created."
    )

else:

    print()
    print(
        "RESULT: CHECK REQUIRED"
    )

    print(
        "Expected:"
    )

    print(
        "1000 images"
    )

    print(
        "1000 labels"
    )


print()

print(
    f"Report saved to:"
)

print(
    report
)

print()

print(
    "Original emergency dataset "
    "was NOT modified."
)