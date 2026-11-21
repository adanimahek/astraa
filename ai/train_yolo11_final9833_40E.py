from ultralytics import YOLO
from pathlib import Path
import torch
import shutil


# ============================================================
# ASTRA - FINAL YOLO11s TRAINING
# 9,833 IMAGE DATASET
# 40 EPOCHS / BATCH 4
# ============================================================
#
# Dataset:
# D:\ASTRA\dataset\final_9833
#
# Classes:
# 0  Car
# 1  Bus
# 2  Truck
# 3  2-Wheeler
# 4  3-Wheeler
# 5  Tempo/Van
# 6  Bicycle
# 7  Other
# 8  Ambulance
# 9  Fire Truck
#
# IMPORTANT:
# This starts fresh from official YOLO11s pretrained weights.
# It does NOT use the previous ASTRA best.pt.
# ============================================================


def main():

    # ========================================================
    # PATHS
    # ========================================================

    DATASET = Path(
        r"D:\ASTRA\dataset\final_9833"
    )

    DATA_YAML = DATASET / "data.yaml"

    PROJECT_DIR = Path(
        r"D:\ASTRA\training"
    )

    RUN_NAME = (
        "ASTRA_YOLO11s_FINAL_9833_40E"
    )

    RUN_DIR = (
        PROJECT_DIR / RUN_NAME
    )


    # ========================================================
    # TRAINING SETTINGS
    # ========================================================

    EPOCHS = 40

    IMGSZ = 640

    # Batch 4 was successfully tested
    BATCH = 4

    # Windows + 8 GB RAM
    WORKERS = 0

    # NVIDIA GPU
    DEVICE = 0

    # Do not load the entire dataset into RAM
    CACHE = False


    # ========================================================
    # START
    # ========================================================

    print()
    print("=" * 60)
    print("ASTRA FINAL YOLO11s TRAINING")
    print("=" * 60)
    print()

    print("Dataset:")
    print(DATASET)

    print()
    print("data.yaml:")
    print(DATA_YAML)

    print()
    print("Training output:")
    print(RUN_DIR)


    # ========================================================
    # STEP 1 - DATASET CHECK
    # ========================================================

    print()
    print("=" * 60)
    print("DATASET CHECK")
    print("=" * 60)

    if not DATASET.exists():

        raise RuntimeError(
            f"Dataset not found:\n{DATASET}"
        )

    if not DATA_YAML.exists():

        raise RuntimeError(
            f"data.yaml not found:\n{DATA_YAML}"
        )

    print()
    print("Dataset found.")
    print("data.yaml found.")


    # ========================================================
    # STEP 2 - GPU CHECK
    # ========================================================

    print()
    print("=" * 60)
    print("GPU CHECK")
    print("=" * 60)
    print()

    cuda_available = (
        torch.cuda.is_available()
    )

    print(
        "CUDA available:",
        cuda_available
    )

    if not cuda_available:

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

    # Display GPU memory
    total_memory = (
        torch.cuda.get_device_properties(0)
        .total_memory
        / (1024 ** 3)
    )

    print(
        f"GPU VRAM: {total_memory:.2f} GB"
    )


    # ========================================================
    # STEP 3 - TRAINING CONFIGURATION
    # ========================================================

    print()
    print("=" * 60)
    print("TRAINING CONFIGURATION")
    print("=" * 60)
    print()

    print("Model: YOLO11s")
    print("Dataset: final_9833")
    print("Epochs:", EPOCHS)
    print("Image size:", IMGSZ)
    print("Batch size:", BATCH)
    print("Workers:", WORKERS)
    print("Device:", DEVICE)
    print("AMP:", True)
    print("Cache:", CACHE)

    print()
    print("Classes:")
    print("0  Car")
    print("1  Bus")
    print("2  Truck")
    print("3  2-Wheeler")
    print("4  3-Wheeler")
    print("5  Tempo/Van")
    print("6  Bicycle")
    print("7  Other")
    print("8  Ambulance")
    print("9  Fire Truck")


    # ========================================================
    # STEP 4 - LOAD PRETRAINED YOLO11s
    # ========================================================

    print()
    print("=" * 60)
    print("LOADING YOLO11s")
    print("=" * 60)
    print()

    print(
        "Loading official pretrained YOLO11s..."
    )

    model = YOLO(
        "yolo11s.pt"
    )

    print()
    print(
        "YOLO11s loaded successfully."
    )


    # ========================================================
    # STEP 5 - START TRAINING
    # ========================================================

    print()
    print("=" * 60)
    print("STARTING FINAL 40-EPOCH TRAINING")
    print("=" * 60)
    print()

    print(
        "Expected training duration: "
        "approximately 2-4 hours."
    )

    print(
        "Actual time depends on GPU load, "
        "disk speed and validation time."
    )

    print()


    results = model.train(

        # ----------------------------------------------------
        # DATASET
        # ----------------------------------------------------

        data=str(
            DATA_YAML
        ),

        # ----------------------------------------------------
        # TRAINING
        # ----------------------------------------------------

        epochs=EPOCHS,

        imgsz=IMGSZ,

        batch=BATCH,

        # ----------------------------------------------------
        # HARDWARE
        # ----------------------------------------------------

        device=DEVICE,

        workers=WORKERS,

        # ----------------------------------------------------
        # PRETRAINED YOLO11s
        # ----------------------------------------------------

        pretrained=True,

        # ----------------------------------------------------
        # MIXED PRECISION
        # ----------------------------------------------------

        amp=True,

        # ----------------------------------------------------
        # MEMORY
        # ----------------------------------------------------

        cache=CACHE,

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        val=True,

        # ----------------------------------------------------
        # SAVE MODELS
        # ----------------------------------------------------

        save=True,

        save_period=10,

        # ----------------------------------------------------
        # EARLY STOPPING
        # ----------------------------------------------------

        patience=20,

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        project=str(
            PROJECT_DIR
        ),

        name=RUN_NAME,

        exist_ok=True,

        # ----------------------------------------------------
        # REPRODUCIBILITY
        # ----------------------------------------------------

        seed=42,

        deterministic=False,

        # ----------------------------------------------------
        # OPTIMIZER
        # ----------------------------------------------------

        optimizer="auto",

        # ----------------------------------------------------
        # DATA AUGMENTATION
        # ----------------------------------------------------

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

        # Disable mosaic for final 10 epochs
        # to improve final localization
        close_mosaic=10,

        # ----------------------------------------------------
        # PLOTS
        # ----------------------------------------------------

        plots=True,

        verbose=True
    )


    # ========================================================
    # STEP 6 - CHECK BEST MODEL
    # ========================================================

    print()
    print("=" * 60)
    print("TRAINING FINISHED")
    print("=" * 60)
    print()

    BEST_MODEL = (
        RUN_DIR
        / "weights"
        / "best.pt"
    )

    LAST_MODEL = (
        RUN_DIR
        / "weights"
        / "last.pt"
    )

    print("Training folder:")
    print(RUN_DIR)

    print()

    if BEST_MODEL.exists():

        print(
            "best.pt FOUND:"
        )

        print(
            BEST_MODEL
        )

    else:

        raise RuntimeError(
            "best.pt was not found."
        )

    print()

    if LAST_MODEL.exists():

        print(
            "last.pt FOUND:"
        )

        print(
            LAST_MODEL
        )


    # ========================================================
    # STEP 7 - FINAL VALIDATION
    # ========================================================

    print()
    print("=" * 60)
    print("FINAL VALIDATION")
    print("=" * 60)
    print()

    print(
        "Loading best.pt..."
    )

    best_model = YOLO(
        str(BEST_MODEL)
    )


    validation_results = (
        best_model.val(

            data=str(
                DATA_YAML
            ),

            imgsz=IMGSZ,

            # Safe validation batch
            batch=2,

            device=DEVICE,

            plots=True
        )
    )


    # ========================================================
    # STEP 8 - PRINT FINAL METRICS
    # ========================================================

    print()
    print("=" * 60)
    print("FINAL MODEL RESULTS")
    print("=" * 60)
    print()

    print(
        f"Precision : "
        f"{validation_results.box.mp:.4f}"
    )

    print(
        f"Recall    : "
        f"{validation_results.box.mr:.4f}"
    )

    print(
        f"mAP50     : "
        f"{validation_results.box.map50:.4f}"
    )

    print(
        f"mAP50-95  : "
        f"{validation_results.box.map:.4f}"
    )


    # ========================================================
    # STEP 9 - PER-CLASS RESULTS
    # ========================================================

    print()
    print("=" * 60)
    print("PER-CLASS RESULTS")
    print("=" * 60)
    print()

    for i, class_id in enumerate(
        validation_results.box.ap_class_index
    ):

        class_id = int(
            class_id
        )

        class_name = (
            validation_results.names[
                class_id
            ]
        )

        precision = (
            validation_results.box.p[i]
        )

        recall = (
            validation_results.box.r[i]
        )

        map50 = (
            validation_results.box.ap50[i]
        )

        map5095 = (
            validation_results.box.ap[i]
        )

        print(
            f"{class_name:<15}"
            f"P={precision:.3f}  "
            f"R={recall:.3f}  "
            f"mAP50={map50:.3f}  "
            f"mAP50-95={map5095:.3f}"
        )


    # ========================================================
    # STEP 10 - SAVE METRICS REPORT
    # ========================================================

    metrics_file = (
        RUN_DIR
        / "final_metrics.txt"
    )

    with open(
        metrics_file,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "ASTRA YOLO11s FINAL 9833 METRICS\n"
        )

        file.write(
            "=================================\n\n"
        )

        file.write(
            f"Precision: "
            f"{validation_results.box.mp:.4f}\n"
        )

        file.write(
            f"Recall: "
            f"{validation_results.box.mr:.4f}\n"
        )

        file.write(
            f"mAP50: "
            f"{validation_results.box.map50:.4f}\n"
        )

        file.write(
            f"mAP50-95: "
            f"{validation_results.box.map:.4f}\n"
        )

        file.write(
            "\nPER-CLASS RESULTS\n"
        )

        file.write(
            "-----------------\n"
        )

        for i, class_id in enumerate(
            validation_results.box.ap_class_index
        ):

            class_id = int(
                class_id
            )

            class_name = (
                validation_results.names[
                    class_id
                ]
            )

            file.write(
                f"{class_name:<15}"
                f"P={validation_results.box.p[i]:.3f}  "
                f"R={validation_results.box.r[i]:.3f}  "
                f"mAP50={validation_results.box.ap50[i]:.3f}  "
                f"mAP50-95={validation_results.box.ap[i]:.3f}\n"
            )


    print()
    print(
        "Metrics report saved:"
    )

    print(
        metrics_file
    )


    # ========================================================
    # STEP 11 - CREATE UNIQUELY NAMED FINAL MODEL
    # ========================================================

    FINAL_MODEL = (
        PROJECT_DIR
        /
        "ASTRA_YOLO11s_FINAL_9833_best.pt"
    )

    shutil.copy2(
        BEST_MODEL,
        FINAL_MODEL
    )


    print()
    print("=" * 60)
    print("FINAL MODEL CREATED")
    print("=" * 60)
    print()

    print(
        "Final model:"
    )

    print(
        FINAL_MODEL
    )

    print()
    print(
        "This is the model to use for ASTRA."
    )

    print()
    print(
        "It can be used for:"
    )

    print(
        "1. Image detection"
    )

    print(
        "2. Video detection"
    )

    print(
        "3. Vehicle counting"
    )

    print(
        "4. Ambulance detection"
    )

    print(
        "5. Fire Truck detection"
    )

    print(
        "6. ASTRA traffic-management pipeline"
    )

    print()
    print("=" * 60)
    print("ASTRA TRAINING COMPLETE")
    print("=" * 60)


# ============================================================
# WINDOWS ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()