import cv2
import numpy as np
import argparse
import yaml
import sys
import math

def load_calibration(yaml_path):
    """读取 M2-1 的标定文件"""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 提取内参矩阵和畸变系数
        mtx = np.array([
            [data['camera']['intrinsics']['fx'], 0, data['camera']['intrinsics']['cx']],
            [0, data['camera']['intrinsics']['fy'], data['camera']['intrinsics']['cy']],
            [0, 0, 1]
        ], dtype=np.float64)
        
        dist = np.array([
            data['camera']['distortion']['k1'], data['camera']['distortion']['k2'],
            data['camera']['distortion']['p1'], data['camera']['distortion']['p2'],
            data['camera']['distortion']['k3']
        ], dtype=np.float64)
        
        return mtx, dist
    except Exception as e:
        print(f"Error: Cannot load calibration file {e}", file=sys.stderr)
        sys.exit(1)

def is_rotation_matrix(R):
    """判断是否是合法的旋转矩阵"""
    Rt = np.transpose(R)
    should_be_identity = np.dot(Rt, R)
    I = np.identity(3, dtype=R.dtype)
    n = np.linalg.norm(I - should_be_identity)
    return n < 1e-6

def rotation_matrix_to_euler_angles(R):
    """旋转矩阵转欧拉角 (XYZ内旋)"""
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6
    if not singular:
        x = math.atan2(R[2, 1], R[2, 2])
        y = math.atan2(-R[2, 0], sy)
        z = math.atan2(R[1, 0], R[0, 0])
    else:
        x = math.atan2(-R[1, 2], R[1, 1])
        y = math.atan2(-R[2, 0], sy)
        z = 0
    return np.array([math.degrees(x), math.degrees(y), math.degrees(z)])

def process_frame(frame, mtx, dist, board_size, square_size, use_distortion=True):
    """核心位姿估计逻辑"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # 1. 找角点
    ret, corners = cv2.findChessboardCorners(gray, board_size, None)
    
    if ret:
        # 亚像素优化
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        
        # 2. 定义 3D 物理坐标 (原点在左上角，Z=0)
        objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2)
        objp = objp * square_size
        
        # 3. 解算 PnP (使用 IPPE 算法)
        # IPPE 专为平面靶标设计，速度快，但会输出两个解 (R1, t1) 和 (R2, t2)
        dist_coeffs = dist if use_distortion else np.zeros(5)
        
        retval, rvecs, tvecs, reprojErrs = cv2.solvePnPGeneric(
            objp, corners2, mtx, dist_coeffs, flags=cv2.SOLVEPNP_IPPE
        )
        
        if retval >= 1:
            # 如果返回两个解，选重投影误差小的那个
            best_idx = 0
            if retval == 2 and reprojErrs is not None:
                if reprojErrs[1] < reprojErrs[0]:
                    best_idx = 1
            
            rvec = rvecs[best_idx]
            tvec = tvecs[best_idx]
            
            # 4. 姿态转换
            R, _ = cv2.Rodrigues(rvec)
            euler_angles = rotation_matrix_to_euler_angles(R)
            
            # 5. 画坐标轴 (X红, Y绿, Z蓝)，长度为边长的 0.5 倍
            axis_len = square_size * 0.5
            cv2.drawFrameAxes(frame, mtx, dist_coeffs, rvec, tvec, axis_len)
            
            # 6. 叠显信息
            distance = tvec[2][0] # Z轴距离，单位米
            text = f"[Dist: {distance:.2f}m, Yaw: {euler_angles[1]:+.1f}, Pitch: {euler_angles[0]:+.1f}]"
            cv2.putText(frame, text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            # 画角点连接线
            cv2.drawChessboardCorners(frame, board_size, corners2, ret)

    return frame

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--image", help="输入图片路径")
    parser.add_argument("-v", "--video", help="输入视频路径")
    parser.add_argument("-c", "--calib", required=True, help="M2-1 标定 yaml 路径")
    parser.add_argument("-s", "--show", action="store_true", help="显示画面")
    # 用于测试不带畸变系数的情况
    parser.add_argument("--no-dist", action="store_true", help="不使用畸变系数测试")
    args = parser.parse_args()

    mtx, dist = load_calibration(args.calib)
    print(f"Loaded calibration from {args.calib}")
    
    # 靶标参数 (9x6 内角点，24.0mm 边长)
    board_size = (9, 6)
    square_size = 24.0 / 1000.0 # 转换为米
    
    use_dist = not args.no_dist

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None: return
        result = process_frame(frame, mtx, dist, board_size, square_size, use_dist)
        if args.show:
            cv2.imshow("Pose Estimation", result)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        cv2.imwrite("output_pose.jpg", result)

    else:
        # 默认摄像头
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            result = process_frame(frame, mtx, dist, board_size, square_size, use_dist)
            cv2.imshow("Pose Estimation", result)
            
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()