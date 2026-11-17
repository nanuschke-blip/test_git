"""M2-3 手工标注工具（半自动：先用 COCO 预训练模型给建议框，再手动拖框修正）

用法:
    cd C:\\Users\\AMDI2025\\Desktop\\M2-3
    python label_tool.py

操作:
    Enter 或 空格  = 采用当前框（没有框时直接用蓝色建议框）并进入下一张
    鼠标左键拖拽  = 画/改框
    u             = 采用蓝色建议框
    r             = 清空当前框
    s             = 跳过这一张（不写标签）
    Esc           = 退出（已保存的不会丢，下次接着标）

标签写在 data/labels_raw/<同名>.txt，格式为 YOLO 的 "cls cx cy w h"（归一化）。
类别由文件名前缀自动决定，不需要手选。

注意：建议框只提供“大概位置”，类别名不重要（COCO 常把瓶子认成 cup/vase），
      位置不对就拖鼠标重画，别直接回车把错框存进去。
"""
import os
import glob
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, "data", "images")
RAW_DIR = os.path.join(ROOT, "data", "labels_raw")
os.makedirs(RAW_DIR, exist_ok=True)

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
CMAP = {n: i for i, n in enumerate(CLASSES)}

# 这些是背景/人/家具，不当成目标物体的建议框
BACKGROUND = {
    "person", "dining table", "chair", "couch", "bed", "refrigerator", "laptop",
    "tv", "suitcase", "car", "bicycle", "motorcycle", "bench", "sink", "toilet",
    "door", "window", "clock", "vase", "book",
}
# 类别名能对上时给个加分，优先采用
CLASS_HINT = {
    "bottle": "bottle", "cup": "cup", "wine glass": "cup", "cell phone": "phone",
    "mouse": "mouse", "remote": "mouse", "book": "tissue",
}

WIN = "label_tool"
VIEW_W, VIEW_H = 960, 540

S = {
    "img": None,
    "scale": 1.0,
    "box": None,       # 原图坐标系 (x1,y1,x2,y2)
    "drag": None,      # (x0,y0)
    "prop": None,      # 建议框
    "name": "",
    "cls": 0,
    "idx": 0,
    "total": 0,
    "msg": "",
}
MODEL = None


def load_model():
    global MODEL
    try:
        from ultralytics import YOLO
        p = os.path.join(ROOT, "yolov8n.pt")
        MODEL = YOLO(p if os.path.exists(p) else "yolov8n.pt")
        print("[info] suggestion model loaded")
    except Exception as e:  # 没装 ultralytics 也能纯手工标
        print(f"[warn] cannot load proposal model, draw all boxes by hand: {e}")
        MODEL = None


def propose(img, target_cls):
    """返回一个“大概位置”的建议框（原图坐标）。不挑类别，只排除背景类。"""
    if MODEL is None:
        return None
    try:
        r = MODEL(img, verbose=False, imgsz=960, conf=0.08)[0]
    except Exception:
        return None
    h, w = img.shape[:2]
    area = float(w * h)
    best, best_score = None, 0.0
    for b in r.boxes:
        nm = r.names[int(b.cls[0])]
        if nm in BACKGROUND:
            continue
        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
        a = (x2 - x1) * (y2 - y1)
        if a < 0.02 * area or a > 0.85 * area:   # 太小/太大都不像目标
            continue
        score = float(b.conf[0])
        if CLASS_HINT.get(nm) == CLASSES[target_cls]:
            score += 0.5
        if score > best_score:
            best_score, best = score, [x1, y1, x2, y2]
    return best


def draw(img, box, prop, cls, name, idx, total, msg):
    h, w = img.shape[:2]
    scale = min(VIEW_W / w, VIEW_H / h)
    disp = cv2.resize(img, (int(w * scale), int(h * scale)))

    def sc(b):
        return (int(b[0] * scale), int(b[1] * scale), int(b[2] * scale), int(b[3] * scale))

    if prop is not None:
        x1, y1, x2, y2 = sc(prop)
        cv2.rectangle(disp, (x1, y1), (x2, y2), (255, 160, 0), 2)
        cv2.putText(disp, "suggestion", (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 160, 0), 1, cv2.LINE_AA)
    if box is not None:
        x1, y1, x2, y2 = sc(box)
        cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 255, 0), 2)
        bw, bh = box[2] - box[0], box[3] - box[1]
        cv2.putText(disp, f"{CLASSES[cls]}  {int(bw)}x{int(bh)}", (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA)

    bar = f"[{idx+1}/{total}] {name}   class={CLASSES[cls]}"
    cv2.putText(disp, bar, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
    if box is None and prop is not None:
        tip = "Enter = use suggestion & save    drag = redraw    r = clear    s = skip    Esc = quit"
    else:
        tip = "drag = box    Enter = save    u = suggestion    r = clear    s = skip    Esc = quit"
    cv2.putText(disp, tip, (8, disp.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    if msg:
        cv2.putText(disp, msg, (8, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
    return disp, scale


def refresh():
    disp, scale = draw(S["img"], S["box"], S["prop"], S["cls"], S["name"],
                       S["idx"], S["total"], S["msg"])
    S["scale"] = scale
    cv2.imshow(WIN, disp)


def on_mouse(event, x, y, flags, param):
    if S["img"] is None:
        return
    s = S["scale"]
    ox, oy = x / s, y / s
    h, w = S["img"].shape[:2]
    ox = min(max(ox, 0), w - 1)
    oy = min(max(oy, 0), h - 1)
    if event == cv2.EVENT_LBUTTONDOWN:
        S["drag"] = (ox, oy)
        S["box"] = (ox, oy, ox, oy)
        refresh()
    elif event == cv2.EVENT_MOUSEMOVE and S["drag"] is not None:
        x0, y0 = S["drag"]
        S["box"] = (min(x0, ox), min(y0, oy), max(x0, ox), max(y0, oy))
        refresh()
    elif event == cv2.EVENT_LBUTTONUP and S["drag"] is not None:
        x0, y0 = S["drag"]
        b = (min(x0, ox), min(y0, oy), max(x0, ox), max(y0, oy))
        S["drag"] = None
        S["box"] = b if (b[2] - b[0] > 8 and b[3] - b[1] > 8) else None
        refresh()


def save_box():
    x1, y1, x2, y2 = S["box"]
    h, w = S["img"].shape[:2]
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    bw, bh = (x2 - x1) / w, (y2 - y1) / h
    out = os.path.join(RAW_DIR, S["name"].rsplit(".", 1)[0] + ".txt")
    with open(out, "w") as f:
        f.write(f"{S['cls']} {min(max(cx, 0), 1):.6f} {min(max(cy, 0), 1):.6f} "
                f"{min(bw, 1):.6f} {min(bh, 1):.6f}\n")
    return out


def main():
    load_model()

    files = [f for f in sorted(os.listdir(IMG_DIR))
             if f.lower().endswith((".jpg", ".png", ".jpeg")) and "_aug" not in f]
    todo = []
    for f in files:
        if f.split("_")[0] not in CMAP:
            continue
        if os.path.exists(os.path.join(RAW_DIR, f.rsplit(".", 1)[0] + ".txt")):
            continue
        todo.append(f)

    done = len(files) - len(todo)
    S["total"] = len(todo)
    if not todo:
        print(f"all {len(files)} originals already labeled (data/labels_raw)")
        return
    print(f"labeled {done}, remaining {len(todo)}. Enter = use suggestion & save, drag = redraw.")

    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WIN, on_mouse)

    for i, name in enumerate(todo):
        img = cv2.imread(os.path.join(IMG_DIR, name))
        if img is None:
            continue
        S.update(img=img, name=name, cls=CMAP[name.split("_")[0]], idx=done + i,
                 box=None, prop=None, drag=None, msg="")
        S["prop"] = propose(img, S["cls"])
        if S["prop"] is None:
            S["msg"] = "no suggestion - please drag a box"
        refresh()

        while True:
            k = cv2.waitKey(0) & 0xFF
            if k in (13, 10, 32):  # Enter / Space
                if S["box"] is None and S["prop"] is not None:
                    S["box"] = tuple(S["prop"])
                if S["box"] is None:
                    S["msg"] = "no box - drag first"
                    refresh()
                    continue
                save_box()
                print(f"[{done+i+1}/{done+len(todo)}] {name} saved")
                break
            elif k == 0:  # 方向键等特殊键，忽略
                continue
            elif k == ord("u"):
                if S["prop"] is not None:
                    S["box"] = tuple(S["prop"])
                    S["msg"] = ""
                refresh()
            elif k == ord("r"):
                S["box"] = None
                S["msg"] = ""
                refresh()
            elif k == ord("s"):
                print(f"[{done+i+1}/{done+len(todo)}] {name} skipped")
                break
            elif k == 27:  # Esc
                cv2.destroyAllWindows()
                print("quit - saved labels are kept, rerun to continue")
                return
    cv2.destroyAllWindows()

    got = len(glob.glob(os.path.join(RAW_DIR, "*.txt")))
    print(f"done, {got} label files in data/labels_raw")


if __name__ == "__main__":
    main()
