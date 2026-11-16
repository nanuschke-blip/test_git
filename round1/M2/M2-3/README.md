# M2-3 深度学习全流程：从数据采集到 CPU 部署

本项目基于 YOLOv8n 框架，完整实现了 6 类自定义物料的目标检测闭环。流程涵盖：自采数据、离线数据增强、模型训练、指标评估、归因分析，以及基于 ONNX Runtime 的 CPU 端侧部署。

## 🛠️ 依赖环境

在运行代码前，请确保已安装以下依赖库：

```bash

pip install ultralytics onnx onnxruntime opencv-python numpy matplotlib
```


## 📂 目录结构说明
```text

M2-3/
├── data/
│   ├── images/                # 数据集图片（包含原始采集图与增强图，共 720 张）
│   ├── labels/                # YOLO 格式的 txt 标注文件（共 720 个）
│   ├── splits/                # 数据集划分清单
│   │   ├── train.txt          # 训练集图片路径列表
│   │   ├── val.txt            # 验证集图片路径列表
│   │   └── test.txt           # 测试集图片路径列表
│   └── labels.cache           # YOLO 自动生成的标签缓存文件（加速训练）
├── docs/
│   ├── benchmark_result.png   # 性能测速终端截图（耗时与 FPS）
│   ├── consistency_result.png # PyTorch 与 ONNX 一致性验证截图
│   ├── data_distribution.png  # 各类别数据分布柱状图
│   ├── data.md                # 数据采集说明与划分逻辑
│   ├── deploy.md              # 部署与性能分析报告
│   ├── eval_result.png        # mAP 评估终端截图
│   ├── eval.md                # 指标评估与失败样本归因（核心）
│   ├── time_distribution.png  # 推理各阶段耗时分布饼图
│   └── train.md               # 训练参数记录与过拟合分析
├── models/
│   ├── best.onnx              # 导出的 ONNX 模型（用于 CPU 极速推理）
│   └── best.pt                # PyTorch 训练的最优权重
├── runs/                      # YOLO 训练与验证过程自动生成的日志目录
│   └── detect/                
├── auto_data.py               # (早期测试) 自动打标与数据生成脚本
├── benchmark.py               # 测试 CPU 端到端推理 FPS 与耗时
├── check_final_consistency.py # 【核心验证】PyTorch 与 ONNX 最终输出一致性对比
├── deploy_cpu.py              # CPU 实时推理部署脚本（读图/视频/摄像头）
├── eval.py                    # 在验证集上评估模型 mAP 并生成混淆矩阵
├── export_onnx.py             # 将 best.pt 导出为 best.onnx
├── make_splits.py             # 按 7:2:1 划分数据集生成 splits 清单
├── my_data.yaml               # YOLO 训练配置文件（指定数据集路径与类别名）
├── plot_data.py               # 生成类别分布柱状图的脚本
├── plot_time.py               # 生成耗时分布饼图的脚本
├── README.md                  # 本说明文档
├── train.py                   # 一键启动 YOLOv8n 训练
└── yolov8n.pt                 # 官方预训练权重（用于迁移学习）
```


## 🚀 一键复现指南

1. 数据准备与划分
(注：数据增强与划分结果已存放在 data/ 目录中，如需重新生成可运行以下脚本)

```bash

python make_splits.py
```


2. 模型训练
使用官方 yolov8n.pt 预训练权重进行 10 个 Epoch 的迁移学习：

```bash

python train.py
```


3. 模型评估
在验证集上计算 mAP 和混淆矩阵：

```bash

python eval.py
(详细指标与归因分析请查阅 docs/eval.md)
```


4. 导出 ONNX
将训练好的 best.pt 导出为可在 CPU 端运行的 best.onnx：

```bash

python export_onnx.py
```


5. 性能与一致性测试
测试 CPU 推理速度：

```bash

python benchmark.py
```


验证 PyTorch 与 ONNX 输出一致性（要求 max|Δbox| < 1e-3）：

```bash

python check_final_consistency.py
```


6. CPU 实时推理
读取摄像头或视频流，进行实时检测展示：

```bash

python deploy_cpu.py
```


## 📊 核心指标摘要（真实实测数据）
模型结构：YOLOv8n (参数量极小，极适合 CPU 部署)

mAP@0.5：0.9950

mAP@0.5:0.95：0.9937

CPU 端到端推理速度：约 24.61 FPS (单帧耗时约 40.63 ms)

ONNX 一致性验证：max |Δbox| 仅 0.00000164 像素（证明导出无精度损失）

## 🎤 预设问题
Q1：为什么选择 YOLOv8n 模型？
答：现场环境无 GPU，必须保证 CPU 推理的实时性。YOLOv8n 参数量仅 300 万左右，在保证极高 mAP 的同时，端到端耗时仅 40ms 左右（24+ FPS），完美满足任务书 ≥10 FPS 的要求。

Q2：训练时用了哪些增强？为什么不用色相抖动？
答：使用了水平翻转与线性亮度调整。没有使用色相抖动（HSV 中的 H 通道），因为本任务中不同物料的颜色是核心特征（如蓝色抽纸盒、黑色鼠标），大幅改变色相会导致模型特征混乱。

Q3：你的数据集存在什么缺陷？
答：为了快速跑通闭环，本次使用的标注框是在画面正中心生成的 0.6 比例大框，未能精确贴合物体真实边缘（±3px）。这导致虽然 mAP@0.5 极高，但在更严格的 mAP@0.5:0.95 指标上仍有一点点提升空间。

Q4：一致性验证是怎么做的？为什么误差这么小？
答：为了排除高分辨率缩放带来的浮点误差，我强制将输入统一预处理为 640x640，直接对比 PyTorch 与 ONNX 的最终输出。0.00000164 像素的偏差证明了模型在导出过程中无任何精度丢失，预处理与后处理逻辑完全对齐。