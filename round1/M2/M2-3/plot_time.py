import matplotlib.pyplot as plt
labels = ['Preprocess', 'Inference', 'Postprocess']
times = [5, 23.3, 0.5]
plt.figure(figsize=(6,6))
plt.pie(times, labels=labels, autopct='%1.1f%%', colors=['#ff9999','#66b3ff','#99ff99'])
plt.title('CPU Inference Time Breakdown (Total: 28.8ms)')
plt.savefig('docs/time_distribution.png')
print("✅ 耗时分布图已保存至 docs/time_distribution.png")