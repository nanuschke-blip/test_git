import cv2
import numpy as np
import glob
import yaml
import argparse
import os

def calibrate(images_path, output_file, square_size):
    # 9x6 内角点 (宽9, 高6)
    pattern_size = (9, 6)
    
    # 准备世界坐标系中的点 (0,0,0), (1,0,0), (2,0,0) ...
    objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern_size[0], 0:pattern_size[1]].T.reshape(-1, 2)
    objp = objp * square_size # 乘以实际物理尺寸(mm)

    objpoints = [] # 真实世界中的 3D 点
    imgpoints = [] # 图像平面上的 2D 点

    # 读取所有 jpg 和 png 图片
    images = glob.glob(os.path.join(images_path, "*.jpg")) + glob.glob(os.path.join(images_path, "*.png"))
    if not images:
        print("[FAIL] 错误：文件夹中没有找到图片，请检查路径！")
        return

    print(f"找到 {len(images)} 张图片，开始处理...")
    img_shape = None
    success_count = 0

    for fname in images:
        img = cv2.imread(fname)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        if img_shape is None:
            img_shape = gray.shape[::-1] # (width, height)

        # 寻找棋盘格角点
        ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)
        
        if ret:
            objpoints.append(objp)
            # 亚像素级精细化，提高精度
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)
            
            # 画出角点供肉眼检查
            cv2.drawChessboardCorners(img, pattern_size, corners2, ret)
            cv2.imshow('Find Corners (Press any key)', cv2.resize(img, (800, 600)))
            cv2.waitKey(300) # 显示 300ms
            success_count += 1
        else:
            print(f"[WARN] 未能在 {os.path.basename(fname)} 中找到角点，已跳过。")

    cv2.destroyAllWindows()

    if success_count == 0:
        print("[FAIL] 错误：所有图片都未能识别出角点，请重新拍摄！")
        return

    # 开始标定计算
    print(f"成功识别 {success_count} 张图，开始计算内参...")
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_shape, None, None)

    # 提取参数
    fx = mtx[0, 0]
    fy = mtx[1, 1]
    cx = mtx[0, 2]
    cy = mtx[1, 2]
    k1, k2, p1, p2, k3 = dist[0]

    # 计算重投影误差 (RMSE)
    total_error = 0
    for i in range(len(objpoints)):
        imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
        total_error += error
    mean_error = total_error / len(objpoints)

    print(f"\n[OK] 标定完成！")
    print(f" 重投影误差 (RMSE): {mean_error:.4f} px")

    # 严格按照任务书 §4.2 格式保存 YAML
    calib_data = {
        "camera": {
            "model": "pinhole",
            "resolution": [int(img_shape[0]), int(img_shape[1])],
            "intrinsics": {
                "fx": float(fx), "fy": float(fy),
                "cx": float(cx), "cy": float(cy)
            },
            "distortion": {
                "k1": float(k1), "k2": float(k2),
                "p1": float(p1), "p2": float(p2),
                "k3": float(k3)
            },
            "reprojection_error": float(mean_error),
            "calib_board": {
                "type": "chessboard",
                "inner_corners": [9, 6],
                "square_size_mm": float(square_size),
                "images_used": success_count
            }
        }
    }

    # 保存文件
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(calib_data, f, sort_keys=False, default_flow_style=False)
    print(f" 内参已成功保存至: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenCV 相机标定脚本")
    parser.add_argument("-i", "--images", required=True, help="图片文件夹路径")
    parser.add_argument("-o", "--out", default="camera_calibration.yaml", help="输出yaml文件路径")
    parser.add_argument("-s", "--square_size", type=float, default=25.0, help="棋盘格单个方格的实际边长(mm)")
    args = parser.parse_args()

    calibrate(args.images, args.out, args.square_size)