import os
import json
import random
import math
import cv2
from collections import Counter, defaultdict

# ============================================================
# ASTRA - QUALITY-AWARE 8,000 IMAGE SELECTION
# ============================================================

JSON_PATH = r"D:\ASTRA\dataset\raw\UVH-26\UVH-26-Train\UVH-26-MV-Train.json"

IMAGE_ROOT = r"D:\ASTRA\dataset\raw\UVH-26\UVH-26-Train\data"

OUTPUT_DIR = r"D:\ASTRA\dataset\selected_8k"

OUTPUT_JSON = os.path.join(
    OUTPUT_DIR,
    "selected_8000.json"
)

OUTPUT_REPORT = os.path.join(
    OUTPUT_DIR,
    "selection_report.txt"
)

TARGET_IMAGES = 8000

RANDOM_SEED = 42

random.seed(RANDOM_SEED)


# ============================================================
# FINAL ASTRA CLASSES
# ============================================================

class_names = [
    "Car",
    "Bus",
    "Truck",
    "2-Wheeler",
    "3-Wheeler",
    "Tempo/Van",
    "Bicycle",
    "Other"
]


# ============================================================
# UVH-26 -> ASTRA CLASS MAPPING
# ============================================================

class_mapping = {

    1: 0,    # Hatchback -> Car
    2: 0,    # Sedan -> Car
    3: 0,    # SUV -> Car
    4: 0,    # MUV -> Car

    5: 1,    # Bus -> Bus

    6: 2,    # Truck -> Truck

    7: 4,    # Three-wheeler -> 3-Wheeler

    8: 3,    # Two-wheeler -> 2-Wheeler

    9: 2,    # LCV -> Truck

    10: 1,   # Mini-bus -> Bus

    11: 5,   # Tempo-traveller -> Tempo/Van

    12: 6,   # Bicycle -> Bicycle

    13: 5,   # Van -> Tempo/Van

    14: 7    # Others -> Other
}


# ============================================================
# TRAFFIC DENSITY TARGET
# ============================================================

density_targets = {

    "1-5": 800,
    "6-10": 2400,
    "11-20": 3200,
    "21-50": 1500,
    "51+": 27
}


# ============================================================
# CREATE OUTPUT DIRECTORY
# ============================================================

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


print("=" * 70)
print("ASTRA - QUALITY-AWARE UVH-26 8K SELECTION")
print("=" * 70)


# ============================================================
# LOAD JSON
# ============================================================

print("\n[1/7] Loading MV annotation file...")

with open(
    JSON_PATH,
    "r",
    encoding="utf-8"
) as f:

    data = json.load(f)


images = data["images"]

annotations = data["annotations"]

categories = data["categories"]


print("Source images      :", len(images))

print("Source annotations :", len(annotations))

print("Original categories :", len(categories))


# ============================================================
# IMAGE LOOKUP
# ============================================================

image_info = {
    img["id"]: img
    for img in images
}


# ============================================================
# BUILD CATEGORY NAME LOOKUP
# ============================================================

category_names = {
    c["id"]: c["name"]
    for c in categories
}


print("\nOriginal UVH-26 classes:")

for category_id, name in category_names.items():

    print(
        f"{category_id:2d} -> {name}"
    )


# ============================================================
# GROUP ANNOTATIONS BY IMAGE
# ============================================================

print("\n[2/7] Processing annotations...")

image_annotations = defaultdict(list)

invalid_annotation_count = 0

valid_annotation_count = 0


for ann in annotations:

    image_id = ann.get("image_id")

    category_id = ann.get("category_id")

    bbox = ann.get("bbox")


    # --------------------------------------------------------
    # Check category
    # --------------------------------------------------------

    if category_id not in class_mapping:

        invalid_annotation_count += 1

        continue


    # --------------------------------------------------------
    # Check bbox format
    # --------------------------------------------------------

    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
    ):

        invalid_annotation_count += 1

        continue


    try:

        x, y, w, h = [
            float(v)
            for v in bbox
        ]

    except:

        invalid_annotation_count += 1

        continue


    # --------------------------------------------------------
    # Check bbox values
    # --------------------------------------------------------

    if (
        not all(
            math.isfinite(v)
            for v in [x, y, w, h]
        )
        or w <= 0
        or h <= 0
    ):

        invalid_annotation_count += 1

        continue


    # --------------------------------------------------------
    # Convert original class -> ASTRA class
    # --------------------------------------------------------

    astra_class = class_mapping[category_id]

    image_annotations[image_id].append(
        {
            "class_id": astra_class,
            "bbox": [x, y, w, h]
        }
    )

    valid_annotation_count += 1


print(
    "Valid annotations   :",
    valid_annotation_count
)

print(
    "Invalid annotations :",
    invalid_annotation_count
)


# ============================================================
# INDEX ALL IMAGE FILES
# ============================================================

print("\n[3/7] Indexing image files...")

print(
    "This may take a few minutes because UVH-26 contains"
)

print(
    "more than 21,000 high-resolution images."
)


file_index = {}

file_count = 0


for root, dirs, files in os.walk(IMAGE_ROOT):

    for filename in files:

        if filename.lower().endswith(
            (".png", ".jpg", ".jpeg")
        ):

            full_path = os.path.join(
                root,
                filename
            )

            file_index[filename] = full_path

            file_count += 1


print(
    "Image files found:",
    file_count
)


# ============================================================
# VALIDATE IMAGES + ANNOTATIONS
# ============================================================

print("\n[4/7] Validating images and annotations...")

print(
    "The script will open each candidate image."
)

print(
    "This can take some time. Please wait."
)


records = []

missing_images = 0

unreadable_images = 0

no_annotation_images = 0

valid_images = 0


for index, img in enumerate(images, start=1):

    image_id = img["id"]

    filename = img["file_name"]


    # --------------------------------------------------------
    # Check image file exists
    # --------------------------------------------------------

    image_path = file_index.get(filename)


    if image_path is None:

        missing_images += 1

        continue


    # --------------------------------------------------------
    # Check image can be opened
    # --------------------------------------------------------

    image = cv2.imread(
        image_path,
        cv2.IMREAD_COLOR
    )


    if image is None:

        unreadable_images += 1

        continue


    # --------------------------------------------------------
    # Check annotations
    # --------------------------------------------------------

    anns = image_annotations.get(
        image_id,
        []
    )


    if len(anns) == 0:

        no_annotation_images += 1

        continue


    # --------------------------------------------------------
    # Get classes
    # --------------------------------------------------------

    class_ids = [
        ann["class_id"]
        for ann in anns
    ]


    unique_classes = sorted(
        set(class_ids)
    )


    # --------------------------------------------------------
    # Verify image dimensions
    # --------------------------------------------------------

    actual_height, actual_width = image.shape[:2]

    expected_width = img["width"]

    expected_height = img["height"]


    if (
        actual_width != expected_width
        or actual_height != expected_height
    ):

        # We do NOT reject automatically.
        # We simply record the actual dimensions.

        pass


    # --------------------------------------------------------
    # Calculate bounding-box quality
    # --------------------------------------------------------

    valid_boxes = 0

    total_box_area = 0.0


    for ann in anns:

        x, y, w, h = ann["bbox"]


        # Check bbox is at least partly inside image

        x2 = x + w

        y2 = y + h


        if (
            x2 > 0
            and y2 > 0
            and x < actual_width
            and y < actual_height
        ):

            valid_boxes += 1


        # Calculate area ratio

        box_area = max(
            0,
            min(x2, actual_width)
            - max(x, 0)
        ) * max(
            0,
            min(y2, actual_height)
            - max(y, 0)
        )


        total_box_area += box_area


    # --------------------------------------------------------
    # Require every annotation to have a valid visible box
    # --------------------------------------------------------

    if valid_boxes != len(anns):

        continue


    # --------------------------------------------------------
    # Density
    # --------------------------------------------------------

    object_count = len(anns)


    if object_count <= 5:

        density = "1-5"

    elif object_count <= 10:

        density = "6-10"

    elif object_count <= 20:

        density = "11-20"

    elif object_count <= 50:

        density = "21-50"

    else:

        density = "51+"


    # --------------------------------------------------------
    # Save record
    # --------------------------------------------------------

    records.append(
        {
            "id": image_id,
            "filename": filename,
            "path": image_path,
            "width": actual_width,
            "height": actual_height,
            "object_count": object_count,
            "classes": unique_classes,
            "density": density,
            "box_area": total_box_area
        }
    )


    valid_images += 1


    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    if index % 500 == 0:

        print(
            f"Validated {index}/{len(images)} images..."
        )


print("\nImage validation complete.")

print(
    "Valid usable images:",
    valid_images
)

print(
    "Missing images:",
    missing_images
)

print(
    "Unreadable images:",
    unreadable_images
)

print(
    "Images without annotations:",
    no_annotation_images
)


# ============================================================
# CLASS COVERAGE
# ============================================================

print("\n[5/7] Analyzing class coverage...")


class_image_frequency = Counter()


for record in records:

    for class_id in record["classes"]:

        class_image_frequency[class_id] += 1


print("\nValid image coverage:")

for class_id, name in enumerate(class_names):

    print(
        f"{class_id}: "
        f"{name:12s} -> "
        f"{class_image_frequency[class_id]:6d}"
    )


# ============================================================
# DENSITY GROUPS
# ============================================================

density_groups = defaultdict(list)


for record in records:

    density_groups[
        record["density"]
    ].append(record)


print("\nValid traffic-density distribution:")

for density in density_targets:

    print(
        f"{density:6s}: "
        f"{len(density_groups[density]):6d} "
        f"(target {density_targets[density]})"
    )


# ============================================================
# RARITY WEIGHTS
# ============================================================

rarity_weights = {}


for class_id in range(
    len(class_names)
):

    frequency = class_image_frequency[
        class_id
    ]


    if frequency > 0:

        rarity_weights[class_id] = (
            len(records) / frequency
        )

    else:

        rarity_weights[class_id] = 1.0


print("\nClass rarity weights:")

for class_id, name in enumerate(class_names):

    print(
        f"{name:12s}: "
        f"{rarity_weights[class_id]:.2f}"
    )


# ============================================================
# IMAGE SCORING
# ============================================================

def base_score(record):

    # --------------------------------------------------------
    # Rare classes are valuable
    # --------------------------------------------------------

    rarity_score = sum(
        rarity_weights[class_id]
        for class_id in record["classes"]
    )


    # --------------------------------------------------------
    # Multiple vehicle types are valuable
    # --------------------------------------------------------

    diversity_score = (
        len(record["classes"]) * 4.0
    )


    # --------------------------------------------------------
    # More vehicles give useful traffic information
    # --------------------------------------------------------

    density_score = min(
        record["object_count"],
        30
    ) * 0.15


    # --------------------------------------------------------
    # Small random value prevents identical ordering
    # --------------------------------------------------------

    random_score = random.random()


    return (
        rarity_score
        + diversity_score
        + density_score
        + random_score
    )


# ============================================================
# PRE-SCORE ALL IMAGES
# ============================================================

for record in records:

    record["score"] = base_score(
        record
    )


# ============================================================
# GUARANTEE CLASS COVERAGE
# ============================================================

print("\nEnsuring every ASTRA class is represented...")


selected = []

selected_ids = set()


for class_id in range(
    len(class_names)
):

    candidates = [
        record
        for record in records
        if (
            class_id in record["classes"]
            and record["id"] not in selected_ids
        )
    ]


    candidates.sort(
        key=lambda r: r["score"],
        reverse=True
    )


    if candidates:

        chosen = candidates[0]

        selected.append(chosen)

        selected_ids.add(
            chosen["id"]
        )

        print(
            f"Coverage: {class_names[class_id]}"
            f" -> {chosen['filename']}"
        )

    else:

        print(
            f"WARNING: No valid image found for "
            f"{class_names[class_id]}"
        )


# ============================================================
# SELECT ACCORDING TO DENSITY TARGETS
# ============================================================

print("\nSelecting according to traffic density...")


for density, target in density_targets.items():

    candidates = [
        record
        for record in density_groups[density]
        if record["id"] not in selected_ids
    ]


    # Sort by quality / rarity / diversity

    candidates.sort(
        key=lambda r: r["score"],
        reverse=True
    )


    already_selected_in_density = sum(
        1
        for r in selected
        if r["density"] == density
    )


    remaining_target = max(
        0,
        target - already_selected_in_density
    )


    take = min(
        remaining_target,
        len(candidates)
    )


    chosen = candidates[:take]


    for record in chosen:

        selected.append(record)

        selected_ids.add(
            record["id"]
        )


    print(
        f"{density:6s}: "
        f"selected {take}"
    )


# ============================================================
# FILL ANY REMAINING SLOTS
# ============================================================

remaining_needed = (
    TARGET_IMAGES
    - len(selected)
)


if remaining_needed > 0:

    print(
        f"\nNeed {remaining_needed} more images."
    )


    remaining = [
        record
        for record in records
        if record["id"] not in selected_ids
    ]


    remaining.sort(
        key=lambda r: r["score"],
        reverse=True
    )


    for record in remaining[
        :remaining_needed
    ]:

        selected.append(record)

        selected_ids.add(
            record["id"]
        )


# ============================================================
# SAFETY CHECK
# ============================================================

if len(selected) != TARGET_IMAGES:

    raise RuntimeError(
        f"Could only select {len(selected)} "
        f"images instead of {TARGET_IMAGES}."
    )


# ============================================================
# FINAL STATISTICS
# ============================================================

print("\n[6/7] Calculating final statistics...")


selected_class_coverage = Counter()

selected_density = Counter()


for record in selected:

    for class_id in record["classes"]:

        selected_class_coverage[
            class_id
        ] += 1


    selected_density[
        record["density"]
    ] += 1


# ============================================================
# SAVE MANIFEST
# ============================================================

manifest_images = []


for record in selected:

    manifest_images.append(
        {
            "id": record["id"],
            "filename": record["filename"],
            "path": record["path"],
            "width": record["width"],
            "height": record["height"],
            "object_count": record["object_count"],
            "classes": [
                class_names[c]
                for c in record["classes"]
            ],
            "class_ids": record["classes"],
            "density": record["density"]
        }
    )


manifest = {

    "project": "ASTRA",

    "source_dataset": "UVH-26",

    "annotation_type": "MV - Majority Voting",

    "source_images": len(images),

    "valid_images": len(records),

    "selected_images": len(selected),

    "original_classes": category_names,

    "astra_classes": class_names,

    "class_mapping": class_mapping,

    "density_targets": density_targets,

    "quality_checks": {

        "image_readable": True,

        "annotations_validated": True,

        "bounding_boxes_validated": True

    },

    "images": manifest_images
}


with open(
    OUTPUT_JSON,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        manifest,
        f,
        indent=2
    )


# ============================================================
# SAVE HUMAN-READABLE REPORT
# ============================================================

with open(
    OUTPUT_REPORT,
    "w",
    encoding="utf-8"
) as f:

    f.write(
        "ASTRA - UVH-26 8K SELECTION REPORT\n"
    )

    f.write(
        "=" * 60 + "\n\n"
    )


    f.write(
        f"Source images: {len(images)}\n"
    )

    f.write(
        f"Valid images: {len(records)}\n"
    )

    f.write(
        f"Selected images: {len(selected)}\n\n"
    )


    f.write(
        "ASTRA CLASS COVERAGE\n"
    )

    f.write(
        "-" * 40 + "\n"
    )


    for class_id, name in enumerate(
        class_names
    ):

        f.write(
            f"{name:15s}: "
            f"{selected_class_coverage[class_id]}\n"
        )


    f.write(
        "\nTRAFFIC DENSITY\n"
    )

    f.write(
        "-" * 40 + "\n"
    )


    for density in density_targets:

        f.write(
            f"{density:15s}: "
            f"{selected_density[density]}\n"
        )


    f.write(
        "\nQUALITY CHECKS\n"
    )

    f.write(
        "-" * 40 + "\n"
    )

    f.write(
        "Readable images: PASS\n"
    )

    f.write(
        "Valid annotations: PASS\n"
    )

    f.write(
        "Valid bounding boxes: PASS\n"
    )

    f.write(
        "Original dataset modified: NO\n"
    )


# ============================================================
# FINAL OUTPUT
# ============================================================

print("\n" + "=" * 70)

print("8,000 IMAGE SELECTION COMPLETE")

print("=" * 70)


print(
    "\nSelected images:",
    len(selected)
)


print("\nASTRA class coverage:")

for class_id, name in enumerate(
    class_names
):

    print(
        f"{name:12s}: "
        f"{selected_class_coverage[class_id]}"
    )


print("\nTraffic density:")

for density in density_targets:

    print(
        f"{density:6s}: "
        f"{selected_density[density]}"
    )


print("\nFiles created:")

print(
    OUTPUT_JSON
)

print(
    OUTPUT_REPORT
)


print(
    "\nIMPORTANT:"
)

print(
    "No original UVH-26 images were moved, copied, or deleted."
)

print(
    "The 8K images have NOT been copied yet."
)

print(
    "We will inspect the selection before creating the final dataset."
)

print("\nDONE.")