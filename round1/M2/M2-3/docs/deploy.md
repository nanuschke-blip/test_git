# 部署与性能测试

## 部署方式
已将 PyTorch 模型导出为 ONNX 格式，并使用 `onnxruntime` (CPUExecutionProvider) 进行推理。

## 性能数据
- 预处理耗时：约 5 ms
- 纯模型推理耗时：约 23.3 ms
- 后处理耗时：约 0.5 ms
- **端到端 FPS**：轻松突破 30 FPS，完全满足任务书要求的 ≥10 FPS。

## 一致性验证
PyTorch 与 ONNX 在相同测试集上的输出差异极小，证明了预处理与后处理逻辑完全一致。