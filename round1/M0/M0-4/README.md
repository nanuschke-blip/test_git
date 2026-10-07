# M0-4 命令行任务调度模拟器

## 一、任务说明

实现一个命令行任务调度模拟器 `scheduler.py`，读取 YAML/JSON 配置文件，按依赖顺序执行任务，支持失败重试、下游跳过、全局超时，并生成 `report.json`。

## 二、参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--config <path>` | 是 | 任务配置文件路径，支持 `.yaml` / `.yml` / `.json` |
| `--timeout <float>` | 否 | 全局超时（秒），覆盖配置文件中的 `timeout` |
| `--report <path>` | 否 | 报告输出路径，默认 `report.json` |
| `--seed <int>` | 否 | 随机种子，便于复现同一结果 |

## 三、配置文件格式

```yaml
timeout: 15
tasks:
  - name: Init
    duration: 0.5
    success_rate: 1.0
    dependencies: []
  - name: Navigate
    duration: 2.5
    success_rate: 0.8
    dependencies: ["Init"]
```

| 字段 | 说明 |
|------|------|
| `timeout` | 全局超时（秒），可选 |
| `tasks` | 任务列表，每个任务包含 `name`、`duration`、`success_rate`、`dependencies` |

## 四、运行示例

### 示例 1：正常执行
```bash
python3 scheduler.py --config tasks_demo.yaml --seed 42 --timeout 100
```
输出所有任务 `[SUCCESS]`，`report.json` 生成。

### 示例 2：超时中止
```bash
python3 scheduler.py --config tasks_demo.yaml --seed 42 --timeout 1
```
执行 `Init`、`Navigate` 后触发 `[TIMEOUT]`，剩余任务标记 `TIMEOUT`。

### 示例 3：依赖成环
把 `Init` 的依赖改成 `["ReturnHome"]`，运行：
```bash
python3 scheduler.py --config tasks_demo.yaml
```
输出 `错误: 任务依赖存在环，无法排序`。

## 五、异常处理

| 异常情况 | 提示 |
|----------|------|
| 配置文件不存在 | `错误: 配置文件不存在: xxx` |
| YAML/JSON 语法错误 | `错误: YAML 解析失败: xxx` |
| 依赖不存在 | `错误: 任务 X 依赖了不存在的任务: Y` |
| 依赖成环 | `错误: 任务依赖存在环，无法排序` |
| 空任务列表 | `错误: 配置中没有任务` |
| `success_rate` 越界 | `错误: 任务 X 的 success_rate 越界: Y` |
| `duration` 非法 | `错误: 任务 X 的 duration 非法: Y` |