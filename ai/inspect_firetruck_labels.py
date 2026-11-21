from pathlib import Path

SOURCE = Path(r"D:\ASTRA\dataset\firetruck_raw")

bbox = 0
polygon = 0
other = 0
empty = 0

examples = {}

for split in ["train", "valid", "test"]:

    label_dir = SOURCE / split / "labels"

    for f in label_dir.glob("*.txt"):

        text = f.read_text().strip()

        if not text:
            empty += 1
            continue

        file_type = None

        for line in text.splitlines():

            parts = line.strip().split()

            if len(parts) == 5:
                file_type = "bbox"

            elif len(parts) >= 7 and (len(parts) - 1) % 2 == 0:
                file_type = "polygon"

            else:
                file_type = "other"

            break

        if file_type == "bbox":
            bbox += 1
            examples.setdefault("bbox", f.name)

        elif file_type == "polygon":
            polygon += 1
            examples.setdefault("polygon", f.name)

        else:
            other += 1
            examples.setdefault("other", f.name)


print()
print("==========================================")
print("FIRE TRUCK LABEL FORMAT INSPECTION")
print("==========================================")
print()
print("Total label files:", bbox + polygon + other + empty)
print("Bounding-box files:", bbox)
print("Polygon files:", polygon)
print("Other files:", other)
print("Empty files:", empty)
print()
print("Examples:")
print(examples)