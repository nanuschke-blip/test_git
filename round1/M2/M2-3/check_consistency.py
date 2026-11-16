import os
import cv2
import numpy as np
from ultralytics import YOLO

# 1. 加载 PyTorch 模型和 ONNX 模型
model_pt = YOLO("models/best.pt")
model_onnx = YOLO("models/best.onnx")

# 2. 随便挑一张图测试
test_img_path = "data/images/cup_1.jpg"
if not os.path.exists(test_img_path):
    # 如果没找到，就取 images 文件夹里的第一张图
    test_img_path = os.path.join("data/images", os.listdir("data/images")[0])

# 3. 分别进行推理
res_pt = model_pt(test_img_path, verbose=False)[0]
res_onnx = model_onnx(test_img_path, verbose=False)[0]

# 4. 提取预测框和置信度
# 注意：这里为了对比简单，我们只看第一个预测框
if len(res_pt.boxes) > 0 and len(res_onnx.boxes) > 0:
    box_pt = res_pt.boxes.xyxy[0].cpu().numpy()
    conf_pt = res_pt.boxes.conf[0].cpu().numpy()

    box_onnx = res_onnx.boxes.xyxy[0].cpu().numpy()
    conf_onnx = res_onnx.boxes.conf[0].cpu().numpy()

    # 5. 计算最大绝对差异
    delta_box = np.max(np.abs(box_pt - box_onnx))
    delta_conf = np.max(np.abs(conf_pt - conf_onnx))

    print("✅ 一致性验证结果：")
    print(f"最大检测框坐标偏差 max|Δbox|: {delta_box:.6f}")
    print(f"最大置信度偏差 max|Δconf|: {delta_conf:.6f}")
else:
    print("❌ 图片中未检测到目标，请换一张图片测试。")