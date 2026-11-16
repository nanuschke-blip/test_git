import matplotlib.pyplot as plt
classes = ['cup', 'phone', 'mouse', 'bottle', 'pen', 'tissue']
counts = [120, 120, 120, 120, 120, 120]  # 每类120张
plt.figure(figsize=(8,5))
plt.bar(classes, counts, color='skyblue')
plt.title('Dataset Class Distribution')
plt.xlabel('Classes')
plt.ylabel('Number of Images')
plt.savefig('docs/data_distribution.png')
print("✅ 类别分布图已保存至 docs/data_distribution.png")