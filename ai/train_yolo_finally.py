from ultralytics import YOLO
import shutil
import os


def main():

    # ============================================================
    # ASTRA - YOLO11s
    # ADDITIONAL 50-EPOCH TRAINING
    # Starting from the existing 5-epoch best.pt
    # ============================================================

    DATASET = r"D:\ASTRA\dataset\final_9k\data.yaml"

    # Existing 5-epoch best model
    START_MODEL = (
        r"D:\ASTRA\training\astra_yolo11s_test"
        r"\weights\best.pt"
    )

    # New training output
    PROJECT_DIR = r"D:\ASTRA\training"
    RUN_NAME = "astra_yolo11s_additional50"

    # ============================================================
    # LOAD 5-EPOCH MODEL
    # ============================================================

    print("Loading existing 5-epoch best.pt...")
    print(START_MODEL)

    model = YOLO(START_MODEL)

    # ============================================================
    # TRAIN FOR 50 ADDITIONAL EPOCHS
    # ============================================================

    results = model.train(
        data=DATASET,

        # Training
        epochs=50,
        imgsz=640,
        batch=2,

        # GPU
        device=0,

        # Windows
        workers=2,

        # Separate output folder
        project=PROJECT_DIR,
        name=RUN_NAME,
        exist_ok=True,

        # Start a new training run from best.pt
        resume=False,

        # Validation
        val=True,

        # Save checkpoints
        save=True,
        save_period=5,

        # Early stopping
        patience=20,

        # Memory
        cache=False,

        # Reproducibility
        seed=42,
        deterministic=True,

        # Fine-tuning learning rate
        lr0=0.001,
        lrf=0.01,

        # Regularization
        weight_decay=0.0005,

        # Learning-rate schedule
        cos_lr=True,

        # Warmup
        warmup_epochs=3,

        # Generate plots
        plots=True,

        verbose=True
    )

    # ============================================================
    # CREATE UNIQUELY NAMED FINAL MODEL
    # ============================================================

    trained_best = (
        r"D:\ASTRA\training\astra_yolo11s_additional50"
        r"\weights\best.pt"
    )

    final_model = (
        r"D:\ASTRA\training"
        r"\ASTRA_YOLO11s_5plus50_best.pt"
    )

    if os.path.exists(trained_best):

        shutil.copy2(
            trained_best,
            final_model
        )

        print()
        print("==============================================")
        print("ASTRA ADDITIONAL 50-EPOCH TRAINING COMPLETE")
        print("==============================================")
        print()
        print("Starting model:")
        print(START_MODEL)
        print()
        print("New best.pt:")
        print(trained_best)
        print()
        print("Final named model:")
        print(final_model)
        print()
        print("Total effective training: 5 + 50 = 55 epochs")
        print("==============================================")

    else:

        print()
        print("ERROR: New best.pt was not found.")
        print(trained_best)


if __name__ == "__main__":
    main()