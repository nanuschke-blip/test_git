# M2-2 单目视觉位姿估计（6-DoF）

本项目基于单目相机与平面棋盘格靶标，利用 PnP（Perspective-n-Point）算法，实现了从 2D 图像像素到 3D 空间位姿（位置 + 姿态）的高精度解算与实时可视化。

## 🛠️ 依赖环境

在运行代码前，请确保已安装 Python 3.10+ 及以下依赖库：

```bash
pip install opencv-python numpy pyyaml 
```
pyyaml

## 运行说明

重要提示：本程序严格复用 M2-1 阶段同一台相机的标定结果 camera_calibration.yaml，禁止重新标定，禁止写死内参。

模式 A：实时摄像头检测（默认）
```bash
python pose_estimate.py -c camera_calibration.yaml -s
```
(运行后，将靶标置于镜头前，按 q 键退出)

模式 B：单张图片检测
```bash
python pose_estimate.py -i test.jpg -c camera_calibration.yaml -s
```

## 核心算法管线解析
靶标检测：使用 cv2.findChessboardCorners 提取 9x6 棋盘格角点，并利用 cv2.cornerSubPix 进行亚像素级迭代优化。

位姿解算：采用 cv2.SOLVEPNP_IPPE 算法。IPPE 专为平面靶标设计，速度极快。由于平面 PnP 存在镜像歧义（会输出两个解），代码内部自动对比两个解的重投影误差，保留误差最小的真实位姿。

坐标转换：利用 cv2.Rodrigues 将旋转向量转化为旋转矩阵，随后基于 XYZ 内旋顺序转化为欧拉角（Roll/Pitch/Yaw）。

可视化：通过 cv2.drawFrameAxes 绘制彩色坐标轴（X红、Y绿、Z蓝），并实时在画面上叠加显示当前距离与偏航/俯仰角。

## 目录结构说明

M2-2/
├── pose_estimate.py         # 位姿估计主程序（支持图/视频/摄像头）
├── camera_calibration.yaml  # 复用自 M2-1 的相机内参文件（必须读取）
├── report.md                # 核心原理、物体系定义与答辩分析
├── accuracy.md              # 距离/姿态/畸变三组精度实测数据
├── marker/                  # 靶标原图与实测物理尺寸说明
└── results/                 # 坐标轴可视化截图（≥3个不同姿态）

