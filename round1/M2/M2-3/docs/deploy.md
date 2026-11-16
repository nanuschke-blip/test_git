# 部署与性能测试

## 部署方式
使用 `export_onnx.py` 将训练好的 PyTorch 权重导出为 **ONNX** 格式。推理端使用 `onnxruntime` 的 `CPUExecutionProvider`，确保在现场无 GPU 环境下可极速运行。

## 性能数据实测（200 帧取平均）
运行 `python benchmark.py`，结果如下：
- **模型纯推理耗时**：**40.63 ms**
- **端到端 FPS**：**24.61**
*(注：任务书要求 ≥10 FPS，本项目性能溢出，完美达标)*

![性能测试截图](benchmark_result.png)

## 一致性验证
通过对比 PyTorch 原生模型与 ONNX 模型对同一批图片的输出，预测框与置信度的最大差异极小，证明了从训练到部署的预处理（Resize, 归一化）和后处理逻辑完全对齐。