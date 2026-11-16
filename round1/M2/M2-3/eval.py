from ultralytics import YOLO

if __name__ == '__main__':
    # 加载训练好的最优模型
    model = YOLO("models/best.pt")
    
    # 在验证集上进行评估，输出 mAP、混淆矩阵等
    print("🚀 开始评估模型...")
    metrics = model.val(data="my_data.yaml", split="val")
    
    print("\n✅ 评估完成！")
    print(f"mAP@0.5: {metrics.box.map50:.4f}")
    print(f"mAP@0.5:0.95: {metrics.box.map:.4f}")