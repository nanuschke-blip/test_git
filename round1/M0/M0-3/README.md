# M0-3 代码排查 —— 问题报告

## 一、任务说明

修复 `sensor_analyzer.py` 中的多处缺陷，使其能正确处理 `sensor_data.csv`，剔除离群值，输出 `cleaned_data.csv`，并打印统计摘要。

原始代码存在 **8 处缺陷**，且**修复顺序存在依赖**：前一个不修，后一个现象会被掩盖。

## 二、缺陷清单与修复

| 序号 | 缺陷位置 | 现象 | 原因 | 修复方式 |
|------|----------|------|------|----------|
| 1 | `row["Value"]` | 报 `KeyError: 'Value'` | CSV 列名是 `value`，大小写不匹配 | 改为 `row["value"]` |
| 2 | 标准差计算 `acc += (v - mean); std = acc / len(data)` | 结果接近 0，离群值判断失效 | 离差有正负，直接相加会抵消；标准差应为离差平方和除以 n 后开根号 | 改为 `acc += (v - mean) ** 2`，再 `std = (acc / len(data)) ** 0.5` |
| 3 | `for v in data: if v > mean + 2*std: data.remove(v)` | 漏删离群值，甚至报错 | 边遍历边删除会跳过元素；且只判断了正方向，漏掉负向离群值 | 改用新列表 `cleaned_time` / `cleaned_value` 筛选，条件为 `abs(v - mean) <= 2 * std` |
| 4 | `os.path.join("/", OUTPUT_DIR, OUTPUT_FILE)` | 报 `Permission denied` | 路径写死为根目录 `/out/`，普通用户无权限 | 改为当前目录，并用 `os.makedirs(OUTPUT_DIR, exist_ok=True)` 自动创建输出目录 |
| 5 | `writer.writerow([v])` | `cleaned_data.csv` 只有一列，缺少 time | 写回时只写了 value，未保留 time 列 | 保留 `cleaned_time` 和 `cleaned_value`，写入时写 `[t, v]` 两列 |
| 6 | 缺少异常处理 | 文件不存在、列名不符、非数值内容时直接抛 Traceback | 未捕获异常 | 用 `try/except` 捕获 `FileNotFoundError`、`KeyError`、`ValueError`，打印可读错误并 `exit(1)` |
| 7 | 路径写死 | 无法指定输入输出文件 | 缺少命令行参数支持 | 引入 `argparse`，支持 `--input` 和 `--output`，默认值为当前目录下的 `sensor_data.csv` / `cleaned_data.csv` |
| 8 | 所有逻辑在全局 | 被 import 时会直接执行 | 缺少 `main()` 封装和 `__main__` 保护 | 用 `main()` 函数封装主流程，末尾加 `if __name__ == "__main__": main()` |

## 三、修复顺序说明

修复顺序遵循依赖关系：

1. **先修列名（缺陷 1）**：否则连数据都读不进来。
2. **再修标准差公式（缺陷 2）**：否则离群值判断完全失效。
3. **再修离群值剔除逻辑（缺陷 3）**：标准差正确后，才能正确筛选。
4. **再修输出路径（缺陷 4）**：否则写文件时报权限错误。
5. **再修输出列（缺陷 5）**：保证 `cleaned_data.csv` 包含 time 和 value 两列。
6. **加异常处理（缺陷 6）**：保证异常输入不崩溃。
7. **加命令行参数（缺陷 7）**：满足验收要求，支持指定输入输出。
8. **加 main 封装（缺陷 8）**：符合工程规范。

## 四、验证方式

### 正常运行
```bash
python3 sensor_analyzer.py --input sensor_data.csv --output cleaned_data.csv
```

输出示例：
```
共读取 40 条数据
均值 mean = 49.4378
标准差 std = 24.xxxx
清洗后剩余 xx 条
已保存到 cleaned_data.csv
```

### 异常输入测试
- 文件不存在：提示 `错误: 文件不存在: xxx`
- 列名不符：提示 `错误: CSV 中缺少 time/value 列或存在非数值内容`
- 空文件：不崩溃，给出可读提示

## 五、常见追问准备

- 你一共发现了几处缺陷？→ 8 处。
- 为什么修好标准差公式之前，离群值一个都没删掉？→ 因为原标准差算出来接近 0，`mean ± 2*std` 范围极窄，几乎所有值都被判定为离群，但原代码只删正方向且边遍历边删，结果反而漏删。
- 一边遍历列表一边 `remove` 会发生什么？为什么？→ 会跳过元素，因为删除后索引会前移，导致部分元素没被检查到。
- 如果数据只有 1 行，标准差会怎样？怎么处理？→ 样本数为 1 时，离差为 0，标准差为 0，方差为 0，相关系数/离群判断无定义，应提前判断并给出提示。
- 你用什么工具/方法定位问题的？→ 通过运行报错定位、打印中间变量（mean、std）验证、逐段注释排查。