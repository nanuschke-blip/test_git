# M2-3 深度学习全流程：数据采集到 CPU 部署

本项目完整实现了 YOLOv8 目标检测的闭环流程，包含 6 类自定义物料的数据采集、自动标注、数据增强、模型训练、指标评估，以及最终的 ONNX CPU 端侧部署。

## 🛠️ 依赖环境

```bash
pip install ultralytics onnx onnxruntime numpy opencv-python
```

## 🚀 一键复现指南
1. 数据集准备
原始实拍数据：位于 data/images/（共 63 张真实场景图）。

数据增强：运行 python auto_data.py，通过翻转与亮度调节，将数据集动态扩充至 720 张，并自动生成 YOLO 格式的标注文件至 data/labels/。

2. 模型训练
运行以下命令，使用官方轻量级 yolov8n.pt 预训练权重进行 10 个 Epoch 的迁移学习：

bash
python train.py
(训练结果保存在 runs/detect/train/weights/best.pt)

3. 模型导出 (CPU)
将 PyTorch 模型导出为 ONNX 格式，以便在无 GPU 环境下极速推理：

bash
python export_onnx.py
(导出结果：models/best.onnx)

4. CPU 实时推理部署
将训练好的 best.onnx 放入 models/ 目录后，运行部署脚本：

bash
python deploy_cpu.py

## 📂 目录结构说明
M2-3/
├── data/
│   ├── images/          # 原始照片与增强后的 720 张图片
│   └── labels/          # YOLO 格式的 txt 标注文件
├── models/
│   ├── best.pt          # PyTorch 训练权重
│   └── best.onnx        # 导出的 CPU 部署模型
├── docs/
│   ├── data.md          # 数据采集与划分说明
│   ├── train.md         # 训练参数与 loss 分析
│   ├── eval.md          # 评估指标与混淆矩阵/失败归因
│   └── deploy.md        # 部署一致性与耗时分析
├── train.py             # 训练脚本
├── export_onnx.py       # 导出脚本
└── README.md            # 本说明文档

## 📊 性能与指标摘要
mAP@0.5: 0.995（极佳精度）

ONNX 模型体积: 12.2 MB

CPU 单帧推理耗时: 约 23.3 ms (轻松满足 ≥15 FPS 的实时性要求)

易混淆类别: 水杯 (cup) 与 水瓶 (bottle)（由于白色圆柱体且高光反射相似，详见 docs/eval.md 归因分析）。

## 🎤 答辩要点
为什么选 YOLOv8n？ 参数量极小（3.1M），CPU 推理速度极快，且能在少量数据下通过预训练权重快速收敛。

数据增强策略：只使用了安全的水平翻转与线性亮度变化。避免了剧烈的色相抖动（因为本任务颜色是强特征）。

如何判断过拟合？ 训练 10 个 epoch 后，验证集的 mAP@0.5 稳定在 0.995，且 val_loss 持续下降，说明模型未出现过拟合。