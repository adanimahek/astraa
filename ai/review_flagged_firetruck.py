from pathlib import Path
import cv2
import math

SOURCE = Path(
    r"D:\ASTRA\dataset\firetruck_processed\audit\flagged_other_vehicles"
)

OUTPUT = SOURCE / "review_sheets"
OUTPUT.mkdir(parents=True, exist_ok=True)

images = sorted(SOURCE.glob("*"))

print("Flagged images:", len(images))

# 6 images per sheet
cols = 2
rows = 3

thumb_w = 640
thumb_h = 360

for start in range(0, len(images), cols * rows):

    batch = images[start:start + cols * rows]

    sheet = 255 * __import__("numpy").ones(
        (rows * thumb_h, cols * thumb_w, 3),
        dtype="uint8"
    )

    for i, image_path in enumerate(batch):

        image = cv2.imread(str(image_path))

        if image is None:
            continue

        image = cv2.resize(
            image,
            (thumb_w, thumb_h)
        )

        r = i // cols
        c = i % cols

        sheet[
            r * thumb_h:(r + 1) * thumb_h,
            c * thumb_w:(c + 1) * thumb_w
        ] = image

        cv2.putText(
            sheet,
            image_path.name[:35],
            (c * thumb_w + 10, r * thumb_h + 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2
        )

    sheet_number = start // (cols * rows) + 1

    output = OUTPUT / f"sheet_{sheet_number:02d}.jpg"

    cv2.imwrite(
        str(output),
        sheet
    )

print()
print("Review sheets created.")
print("Folder:")
print(OUTPUT)