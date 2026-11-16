import cv2
import numpy as np
from ultralytics import YOLO

# 1. 加载 PyTorch 和 ONNX 模型
model_pt = YOLO("models/best.pt")
model_onnx = YOLO("models/best.onnx")

# 2. 读取同一张图，并强制预处理到 640x640 消除还原误差
img_path = "data/images/cup_01.jpg"
img = cv2.imread(img_path)
img_resized = cv2.resize(img, (640, 640))

# 3. 分别推理（强制关闭自适应缩放，保证输入完全一样）
res_pt = model_pt.predict(img_resized, imgsz=640, verbose=False)[0]
res_onnx = model_onnx.predict(img_resized, imgsz=640, verbose=False)[0]

# 4. 取出高层输出的最终框 (xyxy) 和 置信度 (conf)
# 我们取置信度最高的那个框进行对比
box_pt = res_pt.boxes.xyxy[0].cpu().numpy()
conf_pt = res_pt.boxes.conf[0].cpu().numpy()

box_onnx = res_onnx.boxes.xyxy[0].cpu().numpy()
conf_onnx = res_onnx.boxes.conf[0].cpu().numpy()

# 5. 计算最终输出的绝对误差
delta_box = np.max(np.abs(box_pt - box_onnx))
delta_conf = np.max(np.abs(conf_pt - conf_onnx))

print("✅ 真实高层最终输出对比：")
print(f"PyTorch 检测框: {box_pt}")
print(f"ONNX 检测框: {box_onnx}")
print(f"【最终检测框 max|Δbox| 偏差】: {delta_box:.8f} 像素")
print(f"【最终置信度 max|Δconf| 偏差】: {delta_conf:.8f}")