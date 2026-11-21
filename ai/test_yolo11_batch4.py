from ultralytics import YOLO
from pathlib import Path
import torch


def main():

    # ============================================================
    # ASTRA - YOLO11s BATCH 4 TEST
    # 2 EPOCHS
    # ============================================================

    DATASET = Path(
        r"D:\ASTRA\dataset\final_9833"
    )

    DATA_YAML = DATASET / "data.yaml"

    PROJECT_DIR = Path(
        r"D:\ASTRA\training"
    )

    RUN_NAME = "ASTRA_YOLO11s_batch4_2epoch_test"


    # ============================================================
    # SETTINGS
    # ============================================================

    EPOCHS = 2
    IMGSZ = 640
    BATCH = 4

    # IMPORTANT FOR WINDOWS + 8 GB RAM
    WORKERS = 0

    DEVICE = 0
    CACHE = False


    # ============================================================
    # START
    # ============================================================

    print()
    print("============================================================")
    print("ASTRA YOLO11s - BATCH 4 TEST")
    print("============================================================")
    print()

    print("Dataset:")
    print(DATASET)

    print()
    print("data.yaml:")
    print(DATA_YAML)


    # ============================================================
    # DATASET CHECK
    # ============================================================

    if not DATASET.exists():

        raise RuntimeError(
            f"Dataset not found:\n{DATASET}"
        )

    if not DATA_YAML.exists():

        raise RuntimeError(
            f"data.yaml not found:\n{DATA_YAML}"
        )


    # ============================================================
    # GPU CHECK
    # ============================================================

    print()
    print("============================================================")
    print("GPU CHECK")
    print("============================================================")

    print(
        "CUDA available:",
        torch.cuda.is_available()
    )

    if not torch.cuda.is_available():

        raise RuntimeError(
            "CUDA is not available."
        )

    print(
        "GPU:",
        torch.cuda.get_device_name(0)
    )

    print(
        "CUDA version:",
        torch.version.cuda
    )


    # ============================================================
    # LOAD YOLO11s
    # ============================================================

    print()
    print("============================================================")
    print("LOADING YOLO11s")
    print("============================================================")

    model = YOLO("yolo11s.pt")

    print()
    print("YOLO11s loaded successfully.")


    # ============================================================
    # CONFIGURATION
    # ============================================================

    print()
    print("============================================================")
    print("TEST CONFIGURATION")
    print("============================================================")

    print()
    print("Epochs:", EPOCHS)
    print("Image size:", IMGSZ)
    print("Batch size:", BATCH)
    print("Workers:", WORKERS)
    print("Device:", DEVICE)
    print("Cache:", CACHE)
    print("AMP:", True)

    print()
    print("Output:")
    print(
        PROJECT_DIR / RUN_NAME
    )


    # ============================================================
    # TRAIN
    # ============================================================

    print()
    print("============================================================")
    print("STARTING 2-EPOCH BATCH 4 TEST")
    print("============================================================")
    print()

    results = model.train(

        # Dataset
        data=str(DATA_YAML),

        # 2 epochs
        epochs=EPOCHS,

        # Resolution
        imgsz=IMGSZ,

        # TEST BATCH
        batch=BATCH,

        # NVIDIA GPU
        device=DEVICE,

        # IMPORTANT:
        # No multiprocessing on Windows
        workers=WORKERS,

        # Pretrained YOLO11s
        pretrained=True,

        # Mixed precision
        amp=True,

        # No RAM caching
        cache=CACHE,

        # Validation
        val=True,

        # Save model
        save=True,

        # Output
        project=str(PROJECT_DIR),

        name=RUN_NAME,

        exist_ok=True,

        # Reproducibility
        seed=42,

        deterministic=False,

        # Optimizer
        optimizer="auto",

        # Augmentation
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,

        degrees=5.0,
        translate=0.1,
        scale=0.5,

        shear=0.0,
        perspective=0.0,

        flipud=0.0,
        fliplr=0.5,

        mosaic=1.0,
        mixup=0.0,
        copy_paste=0.0,

        close_mosaic=0,

        plots=True,

        verbose=True
    )


    # ============================================================
    # TEST COMPLETE
    # ============================================================

    print()
    print("============================================================")
    print("BATCH 4 TEST COMPLETE")
    print("============================================================")
    print()

    RUN_FOLDER = (
        PROJECT_DIR / RUN_NAME
    )

    BEST_MODEL = (
        RUN_FOLDER
        / "weights"
        / "best.pt"
    )

    LAST_MODEL = (
        RUN_FOLDER
        / "weights"
        / "last.pt"
    )

    print("Training folder:")
    print(RUN_FOLDER)

    print()

    if BEST_MODEL.exists():

        print("best.pt created:")
        print(BEST_MODEL)

    else:

        print("best.pt was not found.")

    print()

    if LAST_MODEL.exists():

        print("last.pt created:")
        print(LAST_MODEL)

    else:

        print("last.pt was not found.")

    print()
    print("============================================================")
    print("BATCH 4 TEST FINISHED")
    print("============================================================")


# ============================================================
# VERY IMPORTANT FOR WINDOWS
# ============================================================

if __name__ == "__main__":
    main()