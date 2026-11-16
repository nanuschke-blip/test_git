import os
import cv2
import numpy as np
import random

# 定义类别映射
classes = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
class_map = {name: i for i, name in enumerate(classes)}

img_dir = "data/images"
lbl_dir = "data/labels"

# 目标每类总数：120张
TARGET_PER_CLASS = 120

def augment_image(img):
    """极简且安全的图像增强：只做轻微翻转和亮度调整"""
    # 1. 随机水平翻转
    if random.random() > 0.5:
        img = cv2.flip(img, 1)
    # 2. 随机亮度变化 (范围限制在0.8~1.2，绝对不会过曝变雪花)
    if random.random() > 0.5:
        alpha = random.uniform(0.8, 1.2) # 对比度
        beta = random.uniform(-20, 20)   # 亮度
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
    return img

print("🚀 开始安全的数据增强与自动打标...")

# 统计每个类别的原图数量
class_counts = {c: 0 for c in classes}

# 第一步：只处理原图，生成对应的 txt 标签
for img_name in os.listdir(img_dir):
    if not img_name.endswith(('.jpg', '.png', '.jpeg')) or '_aug' in img_name:
        continue
        
    prefix = img_name.split('_')[0]
    if prefix not in class_map:
        print(f"⚠️ 跳过未知类别: {img_name}")
        continue
        
    class_counts[prefix] += 1
    class_id = class_map[prefix]
    
    # 生成原图的 YOLO 标签 (中心点 0.5, 0.5，宽高 0.6)
    txt_name = img_name.rsplit('.', 1)[0] + ".txt"
    with open(os.path.join(lbl_dir, txt_name), "w") as f:
        f.write(f"{class_id} 0.5 0.5 0.6 0.6\n")

# 第二步：根据实际原图数量，动态补齐增强图
for img_name in os.listdir(img_dir):
    if not img_name.endswith(('.jpg', '.png', '.jpeg')) or '_aug' in img_name:
        continue
        
    prefix = img_name.split('_')[0]
    if prefix not in class_map:
        continue
        
    class_id = class_map[prefix]
    img_path = os.path.join(img_dir, img_name)
    img = cv2.imread(img_path)
    if img is None: continue
    
    # 动态计算需要补充的数量
    need_aug = TARGET_PER_CLASS - class_counts[prefix]
    if need_aug <= 0:
        continue
        
    # 开始批量生成
    for i in range(need_aug):
        aug_img = augment_image(img)
        aug_img_name = f"{prefix}_aug_{i}.jpg"
        cv2.imwrite(os.path.join(img_dir, aug_img_name), aug_img)
        
        aug_txt_name = f"{prefix}_aug_{i}.txt"
        with open(os.path.join(lbl_dir, aug_txt_name), "w") as f:
            f.write(f"{class_id} 0.5 0.5 0.6 0.6\n")

print("✅ 数据增强与自动标注 100% 完成！")
for c in classes:
    print(f" - {c}: 原有 {class_counts[c]} 张，已补齐至 {TARGET_PER_CLASS} 张")