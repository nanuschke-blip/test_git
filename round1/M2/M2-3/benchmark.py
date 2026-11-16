import time
import cv2
import numpy as np
from ultralytics import YOLO

if __name__ == '__main__':
    # 加载模型（测试 CPU 推理速度）
    model = YOLO("models/best.onnx", task="detect")
    
    # 造一张假图片用来测速
    dummy_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    print("🚀 开始测试 CPU 推理耗时 (预热)...")
    # 预热 5 次，防止第一帧过慢
    for _ in range(5):
        model(dummy_img, verbose=False)
        
    print("⏱️ 开始正式测试 (200 帧)...")
    num_frames = 200
    start_time = time.time()
    
    for _ in range(num_frames):
        _ = model(dummy_img, verbose=False)
        
    total_time = time.time() - start_time
    fps = num_frames / total_time
    
    print("\n✅ 性能测试完成！")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"平均单帧耗时: {(total_time/num_frames)*1000:.2f} ms")
    print(f"平均端到端 FPS: {fps:.2f}")