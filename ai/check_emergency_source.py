from pathlib import Path
from collections import Counter
import yaml

# Original emergency dataset
DATASET = Path(r"D:\ASTRA\dataset\emergency_raw\extracted")

print("=" * 60)
print("ASTRA - EMERGENCY SOURCE DATASET CHECK")
print("=" * 60)

# Read data.yaml
yaml_file = DATASET / "data.yaml"

with open(yaml_file, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

names = data["names"]

print("\nClasses in original emergency dataset:")
for i, name in enumerate(names):
    print(f"{i}: {name}")

# Check train/valid/test labels
total_counts = Counter()

for split in ["train", "valid", "test"]:
    label_dir = DATASET / split / "labels"

    if not label_dir.exists():
        print(f"\n{split}: labels folder not found")
        continue

    counts = Counter()

    for label_file in label_dir.glob("*.txt"):
        with open(label_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()

                if not parts:
                    continue

                try:
                    class_id = int(parts[0])
                    counts[class_id] += 1
                    total_counts[class_id] += 1
                except ValueError:
                    pass

    print(f"\n{split.upper()} annotations:")
    for class_id, count in sorted(counts.items()):
        print(f"  {class_id}: {names[class_id]} -> {count}")

print("\n" + "=" * 60)
print("TOTAL ANNOTATIONS")
print("=" * 60)

for class_id, count in sorted(total_counts.items()):
    print(f"{class_id}: {names[class_id]} -> {count}")

print("\nCheck complete.")