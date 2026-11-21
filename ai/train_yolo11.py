from ultralytics import YOLO


def main():

    # ============================================================
    # ASTRA - YOLO11 TRAINING
    # Initial 5-epoch GPU test
    # ============================================================

    DATASET = r"D:\ASTRA\dataset\final_9k\data.yaml"

    # YOLO11 small model
    model = YOLO("yolo11s.pt")

    # Test training
    results = model.train(
        data=DATASET,
        epochs=5,
        imgsz=640,
        batch=2,
        device=0,
        workers=2,
        project=r"D:\ASTRA\training",
        name="astra_yolo11s_test",
        exist_ok=True,
        pretrained=True,
        patience=5,
        verbose=True
    )

    print()
    print("======================================")
    print("ASTRA YOLO11s TEST TRAINING COMPLETE")
    print("======================================")
    print()
    print("Training output:")
    print(r"D:\ASTRA\training\astra_yolo11s_test")


if __name__ == "__main__":
    main()