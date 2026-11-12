import cv2
import numpy as np
import argparse
import yaml
import sys

def load_calibration(yaml_path):
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            calib_data = yaml.safe_load(f)
        return calib_data['camera']
    except Exception as e:
        print(f"Error: Cannot load calibration file {e}", file=sys.stderr)
        sys.exit(1)

def process_frame(frame):
    # 1. 去噪
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    
    # 2. 转 HSV
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    
    # 3. 设定阈值（恢复最灵敏的初始参数）
    # 红色
    lower_red1 = np.array([0, 120, 70])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 70])
    upper_red2 = np.array([180, 255, 255])
    # 黄色
    lower_yellow = np.array([20, 100, 100])
    upper_yellow = np.array([35, 255, 255])
    # 绿色
    lower_green = np.array([40, 70, 70])
    upper_green = np.array([90, 255, 255])

    # 4. 生成掩码
    mask_red = cv2.inRange(hsv, lower_red1, upper_red1) + cv2.inRange(hsv, lower_red2, upper_red2)
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    mask_green = cv2.inRange(hsv, lower_green, upper_green)

    # 5. 形态学清理
    kernel = np.ones((5, 5), np.uint8)
    def clean_mask(mask):
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    mask_red = clean_mask(mask_red)
    mask_yellow = clean_mask(mask_yellow)
    mask_green = clean_mask(mask_green)

    # 6. 画图与判定
    result_frame = frame.copy()
    detected_status = "Unrecognized"
    
    def find_and_draw(mask, color_name, bgr_color):
        nonlocal detected_status
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        max_area = 0
        best_cnt = None
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > max_area:
                max_area = area
                best_cnt = cnt
                
        # 【核心修改点】：面积下限降到了 100，防止手机屏幕上的小圆点被过滤
        if best_cnt is not None and 100 < max_area < 50000:
            (x, y), radius = cv2.minEnclosingCircle(best_cnt)
            center = (int(x), int(y))
            radius = int(radius)
            
            # 画圆
            cv2.circle(result_frame, center, radius, bgr_color, 2)
            # 写文字（英文防乱码）
            cv2.putText(result_frame, color_name, (center[0]-30, center[1]-radius-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, bgr_color, 2)
            
            if detected_status == "Unrecognized":
                detected_status = color_name
            return True
        return False

    # 按优先级检测
    find_and_draw(mask_red, "Red", (0, 0, 255))       # 红色
    find_and_draw(mask_yellow, "Yellow", (0, 255, 255)) # 黄色
    find_and_draw(mask_green, "Green", (0, 255, 0))     # 绿色

    # 如果全没找到
    if detected_status == "Unrecognized":
        cv2.putText(result_frame, "Status: Unrecognized", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    else:
        cv2.putText(result_frame, f"Status: {detected_status}", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    return result_frame

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--image", help="Input image path")
    parser.add_argument("-v", "--video", help="Input video path")
    parser.add_argument("-c", "--calib", required=True, help="Calibration yaml path")
    parser.add_argument("-s", "--show", action="store_true", help="Show window")
    args = parser.parse_args()

    load_calibration(args.calib)
    print(f"Calibration loaded: {args.calib}")

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            print("Error: Cannot read image")
            return
        result = process_frame(frame)
        if args.show:
            cv2.imshow("Result", result)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        cv2.imwrite("output_result.jpg", result)
        print("Saved to output_result.jpg")

    elif args.video:
        cap = cv2.VideoCapture(args.video)
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            result = process_frame(frame)
            if args.show:
                cv2.imshow("Result", result)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
        cap.release()
        cv2.destroyAllWindows()
        
    else:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        print("Camera started. Press 'q' to quit.")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            result = process_frame(frame)
            cv2.imshow("Traffic Light Detector", result)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

    
    #cmd  python detect.py -c camera_calibration.yaml -s