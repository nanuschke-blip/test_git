"""M2-1 标注小工具：点一下灯的中心，按 1/2/3 选颜色，自动跳到下一帧。

用法：
    python3 label_tool.py --source videos/test.mp4 --stride 20 --ann labels.csv
    python3 label_tool.py --source results/ --ann labels.csv          # 图片目录模式

操作：
    鼠标左键   在该帧上点灯的中心（会画十字）
    1/2/3     保存为 Red / Yellow / Green（用最近一次点击的位置），并进入下一帧
    0         保存为 none（这一帧没有灯/全黑），进入下一帧
    n         跳过这一帧（不写标注）
    b         回到上一帧
    q         保存并退出

标注文件格式（eval.py 直接读）：
    key,state,cx,cy
    0,Red,1389,816
    20,none,,
"""
import argparse
import csv
import os

import cv2

WIN = "label_tool  (click center | 1=Red 2=Yellow 3=Green | 0=none | n=skip  b=back  q=quit)"
MAX_W = 1280


def load_frames(source, stride):
    if os.path.isdir(source):
        out = []
        for name in sorted(os.listdir(source)):
            if name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                img = cv2.imread(os.path.join(source, name))
                if img is not None:
                    out.append((name, img))
        return out

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频: {source}")
    out, idx = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            out.append((str(idx), frame))
        idx += 1
    cap.release()
    return out


def load_ann(path):
    d = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d[r["key"].strip()] = r
    return d


def save_ann(path, d, order):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["key", "state", "cx", "cy"])
        w.writeheader()
        for k in order:
            if k in d:
                w.writerow({"key": k, "state": d[k]["state"],
                            "cx": d[k].get("cx", ""), "cy": d[k].get("cy", "")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--ann", default="labels.csv")
    ap.add_argument("--stride", type=int, default=20)
    ap.add_argument("--redo", action="store_true", help="重新标已存在的帧")
    args = ap.parse_args()

    frames = load_frames(args.source, args.stride)
    if not frames:
        raise SystemExit("没有可用的帧")
    order = [k for k, _ in frames]
    ann = load_ann(args.ann)
    print(f"[label] 共 {len(frames)} 帧采样，已有 {len(ann)} 条标注 -> {args.ann}")

    state = {"pt": None, "scale": 1.0}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["pt"] = (x / state["scale"], y / state["scale"])

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WIN, on_mouse)

    i = 0
    while 0 <= i < len(frames):
        key, frame = frames[i]
        if key in ann and not args.redo:
            i += 1
            continue

        state["pt"] = None
        h, w = frame.shape[:2]
        scale = min(1.0, MAX_W / w)
        state["scale"] = scale
        disp = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame.copy()
        cv2.putText(disp, f"{i + 1}/{len(frames)}  key={key}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(disp, "click center | 1=Red 2=Yellow 3=Green | 0=none | n=skip  b=back  q=quit",
                    (10, disp.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        k = -1
        while True:
            show = disp.copy()
            if state["pt"] is not None:
                px, py = int(state["pt"][0] * scale), int(state["pt"][1] * scale)
                cv2.drawMarker(show, (px, py), (0, 255, 255), cv2.MARKER_CROSS, 24, 2)
            if key in ann:
                cv2.putText(show, f"cur: {ann[key]['state']}", (10, 58),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow(WIN, show)
            k = cv2.waitKey(30) & 0xFF
            if k in (ord("1"), ord("2"), ord("3"), ord("0"), ord("n"), ord("b"), ord("q")):
                break

        if k == ord("q"):
            break
        if k == ord("b"):
            i = max(0, i - 1)
            continue
        if k == ord("n"):
            i += 1
            continue

        if k == ord("0"):
            ann[key] = {"key": key, "state": "none", "cx": "", "cy": ""}
        else:
            name = {ord("1"): "Red", ord("2"): "Yellow", ord("3"): "Green"}[k]
            if state["pt"] is None:
                print(f"[label] 第 {key} 帧没有点击位置，先点灯中心再按颜色键")
                continue
            ann[key] = {"key": key, "state": name,
                        "cx": f"{state['pt'][0]:.0f}", "cy": f"{state['pt'][1]:.0f}"}
        save_ann(args.ann, ann, order)
        print(f"[label] {key} -> {ann[key]['state']} ({ann[key]['cx']},{ann[key]['cy']})  "
              f"已存 {len(ann)} 条")
        i += 1

    save_ann(args.ann, ann, order)
    cv2.destroyAllWindows()
    print(f"[label] 完成，共 {len(ann)} 条 -> {args.ann}")


if __name__ == "__main__":
    main()
