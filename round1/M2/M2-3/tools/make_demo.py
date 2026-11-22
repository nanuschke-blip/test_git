"""M2-3 演示视频生成（headless 版，和 deploy_cpu.py 用同一套预处理/推理/NMS/画框）

区别只有一个：不调用 cv2.imshow，所以可以在没有图形界面的终端里批量生成 demo 视频。
画面内容与 deploy_cpu.py 完全一致：检测框 + 类别 + 置信度 + 单帧耗时 + FPS + 平均耗时。

用法：
    python tools/make_demo.py --video ../M2-4/videos/my_scene.mp4 --save demo/demo.mp4
"""
import argparse
import collections
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from yolo_onnx import YoloOnnx          # noqa: E402

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/best.onnx")
    ap.add_argument("--video", required=True)
    ap.add_argument("--save", default="demo/demo.mp4")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--max-frames", type=int, default=0, help="0=整段")
    args = ap.parse_args()

    model = YoloOnnx(args.model, 640, conf=args.conf)
    print(f"[demo] model={args.model} providers={model.providers}")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频: {args.video}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
    writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    n, t_sum = 0, 0.0
    hist = collections.Counter()
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        boxes, scores, ids = model.predict(frame)
        t1 = time.perf_counter()
        t_sum += t1 - t0
        n += 1
        for cid in ids:
            hist[CLASSES[int(cid)]] += 1

        model.draw(frame, boxes, scores, ids, CLASSES)
        cv2.putText(frame,
                    f"{1000.0 * (t1 - t0):.1f} ms  {1.0 / (t1 - t0 + 1e-9):.1f} FPS  "
                    f"avg {1000.0 * t_sum / n:.1f} ms",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        writer.write(frame)

        if n % 100 == 0:
            print(f"[demo] {n} frames, avg {1000.0 * t_sum / n:.1f} ms/frame", flush=True)
        if args.max_frames and n >= args.max_frames:
            break

    cap.release()
    writer.release()
    print(f"[demo] saved -> {args.save}  ({n} frames, {n / max(t_sum, 1e-6):.1f} FPS avg)")
    print(f"[demo] 类别统计: {dict(hist)}")


if __name__ == "__main__":
    main()
