"""M2-3 CPU 推理性能测试（预处理 / 推理 / 后处理 分别计时）

之前这里是一个写死的假数据（随机噪声图 + 手填的 5/23.3/0.5 ms 饼图），
现在改成：用测试集真实图片，分别计时三个阶段，重复 N 次取统计量，
结果写 docs/benchmark_result.json，plot_time.py 从这份 JSON 画图。

用法:
    python benchmark.py
"""
import os
import json
import time
import glob
import csv

import cv2
import numpy as np

from yolo_onnx import YoloOnnx, letterbox, to_tensor, postprocess

MODEL = "models/best.onnx"
IMGSZ = 640
WARMUP = 10
ITERS = 200
OUT_JSON = "docs/benchmark_result.json"


def load_frames(n=4):
    imgs = sorted(glob.glob("data/images/*.jpg"))
    if not imgs:
        raise FileNotFoundError("data/images 里没有图片")
    # 用测试集优先，退化到全部
    test_list = "data/splits/test.txt"
    if os.path.exists(test_list):
        names = [os.path.basename(x.strip()) for x in open(test_list) if x.strip()]
        cand = [p for p in imgs if os.path.basename(p) in names]
        if cand:
            imgs = cand
    step = max(1, len(imgs) // n)
    return [cv2.imread(p) for p in imgs[::step][:n]]


def main():
    model = YoloOnnx(MODEL, IMGSZ)
    frames = load_frames()
    print(f"[bench] model={MODEL} imgsz={IMGSZ} providers={model.providers}")
    print(f"[bench] {len(frames)} frames, {frames[0].shape[1]}x{frames[0].shape[0]}, "
          f"warmup={WARMUP}, iters={ITERS}")

    t_pre, t_inf, t_post = [], [], []
    for i in range(WARMUP + ITERS):
        img = frames[i % len(frames)]

        t0 = time.perf_counter()
        lb, r, pad = letterbox(img, IMGSZ)
        x = to_tensor(lb)
        t1 = time.perf_counter()

        out = model.sess.run(None, {model.input_name: x})
        t2 = time.perf_counter()

        postprocess(out, r, pad, img.shape, model.conf, model.iou)
        t3 = time.perf_counter()

        if i >= WARMUP:
            t_pre.append((t1 - t0) * 1000)
            t_inf.append((t2 - t1) * 1000)
            t_post.append((t3 - t2) * 1000)

    pre, inf, post = (np.array(t_pre), np.array(t_inf), np.array(t_post))
    total = pre + inf + post
    res = {
        "model": MODEL,
        "imgsz": IMGSZ,
        "input_size": [int(frames[0].shape[1]), int(frames[0].shape[0])],
        "providers": model.providers,
        "iters": ITERS,
        "preprocess_ms": round(float(pre.mean()), 3),
        "inference_ms": round(float(inf.mean()), 3),
        "postprocess_ms": round(float(post.mean()), 3),
        "total_ms": round(float(total.mean()), 3),
        "total_std_ms": round(float(total.std()), 3),
        "total_min_ms": round(float(total.min()), 3),
        "total_max_ms": round(float(total.max()), 3),
        "fps": round(float(1000.0 / total.mean()), 2),
        "pct": {
            "preprocess": round(float(pre.mean() / total.mean() * 100), 1),
            "inference": round(float(inf.mean() / total.mean() * 100), 1),
            "postprocess": round(float(post.mean() / total.mean() * 100), 1),
        },
    }
    os.makedirs("docs", exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(res, f, indent=1)

    # 题面要求"输出 CSV + 分布图"
    with open("docs/benchmark_result.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "ms_per_frame", "percent"])
        for k, pct in (("preprocess", "preprocess"), ("inference", "inference"),
                       ("postprocess", "postprocess")):
            w.writerow([k, res[f"{k}_ms"], res["pct"][pct]])
        w.writerow(["total", res["total_ms"], 100.0])
        w.writerow(["fps", res["fps"], ""])
        w.writerow(["iters", res["iters"], ""])
        w.writerow(["input_size", f"{res['input_size'][0]}x{res['input_size'][1]}", ""])

    print(f"[bench] preprocess  {res['preprocess_ms']:7.3f} ms  ({res['pct']['preprocess']}%)")
    print(f"[bench] inference   {res['inference_ms']:7.3f} ms  ({res['pct']['inference']}%)")
    print(f"[bench] postprocess {res['postprocess_ms']:7.3f} ms  ({res['pct']['postprocess']}%)")
    print(f"[bench] total       {res['total_ms']:7.3f} ms  -> {res['fps']} FPS "
          f"(min {res['total_min_ms']} / max {res['total_max_ms']} ms)")
    print(f"[ok] {OUT_JSON}")


if __name__ == "__main__":
    main()
