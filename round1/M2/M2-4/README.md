# M2-4 多目标追踪与运动预测

在 M2-3 训练好的 YOLOv8n 之上，自己实现**卡尔曼滤波 + 匈牙利匹配**的多目标追踪：
ID 保持、遮挡预测、运动估计、轨迹与位移可视化，并与纯 IoU 基线做对照实验。

- 算法、参数推导、实测数据、局限：见 **[report.md](report.md)**
- 一句话结论（84.7 s / 2541 帧素材）：卡尔曼把**同一物体两条 ID 的帧-对**从 25 降到 **6**、
  分配 ID 从 17 降到 **15**、静止目标框的帧间位移方差从 0.082 降到 **0.030 px²（−63%）**，
  代价是 1.24 px 平滑滞后；遮挡 ≤10 帧 ID 保持率 **100%**，人工遮挡 15 帧起归零。
- 交叉情节：第 43~45 秒手机从杯子前面穿过，两框峰值 IoU 0.90，两个 ID 没有互换；
  但两框**连续重叠只有约 1.2 s**（传递过程约 2.5 s，检测在反光/遮挡边缘会断续），
  短于题面的 3 s——这条局限已写进 report 第 14 节。

## 依赖

```bash
pip install opencv-python numpy scipy filterpy matplotlib
# 生成检测序列 / 实时模式还需要（M2-3 的推理栈）：
pip install ultralytics onnxruntime
```

## 目录结构

```text
M2-4/
├── detections/
│   ├── my_scene.json            # 逐帧检测（conf=0.5, NMS=0.45），下游全部复用
│   └── my_scene_lowconf.json    # 低阈值原始检测（conf=0.15），只用于阈值扫描
├── models/
│   └── best.onnx                # 复用 M2-3 的 YOLOv8n（12.2 MB，CPU 推理）
├── videos/
│   └── my_scene.mp4             # 实拍 84.7 s / 2541 帧 / 1280x720 @30fps
├── results/
│   ├── tracked.mp4              # 【核心交付】追踪结果（绿实线=更新, 黄虚线=预测, 青细框=下一帧）
│   ├── iou_only.mp4             # 纯 IoU 基线（.gitignore 排除，可脚本重生成）
│   ├── compare.csv              # 卡尔曼 vs 纯 IoU 的逐项指标
│   ├── occlusion_bench.csv      # 人工遮挡 5/10/15/20 帧的保持率与误差
│   ├── occlusion_curve.png      # 【交付】遮挡帧数 vs 保持率/逐帧误差
│   ├── occlusion_natural.png    # 自然断档回放曲线（补充材料）
│   ├── max_age_sweep.csv        # max_age=5/10/20 的权衡（含身份顶替次数）
│   ├── conf_sweep.csv           # 检测阈值扫描
│   ├── prediction_sim.png/json  # 受控仿真：不同速度下卡尔曼 vs 原地保持
│   ├── noise_params.json        # derive_noise.py 实测出的 R / sigma_a
│   ├── eval_summary.json        # 评测机读结果
│   ├── synthetic_check.txt      # 合成序列自检明细
│   ├── demo_1..5_*.png          # 关键帧（多目标/交叉/遮挡/重入/静止）
│   ├── demo_picks.json          # 每张图取自第几帧、为什么选它
│   └── track_log.json           # 每帧航迹状态（截图脚本依赖）
├── detector_adapter.py          # 视频 -> 检测 JSON（conf / NMS 阈值可调）
├── yolo_onnx.py                 # 纯 ONNX Runtime 推理封装（来自 M2-3，实时模式用）
├── derive_noise.py              # 从检测序列反推 Q/R（滑窗残差 + 二次拟合加速度）
├── tracker.py                   # 【核心】追踪主程序：读 JSON 或接实时检测
├── compare_iou_only.py          # 纯 IoU 基线（无运动模型）
├── evaluate_tracking.py         # 伪真值 + 指标 + 自然断档曲线
├── occlusion_bench.py           # 人工遮挡实验 + max_age 权衡
├── capture_demos.py             # 自动挑关键帧
├── sweep_conf.py                # 检测阈值扫描
├── simulate_prediction_bench.py # 受控仿真（匀速 + 高斯噪声）
├── test_tracker_synthetic.py    # 合成序列自检（断言状态机）
├── record_video.py              # 采集脚本
├── report.md                    # 实现报告
└── README.md
```

## 一键复现

```bash
# 0) 检测（若 detections/*.json 已存在可跳过）
python detector_adapter.py --conf 0.5 --iou 0.45
python detector_adapter.py --conf 0.15 --iou 0.45 --out detections/my_scene_lowconf.json

# 1) 参数与依据
python derive_noise.py        # -> results/noise_params.json
python sweep_conf.py          # -> results/conf_sweep.csv

# 2) 追踪与基线
python tracker.py             # -> results/tracked.mp4
python compare_iou_only.py    # -> results/iou_only.mp4

# 3) 评测与出图
python evaluate_tracking.py   # -> compare.csv / occlusion_natural.png
python occlusion_bench.py     # -> occlusion_bench.csv / occlusion_curve.png / max_age_sweep.csv
python capture_demos.py       # -> results/demo_*.png

# 4) 自检
python simulate_prediction_bench.py
python test_tracker_synthetic.py
```

## 实时模式（现场用遮挡物演示）

```bash
python tracker.py --source 0                          # 摄像头
python tracker.py --source videos/my_scene.mp4        # 跑视频
python tracker.py --source 0 --dump-json detections/live.json   # 顺便存检测
```

按键 `q` 退出。实时模式走的是 M2-3 的 ONNX 检测器，与离线 JSON 通道共用同一套关联/滤波
代码（`process_frame`），两条路行为一致。

## 画面读法

| 元素 | 含义 |
|---|---|
| 绿色实线框 + `ID n cls conf` | 本帧被检测更新 |
| 黄色虚线框 + `PREDICTED ID n k=` | 本帧没检测到，框是盲推的（≤10 帧） |
| 青色细框 + `NEXT n` | 下一帧的预测位置（有检测时也画） |
| 绿色尾迹 | 该 ID 的实测中心历史（指数平滑） |
| `disp Npx` | 从进入画面到当前位置的像素位移 |

## 关键设计点

1. **检测与追踪解耦**：检测算一次落盘，调参/对比都是毫秒级重算。
2. **Q/R 实测**：滑窗残差估 R、二次拟合估加速度（σ_a），不是手凑常数。
3. **自适应 R**：IoU 低/置信度低 → R 放大 → 自动少信这次观测（机制见 report 第 6 节）。
4. **真虚线**：`dashed_rect()` 逐段画，`cv2.rectangle` 画不出虚线。
5. **两级匹配 + 重复检测抑制**：先同类匈牙利；只剩孤立检测时，才允许与"正在预测态"的航迹
   跨类配对（IoU≥0.8，类别抖动救援）。NMS 收到 0.45、追踪层同类 IoU>0.6 不再开新航迹，
   否则一个物体会被两条 ID 抢。
6. **ID 单调递增不回收**，`test_tracker_synthetic.py` 有断言。
