"""M2-3 训练脚本（标签已改为 data/labels_raw 手工标注 → rebuild_dataset.py 重建）

    cd C:\\Users\\AMDI2025\\Desktop\\M2-3
    python train.py
"""
from ultralytics import YOLO

if __name__ == "__main__":
    # 从官方 yolov8n.pt 迁移学习（CPU 也能跑）
    model = YOLO("yolov8n.pt")

    model.train(
        data="my_data.yaml",
        epochs=25,
        imgsz=640,
        batch=8,
        device="cpu",
        workers=4,
        seed=42,
        project="runs/detect",
        name="train_fixed",
        exist_ok=True,
        # 几何增强由 ultralytics 随机生成，标签自动同步；数据集里已自带裁剪缩放增强
        degrees=5.0,
        translate=0.1,
        scale=0.3,
        fliplr=0.5,
        flipud=0.0,
        mosaic=0.5,
        close_mosaic=5,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.4,
        plots=True,
    )
    print("训练结束，权重在 runs/detect/train_fixed/weights/")
