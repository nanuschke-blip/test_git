"""M2-4 检测序列生成：把 M2-3 训好的检测器跑一遍视频，逐帧存成 JSON

为什么单独存 JSON：
    追踪/对比/评测要反复跑很多遍（不同 max_age、不同噪声参数），
    每跑一遍都重新做一次推理太慢（CPU 上 40ms/帧，51s 视频要 40 分钟）。
    先把检测结果落盘，后面所有实验都复用同一份检测，结果也可复现。

用法:
    python detector_adapter.py                       # 只用 JSON，不弹窗
    python detector_adapter.py --preview             # 边跑边显示检测框（按 q 退出预览）
    python detector_adapter.py --conf 0.3 --stride 1 # 调置信度阈值
"""
import os
import json
import argparse

import cv2


def generate_detections(video_path, model_path, output_json,
                        conf=0.25, iou=0.45, preview=False, stride=1, indent=1):
    """逐帧推理，写出 {video, fps, classes, frames:[{frame, dets:[{cls,conf,bbox}]}]}"""
    from ultralytics import YOLO          # 延迟导入，只读 JSON 的脚本不必装 ultralytics

    print(f"[det] video={video_path}  model={model_path}  conf={conf}  "
          f"nms_iou={iou}  stride={stride}")

    model = YOLO(model_path)
    names = model.names
    if isinstance(names, dict):
        classes = [names[i] for i in sorted(names)]
    else:
        classes = list(names)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    data = {
        "video": os.path.basename(video_path),
        "fps": int(round(fps)),
        "classes": classes,
        "conf_thres": conf,
        "frames": [],
    }

    fi = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if stride > 1 and fi % stride != 0:
            fi += 1
            continue

        r = model(frame, verbose=False, conf=conf, iou=iou)[0]
        dets = []
        for b in r.boxes:
            dets.append({
                "cls": int(b.cls[0]),
                "conf": round(float(b.conf[0]), 4),
                "bbox": [round(float(v), 2) for v in b.xyxy[0].tolist()],
            })
        data["frames"].append({"frame": fi, "dets": dets})

        if preview:
            for d in dets:
                x1, y1, x2, y2 = [int(v) for v in d["bbox"]]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{classes[d['cls']]} {d['conf']:.2f}",
                            (x1, max(y1 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, f"frame {fi}/{total}  dets={len(dets)}",
                        (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.imshow("detections (press q to stop preview)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                preview = False
                cv2.destroyAllWindows()

        fi += 1
        if fi % 100 == 0:
            print(f"  {fi}/{total} frames, {len(data['frames'])} kept")

    cap.release()
    if preview:
        cv2.destroyAllWindows()

    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
    with open(output_json, "w") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

    n = sum(len(fr["dets"]) for fr in data["frames"])
    per = {}
    for fr in data["frames"]:
        for d in fr["dets"]:
            per[classes[d["cls"]]] = per.get(classes[d["cls"]], 0) + 1
    print(f"[det] {len(data['frames'])} frames, {n} detections -> {output_json}")
    print("[det] per class: " + ", ".join(f"{k}={v}" for k, v in sorted(per.items())))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="videos/my_scene.mp4")
    ap.add_argument("--model", default="models/best.onnx")
    ap.add_argument("--out", default="detections/my_scene.json")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.45, help="NMS IoU 阈值")

    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    generate_detections(args.video, args.model, args.out, conf=args.conf,
                        iou=args.iou, preview=args.preview, stride=args.stride)



if __name__ == "__main__":
    main()
