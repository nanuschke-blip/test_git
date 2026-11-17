# M2-3 深度学习全流程：数据采集 → 标注 → 训练 → 评估 → CPU 部署

基于 YOLOv8n 实现 6 类物料（cup / phone / mouse / bottle / pen / tissue）的目标检测闭环，
在纯 CPU 环境完成 ONNX 部署与精度一致性验证。文档：`docs/data.md`（数据与划分）、
`docs/train.md`（训练与过拟合证据）、`docs/eval.md`（指标 + 混淆矩阵 + 失败样本归因）、
`docs/deploy.md`（部署与性能）。

## 依赖

```bash
pip install ultralytics onnx onnxruntime opencv-python numpy matplotlib
```

## 核心指标（全部本次实测）

| 项目 | 数值 | 产物 |
|---|---|---|
| 验证集 mAP@0.5:0.95 | **0.7668**（P 0.795 / R 1.0 / F1 0.886） | `docs/eval_metrics.json` |
| 测试集 mAP@0.5:0.95 | **0.8292**（6 张，未参与训练/调参，P 0.748 / R 0.833 / F1 0.789） | 同上 |
| 混淆矩阵（val+test，17 实例） | 纯对角，0 次跨类误判，1 次 bottle 漏检 | `docs/confusion_counts.json` |
| 失败样本 | 压力样本 18 次试验 11 次失败，逐张归因 | `docs/failure_cases.png/json` |
| CPU 端到端 | **28.93 ms → 34.57 FPS**（预处理 7.27 + 推理 21.11 + 后处理 0.54） | `docs/benchmark_result.csv` |
| PT ↔ ONNX 一致性 | max\|Δbox\| = **3.05e-5 px**，max\|Δconf\| = 1.25e-6（test 集 5 张） | `docs/consistency_result.json` |
| 增强消融 | 45 张原图 0.7389 → 703 张 0.7668（**+2.79 点**） | `docs/ablation_aug.json` |

> mAP@0.5 在 val/test 上都饱和到 0.995（每类只有 1~3 个实例），没有区分度；全篇判断看
> mAP@0.5:0.95。细节与"为什么"见 `docs/eval.md`。

## 目录结构

```text
M2-3/
├── data/
│   ├── raw/                    # 62 张原始实拍（抽检用，与 images/ 原图内容一致）
│   ├── images/                 # 720 张 = 62 原图 + 658 增强图
│   ├── labels_raw/             # 62 个人工标注（真值，只读）
│   ├── labels/                 # 720 个标签（原图 + 增强图的同步变换）
│   ├── splits/                 # train / val / test / train_orig 清单
│   └── labels.cache            # YOLO 缓存（.gitignore 排除）
├── docs/
│   ├── data.md  train.md  eval.md  deploy.md
│   ├── aug_check.png           # 增强自检（变换后的框）
│   ├── data_distribution.png   # 类别分布 + 标注框尺寸散点
│   ├── loss_curve.png          # 训练/验证 loss + mAP 曲线
│   ├── eval_result.png         # 逐类 mAP 柱状图
│   ├── confusion_matrix_val.png / _test.png   # 混淆矩阵
│   ├── failure_cases.png       # 8 张失败样本（绿 GT / 红预测）
│   ├── time_distribution.png   # 三阶段耗时占比
│   └── *.json                  # 各图的机读数据（eval/benchmark/consistency/ablation/…）
├── models/                     # best.pt / best.onnx
├── label_tool.py               # 交互式标注（COCO 给建议框）
├── rebuild_dataset.py          # 按人工标注重建数据集（划分 + 增强 + 标签同步变换）
├── my_data.yaml                # YOLO 数据配置（指向 splits 清单）
├── my_data_noaug.yaml          # 消融实验配置（只用原图训练，ablation_aug.py 生成）
├── train.py                    # 训练
├── eval.py                     # 评估：逐类 P/R/F1/mAP + 拷混淆矩阵
├── confusion_counts.py         # 混淆矩阵数值
├── stress_failures.py          # 失败样本分析（过曝/遮挡/模糊压力测试 + 归因）
├── analyze_failures.py         # 干净 val/test 上的失败统计（自然失败）
├── ablation_aug.py             # 增强消融实验（长尾处理前后 mAP 差）
├── export_onnx.py              # 导出 ONNX 到 models/best.onnx
├── yolo_onnx.py                # 纯 ONNX Runtime 推理封装（letterbox/解码/NMS）
├── benchmark.py                # 分阶段测速 → JSON + CSV
├── check_final_consistency.py  # PT vs ONNX 一致性（test 集整批）
├── deploy_cpu.py               # 摄像头/视频实时检测
├── plot_data.py plot_time.py plot_eval.py plot_loss.py   # 四张图
├── yolov8n.pt                  # 官方预训练权重（.gitignore 排除）
└── README.md
```

## 复现步骤

```bash
# 1) 标注（62 张；已标过自动跳过）
python label_tool.py

# 2) 重建数据集（7:2:1 划分 + 只对训练集增强 + 标签同步变换 + docs/aug_check.png）
python rebuild_dataset.py

# 3) 训练（第 4 轮后进入平台期，见 docs/train.md）
python train.py
copy runs\detect\runs\detect\train_fixed\weights\best.pt models\best.pt

# 4) 导出与评估
python export_onnx.py
python eval.py                 # 逐类 P/R/F1/mAP，拷混淆矩阵
python confusion_counts.py     # 混淆矩阵数值
python stress_failures.py      # 失败样本 + 归因
python ablation_aug.py         # 增强消融（可选，需重新训 8 轮）

# 5) 测速 / 一致性 / 出图
python benchmark.py && python check_final_consistency.py
python plot_data.py && python plot_time.py && python plot_eval.py && python plot_loss.py

# 6) 实时部署
python deploy_cpu.py --video ..\M2-4\videos\my_scene.mp4
```

## 常见问题

**Q1：为什么选 YOLOv8n？**
现场无 GPU，必须保证 CPU 实时性。YOLOv8n 仅 3.13 M 参数 / 8.6 GFLOPs，实测 28.9 ms/帧
（34.6 FPS），对 ≥10 FPS 有 3.5 倍余量。

**Q2：为什么用人工标注，而不是脚本生成固定框？**
试过固定居中框（`cls 0.5 0.5 0.6 0.6`），模型只学会"永远输出画面正中的大框"，把训练图
原样喂回去也是同一个框——它根本没学定位，换到真实视频上框会套住人的上半身。现在 62 张全部
人工画框，并配"裁剪缩放 + 翻转 + 亮度"且**标签同步变换**的增强。详见 `docs/data.md`。

**Q3：验证集/测试集怎么分？为什么增强图只进训练集？**
按原图分层划分 45/11/6。若先增强再划分，同一张实物照片的翻转副本会同时出现在训练集和
验证集里，指标必然虚高。局限：62 张图只有一种背景，做不到题面要求的"按场景划分"，已写在
`docs/data.md` 与 `docs/eval.md` 的数据缺陷里。

**Q4：mAP@0.5 为什么全是 0.995？**
每类只有 1~3 个实例，IoU>0.5 太宽松，AP 直接饱和。判断依据统一用 mAP@0.5:0.95。

**Q5：ONNX 一致性怎么测的？为什么偏差只有 3e-5？**
取 test 集全部图片，强制预处理到 640×640（排除 letterbox 还原的浮点差异），比较最终输出框
与置信度。1e-5 量级说明导出链路与推理端预处理/后处理完全对齐。

**Q6：失败样本为什么要在压力样本上找？**
干净 val/test 上模型几乎全对（17 个实例只有 1 个漏检），只贴 1 张失败图说明不了问题。按现场
真实退化（过曝/遮挡/模糊）构造样本后，18 次试验出 11 次失败，才能说清"模型为什么在这类
样本上翻车"。逐张原因见 `docs/eval.md` 第 4 节。
