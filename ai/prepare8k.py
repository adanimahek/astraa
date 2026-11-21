import os
import json
import random
import shutil

# ============================================================
# ASTRA - Prepare Selected 8K for YOLO
# ============================================================

SELECTION_JSON = r"D:\ASTRA\dataset\selected_8k\selected_8000.json"

ANNOTATION_JSON = r"D:\ASTRA\dataset\raw\UVH-26\UVH-26-Train\UVH-26-MV-Train.json"

OUTPUT_DIR = r"D:\ASTRA\dataset\traffic_8k"

RANDOM_SEED = 42

TRAIN_RATIO = 0.80


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
# Create directories
# ============================================================

for split in ["train", "val"]:

    os.makedirs(
        os.path.join(
            OUTPUT_DIR,
            "images",
            split
        ),
        exist_ok=True
    )

    os.makedirs(
        os.path.join(
            OUTPUT_DIR,
            "labels",
            split
        ),
        exist_ok=True
    )


# ============================================================
# Load selected 8K
# ============================================================

print("=" * 65)
print("ASTRA - PREPARING 8K YOLO DATASET")
print("=" * 65)

print("\nLoading selected 8K...")

with open(
    SELECTION_JSON,
    "r",
    encoding="utf-8"
) as f:

    selection_data = json.load(f)


selected = selection_data["images"]

print(
    "Selected images:",
    len(selected)
)


# ============================================================
# Load original annotations
# ============================================================

print("\nLoading MV annotations...")

with open(
    ANNOTATION_JSON,
    "r",
    encoding="utf-8"
) as f:

    annotation_data = json.load(f)


# ============================================================
# Image dimensions
# ============================================================

image_dimensions = {}

for image in annotation_data["images"]:

    image_dimensions[
        image["id"]
    ] = (
        image["width"],
        image["height"]
    )


# ============================================================
# Group annotations by image
# ============================================================

print("Preparing annotations...")

annotations_by_image = {}

for ann in annotation_data["annotations"]:

    image_id = ann["image_id"]

    original_class = ann["category_id"]

    if original_class not in class_mapping:
        continue

    if image_id not in annotations_by_image:

        annotations_by_image[image_id] = []

    annotations_by_image[image_id].append(
        {
            "bbox": ann["bbox"],
            "class_id": class_mapping[
                original_class
            ]
        }
    )


# ============================================================
# Split dataset
# ============================================================

print("\nCreating train/validation split...")

random.seed(RANDOM_SEED)

random.shuffle(selected)

train_count = int(
    len(selected) * TRAIN_RATIO
)

train_items = selected[
    :train_count
]

val_items = selected[
    train_count:
]

print(
    "Train images:",
    len(train_items)
)

print(
    "Validation images:",
    len(val_items)
)


# ============================================================
# Convert COCO bbox -> YOLO bbox
# ============================================================

def coco_to_yolo(
    bbox,
    image_width,
    image_height
):

    x, y, width, height = bbox

    x_center = x + width / 2
    y_center = y + height / 2

    x_center /= image_width
    y_center /= image_height

    width /= image_width
    height /= image_height

    return (
        x_center,
        y_center,
        width,
        height
    )


# ============================================================
# Process split
# ============================================================

def process_split(
    items,
    split_name
):

    print(
        f"\nProcessing {split_name}..."
    )

    image_output_dir = os.path.join(
        OUTPUT_DIR,
        "images",
        split_name
    )

    label_output_dir = os.path.join(
        OUTPUT_DIR,
        "labels",
        split_name
    )

    class_counter = {
        class_id: 0
        for class_id in range(
            len(class_names)
        )
    }

    copied_images = 0
    created_labels = 0

    for index, item in enumerate(
        items,
        start=1
    ):

        image_id = item["id"]

        source_path = item["path"]

        filename = item["filename"]

        # ----------------------------------------------------
        # Copy image
        # ----------------------------------------------------

        destination_image = os.path.join(
            image_output_dir,
            filename
        )

        shutil.copy2(
            source_path,
            destination_image
        )

        copied_images += 1

        # ----------------------------------------------------
        # Image dimensions
        # ----------------------------------------------------

        if image_id in image_dimensions:

            image_width, image_height = (
                image_dimensions[image_id]
            )

        else:

            image_width = item["width"]
            image_height = item["height"]

        # ----------------------------------------------------
        # Create YOLO label
        # ----------------------------------------------------

        annotations = annotations_by_image.get(
            image_id,
            []
        )

        label_filename = os.path.splitext(
            filename
        )[0] + ".txt"

        label_path = os.path.join(
            label_output_dir,
            label_filename
        )

        with open(
            label_path,
            "w",
            encoding="utf-8"
        ) as label_file:

            for ann in annotations:

                class_id = ann["class_id"]

                x_center, y_center, width, height = (
                    coco_to_yolo(
                        ann["bbox"],
                        image_width,
                        image_height
                    )
                )

                # Safety clamp
                x_center = min(
                    max(x_center, 0.0),
                    1.0
                )

                y_center = min(
                    max(y_center, 0.0),
                    1.0
                )

                width = min(
                    max(width, 0.0),
                    1.0
                )

                height = min(
                    max(height, 0.0),
                    1.0
                )

                label_file.write(
                    f"{class_id} "
                    f"{x_center:.6f} "
                    f"{y_center:.6f} "
                    f"{width:.6f} "
                    f"{height:.6f}\n"
                )

                class_counter[
                    class_id
                ] += 1

                created_labels += 1

        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        if index % 250 == 0:

            print(
                f"{split_name}: "
                f"{index}/{len(items)}"
            )

    return (
        copied_images,
        created_labels,
        class_counter
    )


# ============================================================
# Process train
# ============================================================

train_results = process_split(
    train_items,
    "train"
)


# ============================================================
# Process validation
# ============================================================

val_results = process_split(
    val_items,
    "val"
)


# ============================================================
# Create data.yaml
# ============================================================

yaml_path = os.path.join(
    OUTPUT_DIR,
    "data.yaml"
)


with open(
    yaml_path,
    "w",
    encoding="utf-8"
) as f:

    f.write(
        f"path: {OUTPUT_DIR}\n"
    )

    f.write(
        "train: images/train\n"
    )

    f.write(
        "val: images/val\n\n"
    )

    f.write(
        f"nc: {len(class_names)}\n"
    )

    f.write(
        "names:\n"
    )

    for class_id, name in enumerate(
        class_names
    ):

        f.write(
            f"  {class_id}: {name}\n"
        )


# ============================================================
# Final report
# ============================================================

print("\n" + "=" * 65)
print("8K YOLO DATASET CREATED")
print("=" * 65)

print(
    "\nTrain images:",
    train_results[0]
)

print(
    "Validation images:",
    val_results[0]
)

print(
    "Total images:",
    train_results[0] + val_results[0]
)

print(
    "\nTrain labels:",
    train_results[1]
)

print(
    "Validation labels:",
    val_results[1]
)

print(
    "\nDataset location:"
)

print(
    OUTPUT_DIR
)

print(
    "\ndata.yaml:"
)

print(
    yaml_path
)

print(
    "\nFinal classes:"
)

for class_id, name in enumerate(
    class_names
):

    print(
        f"{class_id}: {name}"
    )

print(
    "\nOriginal UVH-26 dataset was NOT modified."
)

print(
    "Emergency classes have NOT been added yet."
)

print("\nDONE.")