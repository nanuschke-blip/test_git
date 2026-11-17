"""导出 ONNX（给 M2-4 的追踪模块当检测前端用）

用法:
    python export_onnx.py
导出结果会同时拷贝到 models/best.onnx
"""
import os
import shutil

from ultralytics import YOLO

SRC = "runs/detect/runs/detect/train_fixed/weights/best.pt"
DST = "models/best.onnx"


def main():
    if not os.path.exists(SRC):
        raise FileNotFoundError(f"找不到训练权重: {SRC}")
    model = YOLO(SRC)
    path = model.export(format="onnx", imgsz=640, opset=12, simplify=True)
    os.makedirs("models", exist_ok=True)
    shutil.copy(path, DST)
    size = os.path.getsize(DST) / 1024 / 1024
    print(f"[ok] {path} -> {DST}  ({size:.2f} MB)")


if __name__ == "__main__":
    main()
