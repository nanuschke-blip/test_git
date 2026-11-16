from ultralytics import YOLO

if __name__ == '__main__':
    # 加载训练好的模型
    model = YOLO("runs/detect/train/weights/best.pt")
    # 导出为 ONNX 格式，确保能在 CPU 上跑
    model.export(format="onnx")