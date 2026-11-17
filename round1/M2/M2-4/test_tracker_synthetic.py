"""合成序列自检：在没有真实检测器的情况下验证追踪器的三条硬性行为

场景（180 帧，两个不同类别目标，避免同类交叉的固有歧义）：
    目标 A（cup）：x 每帧 +4px，从左往右
        - 第 40~47 帧检测缺失（8 帧遮挡）→ 必须保持同一个 ID
        - 第 100~114 帧检测缺失（15 帧离开）→ 超过 max_age=10，必须删除并重新分配新 ID
    目标 B（phone）：x 每帧 -4px，从右往左，全程有检测 → 必须始终只有一个 ID

这三条正好对应考核要求里的"遮挡后 ID 保持 / 超时删除 / ID 不复用"。
断言失败会直接报错，可以当回归测试反复跑。

用法:
    python test_tracker_synthetic.py
"""
import json
import os

import numpy as np

from tracker import run_tracker

FRAMES = 180
MAX_AGE = 10


def build():
    frames = []
    for f in range(FRAMES):
        dets = []
        # 目标 A
        if not (40 <= f <= 47) and not (100 <= f <= 114):
            x = 100 + 4 * f
            dets.append({"cls": 0, "conf": 0.9, "bbox": [x, 100, x + 90, 190]})
        # 目标 B
        x = 900 - 4 * f
        dets.append({"cls": 1, "conf": 0.9, "bbox": [x, 300, x + 80, 400]})
        frames.append({"frame": f, "dets": dets})
    return {"video": "synthetic", "fps": 30, "classes": ["cup", "phone"], "frames": frames}


def id_of_class(rec, frame, cls):
    """该帧里类别为 cls 的检测被分配到的航迹 ID"""
    fr = rec["frames"][frame]
    for tid, di in fr["updated"]:
        if det_cls[frame][di] == cls:
            return tid
    return None


def main():
    os.makedirs("results", exist_ok=True)
    data = build()
    path = os.path.join("results", "synthetic_dets.json")
    with open(path, "w") as f:
        json.dump(data, f)

    global det_cls
    det_cls = [[d["cls"] for d in fr["dets"]] for fr in data["frames"]]

    rec = run_tracker(path, draw=False, max_age=MAX_AGE, verbose=False)

    a0 = id_of_class(rec, 39, 0)        # A 在遮挡前
    a1 = id_of_class(rec, 48, 0)        # A 在短遮挡后
    a2 = id_of_class(rec, 115, 0)       # A 在长时间离开后重新出现
    b_ids = {id_of_class(rec, f, 1) for f in range(FRAMES)} - {None}

    last_seen = max(f for f in range(FRAMES) if id_of_class(rec, f, 0) == a0)

    lines = []
    ok = True

    def check(name, cond, detail):
        nonlocal ok
        ok = ok and cond
        lines.append(f"[{'PASS' if cond else 'FAIL'}] {name}: {detail}")

    check("short gap keeps ID", a0 is not None and a0 == a1,
          f"frame39 ID={a0} -> frame48 ID={a1} (gap 8 <= max_age {MAX_AGE})")
    check("long gap issues new ID", a2 is not None and a2 != a0,
          f"frame115 ID={a2} (gap 15 > max_age {MAX_AGE})")
    check("ID never reused", len({a0, a1, a2}) == 2,
          f"IDs used by A = {sorted({a0, a1, a2})}")
    check("continuous target keeps one ID", len(b_ids) == 1,
          f"B used IDs {sorted(b_ids)}")

    dead = [d for d in rec["deaths"] if d["id"] == a0]
    check("deleted after max_age frames", bool(dead),
          f"death record = {dead[0] if dead else None}")
    if dead:
        check("deletion frame correct", dead[0]["frame"] == last_seen + MAX_AGE + 1,
              f"last seen {last_seen}, deleted at {dead[0]['frame']} "
              f"(= last_seen + max_age + 1)")

    pred_frames = [fr["frame"] for fr in rec["frames"]
                   if any(i == a0 for i, _, _ in fr["predicted"])]
    # A 一共断过两次：8 帧（短遮挡）+ 10 帧（离开直到被删除）
    check("predicted boxes drawn during both gaps", pred_frames == list(range(40, 48)) + list(range(100, 110)),
          f"PREDICTED frames for ID {a0} = {pred_frames} (8 + 10 frames, stops at max_age)")

    text = "\n".join(lines)
    print(text)
    with open(os.path.join("results", "synthetic_check.txt"), "w") as f:
        f.write(text + "\n")
    if not ok:
        raise SystemExit("synthetic check FAILED")
    print("\nall synthetic checks passed")


if __name__ == "__main__":
    main()
