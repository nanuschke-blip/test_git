import cv2

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('videos/my_scene.mp4', fourcc, 30.0, (1280, 720))

print("开始录制，按 'q' 键停止录制...")
while True:
    ret, frame = cap.read()
    if not ret: break
    out.write(frame)
    cv2.imshow("Recording...", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
out.release()
cv2.destroyAllWindows()
print("录制完成，已保存至 videos/my_scene.mp4")