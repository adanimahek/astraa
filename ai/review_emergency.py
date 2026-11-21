from pathlib import Path
import random
import cv2

# ============================================================
# ASTRA EMERGENCY DATASET VISUAL REVIEW
# ============================================================

DATASET = Path(
    r"D:\ASTRA\dataset\emergency_2k"
)

IMAGES_DIR = DATASET / "images"
LABELS_DIR = DATASET / "labels"
OUTPUT_DIR = DATASET / "visual_review"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# Number of random images to review
SAMPLE_COUNT = 40

# Fixed seed for reproducibility
RANDOM_SEED = 42

random.seed(RANDOM_SEED)


# ============================================================
# ASTRA EMERGENCY CLASSES
# ============================================================

CLASS_NAMES = {
    8: "Ambulance",
    9: "Fire Truck"
}


# ============================================================
# FIND ALL IMAGES
# ============================================================

image_files = []

for extension in [
    "*.jpg",
    "*.jpeg",
    "*.png"
]:
    image_files.extend(
        IMAGES_DIR.glob(extension)
    )


print(
    f"Total images found: {len(image_files)}"
)


# ============================================================
# CHECK IMAGE COUNT
# ============================================================

if len(image_files) < SAMPLE_COUNT:

    raise RuntimeError(
        f"Only {len(image_files)} images found. "
        f"Need at least {SAMPLE_COUNT}."
    )


# ============================================================
# SELECT RANDOM SAMPLES
# ============================================================

samples = random.sample(
    image_files,
    SAMPLE_COUNT
)


# ============================================================
# PROCESS SAMPLES
# ============================================================

processed = 0

ambulance_images = 0
fire_truck_images = 0

missing_labels = 0
unreadable_images = 0


for image_path in samples:

    # --------------------------------------------------------
    # Find matching label
    # --------------------------------------------------------

    label_path = (
        LABELS_DIR /
        f"{image_path.stem}.txt"
    )


    if not label_path.exists():

        print(
            f"WARNING: Missing label: "
            f"{image_path.name}"
        )

        missing_labels += 1

        continue


    # --------------------------------------------------------
    # Read image
    # --------------------------------------------------------

    image = cv2.imread(
        str(image_path)
    )


    if image is None:

        print(
            f"WARNING: Cannot read image: "
            f"{image_path.name}"
        )

        unreadable_images += 1

        continue


    image_height, image_width = (
        image.shape[:2]
    )


    # --------------------------------------------------------
    # Read YOLO label
    # --------------------------------------------------------

    try:

        lines = label_path.read_text(
            encoding="utf-8"
        ).splitlines()

    except UnicodeDecodeError:

        lines = label_path.read_text(
            encoding="utf-8-sig"
        ).splitlines()


    image_has_ambulance = False
    image_has_fire_truck = False


    # ========================================================
    # PROCESS EACH BOUNDING BOX
    # ========================================================

    for line in lines:

        parts = line.strip().split()


        # YOLO detection format must contain 5 values
        if len(parts) != 5:
            continue


        try:

            class_id = int(parts[0])

            x_center = float(parts[1])
            y_center = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])

        except ValueError:

            continue


        # Ignore anything except our two emergency classes
        if class_id not in CLASS_NAMES:
            continue


        # ----------------------------------------------------
        # Convert normalized coordinates to pixels
        # ----------------------------------------------------

        x_center_pixel = (
            x_center * image_width
        )

        y_center_pixel = (
            y_center * image_height
        )

        box_width = (
            width * image_width
        )

        box_height = (
            height * image_height
        )


        x1 = int(
            x_center_pixel -
            box_width / 2
        )

        y1 = int(
            y_center_pixel -
            box_height / 2
        )

        x2 = int(
            x_center_pixel +
            box_width / 2
        )

        y2 = int(
            y_center_pixel +
            box_height / 2
        )


        # ----------------------------------------------------
        # Keep box inside image
        # ----------------------------------------------------

        x1 = max(
            0,
            min(image_width - 1, x1)
        )

        y1 = max(
            0,
            min(image_height - 1, y1)
        )

        x2 = max(
            0,
            min(image_width - 1, x2)
        )

        y2 = max(
            0,
            min(image_height - 1, y2)
        )


        # ----------------------------------------------------
        # Track emergency class
        # ----------------------------------------------------

        if class_id == 8:

            image_has_ambulance = True

        elif class_id == 9:

            image_has_fire_truck = True


        # ----------------------------------------------------
        # Box display
        # ----------------------------------------------------

        if class_id == 8:

            # Ambulance
            color = (255, 0, 0)

        else:

            # Fire Truck
            color = (0, 0, 255)


        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            color,
            3
        )


        # ----------------------------------------------------
        # Label text
        # ----------------------------------------------------

        label = CLASS_NAMES[class_id]


        (
            text_width,
            text_height
        ), _ = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            2
        )


        text_y = max(
            y1 - 10,
            text_height + 5
        )


        cv2.rectangle(
            image,

            (
                x1,
                text_y - text_height - 8
            ),

            (
                x1 + text_width + 8,
                text_y
            ),

            color,
            -1
        )


        cv2.putText(
            image,

            label,

            (
                x1 + 4,
                text_y - 4
            ),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.8,

            (255, 255, 255),

            2
        )


    # ========================================================
    # COUNT IMAGE TYPES
    # ========================================================

    if image_has_ambulance:

        ambulance_images += 1


    if image_has_fire_truck:

        fire_truck_images += 1


    # ========================================================
    # ADD HEADER
    # ========================================================

    header = (
        f"ASTRA Emergency Review | "
        f"{processed + 1}/{SAMPLE_COUNT}"
    )


    cv2.putText(
        image,

        header,

        (20, 40),

        cv2.FONT_HERSHEY_SIMPLEX,

        1.0,

        (255, 255, 255),

        3
    )


    # ========================================================
    # SAVE REVIEW IMAGE
    # ========================================================

    output_path = (
        OUTPUT_DIR /
        f"review_{processed + 1:03d}_"
        f"{image_path.name}"
    )


    cv2.imwrite(
        str(output_path),
        image
    )


    processed += 1


# ============================================================
# FINAL RESULT
# ============================================================

print()
print(
    "VISUAL REVIEW COMPLETE"
)

print(
    "----------------------"
)

print(
    f"Samples requested : {SAMPLE_COUNT}"
)

print(
    f"Samples created   : {processed}"
)

print(
    f"Ambulance images  : {ambulance_images}"
)

print(
    f"Fire Truck images : {fire_truck_images}"
)

print(
    f"Missing labels    : {missing_labels}"
)

print(
    f"Unreadable images : {unreadable_images}"
)

print()
print(
    "Review folder:"
)

print(
    OUTPUT_DIR
)