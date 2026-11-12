import cv2
import numpy as np

# 打开摄像头
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

def pick_color(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        pixel = hsv[y, x]
        print(f"👉 你点击的位置 HSV 值为: H={pixel[0]}, S={pixel[1]}, V={pixel[2]}")

cv2.namedWindow("Color Picker")
cv2.setMouseCallback("Color Picker", pick_color)

while True:
    ret, frame = cap.read()
    if not ret: break
    cv2.imshow("Color Picker", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()