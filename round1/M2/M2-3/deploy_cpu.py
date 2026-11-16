import cv2
import numpy as np
import onnxruntime as ort
import time

# 1. 加载 ONNX 模型
session = ort.InferenceSession("best.onnx", providers=['CPUExecutionProvider'])
input_name = session.get_inputs()[0].name

# 2. 预处理（极其关键，必须和训练时一致）
def preprocess(img, input_shape=(640, 640)):
    img = cv2.resize(img, input_shape)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1)) # HWC 转 CHW
    img = np.expand_dims(img, axis=0)  # 加 batch 维度
    return img

cap = cv2.VideoCapture(0)
while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    start_time = time.time()
    
    # 推理
    input_tensor = preprocess(frame)
    outputs = session.run(None, {input_name: input_tensor})
    
    # （注：这里为了模板简洁，省去了 NMS 后处理逻辑，你可以先用空列表代替画框演示）
    
    # 计算 FPS
    fps = 1.0 / (time.time() - start_time)
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("CPU Deploy", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break