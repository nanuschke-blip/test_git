import cv2
import numpy as np
import onnxruntime as ort
import torch
from ultralytics import YOLO

# 1. 准备测试图片 (统一尺寸，消除缩放误差)
test_img_path = "data/images/cup_01.jpg" 
img = cv2.imread(test_img_path)
img = cv2.resize(img, (640, 640)) 
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
img_tensor = img_rgb.astype(np.float32) / 255.0
img_tensor = np.transpose(img_tensor, (2, 0, 1))
img_tensor = np.expand_dims(img_tensor, axis=0)

# 2. 纯 PyTorch 裸推理 (只取矩阵)
model_pt = YOLO("models/best.pt").model
model_pt.eval()
with torch.no_grad():
    pt_input = torch.from_numpy(img_tensor)
    pt_output = model_pt(pt_input)[0].numpy()

# 3. 纯 ONNX 裸推理 (只取矩阵)
session = ort.InferenceSession("models/best.onnx", providers=['CPUExecutionProvider'])
input_name = session.get_inputs()[0].name
onnx_output = session.run(None, {input_name: img_tensor})[0]

# 4. 对比底层矩阵
diff = np.abs(pt_output.flatten() - onnx_output.flatten())
max_diff = np.max(diff)
mean_diff = np.mean(diff)

print(f"底层矩阵最大绝对偏差 max|Δ|: {max_diff:.8f}")
print(f"底层矩阵平均绝对偏差 mean|Δ|: {mean_diff:.8f}")

if max_diff < 1e-3:
    print("🎉 完美！底层误差极小，绝对达标！")