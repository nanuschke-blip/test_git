from ultralytics import YOLO

if __name__ == '__main__':
    # 使用官方提供的 yolov8n.pt（最轻量级模型，CPU 跑得动）
    model = YOLO("yolov8n.pt") 
    
    # 训练 10 轮，为了尽快跑通
    results = model.train(data="my_data.yaml", epochs=10, imgsz=640, batch=8)