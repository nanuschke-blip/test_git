"""纯 ONNX Runtime 的 YOLOv8 推理封装（不依赖 ultralytics，部署/测速都用它）

包含三部分，方便 benchmark.py 分别计时：
    letterbox()   预处理：等比缩放 + 灰边填充到 640x640
    postprocess() 后处理：解码 (1,4+nc,8400) + 置信度过滤 + NMS + 还原到原图坐标
    YoloOnnx      封装上面两步 + session.run
"""
import cv2
import numpy as np


def letterbox(img, new_shape=640, color=(114, 114, 114)):
    h, w = img.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)
    r = min(new_shape[0] / h, new_shape[1] / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    if (w, h) != (nw, nh):
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dw = (new_shape[1] - nw) / 2
    dh = (new_shape[0] - nh) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right,
                             cv2.BORDER_CONSTANT, value=color)
    return img, r, (left, top)


def to_tensor(img):
    x = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = np.transpose(x, (2, 0, 1))[None]
    return np.ascontiguousarray(x)


def postprocess(out, r, pad, orig_shape, conf_thres=0.25, iou_thres=0.45, nc=None):
    """out: session.run 返回的 list，取第一个张量 (1, 4+nc, N)
    -> (boxes xyxy in original image, scores, class ids)"""
    arr = np.asarray(out[0] if isinstance(out, (list, tuple)) else out, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    pred = arr
    if pred.shape[0] < pred.shape[1]:      # (4+nc, N) -> (N, 4+nc)
        pred = pred.T
    boxes_xywh = pred[:, :4]
    cls_scores = pred[:, 4:]
    cls_ids = np.argmax(cls_scores, axis=1)
    scores = cls_scores[np.arange(len(cls_ids)), cls_ids]

    keep = scores >= conf_thres
    if not np.any(keep):
        return np.zeros((0, 4), np.float32), np.zeros((0,), np.float32), np.zeros((0,), np.int32)
    boxes_xywh, scores, cls_ids = boxes_xywh[keep], scores[keep], cls_ids[keep]

    cx, cy, w, h = boxes_xywh.T
    x1 = cx - w / 2
    y1 = cy - h / 2
    left, top = pad
    x1 = (x1 - left) / r
    y1 = (y1 - top) / r
    w = w / r
    h = h / r

    oh, ow = orig_shape[:2]
    x1 = np.clip(x1, 0, ow)
    y1 = np.clip(y1, 0, oh)
    w = np.clip(w, 1, ow)
    h = np.clip(h, 1, oh)

    idx = cv2.dnn.NMSBoxes(np.stack([x1, y1, w, h], 1).tolist(), scores.tolist(),
                           conf_thres, iou_thres)
    if len(idx) == 0:
        return np.zeros((0, 4), np.float32), np.zeros((0,), np.float32), np.zeros((0,), np.int32)
    idx = np.array(idx).reshape(-1)
    xyxy = np.stack([x1[idx], y1[idx], x1[idx] + w[idx], y1[idx] + h[idx]], 1)
    return xyxy.astype(np.float32), scores[idx].astype(np.float32), cls_ids[idx].astype(np.int32)


class YoloOnnx:
    def __init__(self, model_path, imgsz=640, conf=0.25, iou=0.45, providers=None):
        import onnxruntime as ort
        providers = providers or ["CPUExecutionProvider"]
        self.sess = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.sess.get_inputs()[0].name
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self.providers = self.sess.get_providers()

    def predict(self, img):
        """返回 (xyxy, scores, cls_ids)；img 为 BGR 原图"""
        lb, r, pad = letterbox(img, self.imgsz)
        x = to_tensor(lb)
        out = self.sess.run(None, {self.input_name: x})
        return postprocess(out, r, pad, img.shape, self.conf, self.iou)

    def draw(self, img, boxes, scores, cls_ids, names=None, color=(0, 255, 0)):
        for (x1, y1, x2, y2), s, c in zip(boxes, scores, cls_ids):
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            name = names[c] if names and c < len(names) else str(c)
            cv2.putText(img, f"{name} {s:.2f}", (int(x1), max(int(y1) - 8, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        return img
