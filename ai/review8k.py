import os
import json
import random
import cv2

# ============================================================
# ASTRA - Visual Review of Selected 8K
# ============================================================

SELECTION_JSON = r"D:\ASTRA\dataset\selected_8k\selected_8000.json"

ANNOTATION_JSON = r"D:\ASTRA\dataset\raw\UVH-26\UVH-26-Train\UVH-26-MV-Train.json"

OUTPUT_DIR = r"D:\ASTRA\dataset\selected_8k\visual_review"

SAMPLE_COUNT = 40

RANDOM_SEED = 42

random.seed(RANDOM_SEED)

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# ASTRA classes
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
# UVH-26 -> ASTRA mapping
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
# Load selected 8K
# ============================================================

print("Loading selected 8K...")

with open(
    SELECTION_JSON,
    "r",
    encoding="utf-8"
) as f:

    selection_data = json.load(f)


selected = selection_data["images"]

selected_ids = {
    item["id"]
    for item in selected
}

print(
    "Selected images:",
    len(selected)
)


# ============================================================
# Load original MV annotations
# ============================================================

print("Loading original MV annotations...")

with open(
    ANNOTATION_JSON,
    "r",
    encoding="utf-8"
) as f:

    annotation_data = json.load(f)


# ============================================================
# Get annotations only for selected images
# ============================================================

print("Preparing bounding boxes...")

selected_annotations = {}

for ann in annotation_data["annotations"]:

    image_id = ann["image_id"]

    if image_id not in selected_ids:
        continue

    original_class = ann["category_id"]

    if original_class not in class_mapping:
        continue

    astra_class = class_mapping[original_class]

    if image_id not in selected_annotations:

        selected_annotations[image_id] = []

    selected_annotations[image_id].append(
        {
            "bbox": ann["bbox"],
            "class_id": astra_class
        }
    )


# ============================================================
# Select random visual samples
# ============================================================

sample_count = min(
    SAMPLE_COUNT,
    len(selected)
)

samples = random.sample(
    selected,
    sample_count
)

print(
    "Visual samples:",
    sample_count
)


# ============================================================
# Create visual samples
# ============================================================

for index, record in enumerate(
    samples,
    start=1
):

    image_path = record["path"]

    image = cv2.imread(
        image_path
    )

    if image is None:

        print(
            "Could not open:",
            image_path
        )

        continue


    image_id = record["id"]

    annotations = selected_annotations.get(
        image_id,
        []
    )


    # --------------------------------------------------------
    # Draw bounding boxes
    # --------------------------------------------------------

    for ann in annotations:

        x, y, w, h = ann["bbox"]

        class_id = ann["class_id"]

        x1 = int(x)
        y1 = int(y)
        x2 = int(x + w)
        y2 = int(y + h)

        label = class_names[class_id]


        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )


        cv2.putText(
            image,
            label,
            (x1, max(25, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )


    # --------------------------------------------------------
    # Add sample information
    # --------------------------------------------------------

    cv2.putText(
        image,
        f"Sample {index}: {record['filename']}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )


    # --------------------------------------------------------
    # Save image
    # --------------------------------------------------------

    output_path = os.path.join(
        OUTPUT_DIR,
        f"sample_{index:03d}_{record['filename']}"
    )


    cv2.imwrite(
        output_path,
        image
    )


    print(
        f"[{index}/{sample_count}] "
        f"{record['filename']}"
    )


print("\n" + "=" * 60)

print("VISUAL REVIEW COMPLETE")

print("=" * 60)

print("\nReview images saved to:")

print(OUTPUT_DIR)

print("\nOpen this folder in VS Code/File Explorer.")

print("Check the bounding boxes and vehicle labels visually.")

print("\nOriginal UVH-26 dataset was NOT modified.")