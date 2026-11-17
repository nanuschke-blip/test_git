"""纯 ONNX Runtime 的 CPU 部署演示：完整预处理 + 推理 + NMS 后处理 + 画框 + FPS

用法:
    python deploy_cpu.py                    # 摄像头实时
    python deploy_cpu.py --video xxx.mp4    # 对视频文件跑（按 q 退出）
    python deploy_cpu.py --save out.mp4     # 顺便把结果存成视频
"""
import os
import time
import argparse

import cv2

from yolo_onnx import YoloOnnx

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/best.onnx")
    ap.add_argument("--video", default=None, help="不填则打开摄像头 0")
    ap.add_argument("--save", default=None)
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    model = YoloOnnx(args.model, 640, conf=args.conf)
    print(f"[deploy] {args.model} on {model.providers}")

    cap = cv2.VideoCapture(args.video if args.video else 0)
    if not cap.isOpened():
        raise RuntimeError("打不开视频源")

    writer = None
    if args.save:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    n, t_sum = 0, 0.0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        t0 = time.perf_counter()
        boxes, scores, ids = model.predict(frame)
        t1 = time.perf_counter()
        t_sum += t1 - t0
        n += 1

        model.draw(frame, boxes, scores, ids, CLASSES)
        cv2.putText(frame, f"{1000.0 * (t1 - t0):.1f} ms  {1.0 / (t1 - t0 + 1e-9):.1f} FPS  "
                           f"avg {1000.0 * t_sum / n:.1f} ms",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        if writer is not None:
            writer.write(frame)
        cv2.imshow("YOLOv8n ONNX Runtime (CPU) - press q to quit", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    if writer is not None:
        writer.release()
        print(f"[deploy] saved -> {args.save}")
    cv2.destroyAllWindows()
    if n:
        print(f"[deploy] {n} frames, avg {1000.0 * t_sum / n:.2f} ms/frame, "
              f"{n / t_sum:.2f} FPS")


if __name__ == "__main__":
    main()
