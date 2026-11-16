import os
import random

img_dir = "data/images"
split_dir = "data/splits"
os.makedirs(split_dir, exist_ok=True)

# 获取所有原图（不包含增强图）
all_imgs = [f for f in os.listdir(img_dir) if f.endswith('.jpg') and '_aug' not in f]

# 打乱顺序
random.seed(42)
random.shuffle(all_imgs)

# 按 7:2:1 划分原图
total = len(all_imgs)
train_idx = int(total * 0.7)
val_idx = int(total * 0.9)

train_list = all_imgs[:train_idx]
val_list = all_imgs[train_idx:val_idx]
test_list = all_imgs[val_idx:]

# 【修复点】将增强图全部加入 train_list
aug_imgs = [f for f in os.listdir(img_dir) if f.endswith('.jpg') and '_aug' in f]
train_list.extend(aug_imgs)

# 写入 txt 文件
def write_list(filename, img_list):
    with open(os.path.join(split_dir, filename), 'w') as f:
        for img in img_list:
            f.write(f"data/images/{img}\n")

write_list("train.txt", train_list)
write_list("val.txt", val_list)
write_list("test.txt", test_list)

print(f"✅ 划分完成！Train: {len(train_list)} 张 (含增强), Val: {len(val_list)} 张, Test: {len(test_list)} 张")