from pathlib import Path
import random
import cv2

SOURCE = Path(r"D:\ASTRA\dataset\firetruck_processed")
OUTPUT = SOURCE / "visual_review"

OUTPUT.mkdir(parents=True, exist_ok=True)

random.seed(42)

# Get all train + validation images
images = list((SOURCE / "images" / "train").glob("*"))
images += list((SOURCE / "images" / "val").glob("*"))

# Select 30 random images
samples = random.sample(images, min(30, len(images)))

print("Total images:", len(images))
print("Review samples:", len(samples))

created = 0

for i, image_path in enumerate(samples, start=1):

    # Read image
    image = cv2.imread(str(image_path))

    if image is None:
        print("WARNING: Could not read:", image_path.name)
        continue

    height, width = image.shape[:2]

    # Corresponding label
    label_path = (
        SOURCE
        / "labels"
        / ("train" if "train" in image_path.parts else "val")
        / (image_path.stem + ".txt")
    )

    if not label_path.exists():
        print("WARNING: Missing label:", image_path.name)
        continue

    # Draw every Fire Truck bounding box
    for line in label_path.read_text().splitlines():

        parts = line.split()

        if len(parts) != 5:
            continue

        class_id = int(parts[0])

        x_center = float(parts[1])
        y_center = float(parts[2])
        box_width = float(parts[3])
        box_height = float(parts[4])

        # YOLO normalized -> pixel coordinates
        x1 = int((x_center - box_width / 2) * width)
        y1 = int((y_center - box_height / 2) * height)
        x2 = int((x_center + box_width / 2) * width)
        y2 = int((y_center + box_height / 2) * height)

        # Keep coordinates inside image
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(0, min(x2, width - 1))
        y2 = max(0, min(y2, height - 1))

        # Draw box
        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            3
        )

        # Class label
        cv2.putText(
            image,
            "Fire Truck",
            (x1, max(30, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    output_path = OUTPUT / f"review_{i:02d}.jpg"

    cv2.imwrite(
        str(output_path),
        image
    )

    created += 1


print()
print("==========================================")
print("FIRE TRUCK VISUAL REVIEW COMPLETE")
print("==========================================")
print()
print("Images created:", created)
print("Review folder:")
print(OUTPUT)