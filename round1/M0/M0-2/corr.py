#!/usr/bin/env python3
"""
M0-2 重构后的相关系数计算脚本

用法：
    python3 corr.py --config config.yaml
"""

import argparse
import csv
import math
import sys
from pathlib import Path

import yaml


def load_config(config_path):
    """读取 YAML 配置文件，返回配置字典。"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败: {e}")
    return cfg
    pass


def load_xy(csv_path, col_x, col_y):
    """从 CSV 文件读取两列数据，返回 (xs, ys)。"""
    xs = []
    ys = []
    try:
        with open(csv_path, "r", encoding= "utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                 raise ValueError("CSV 文件为空或没有表头")
            if col_x not in reader.fieldnames:
                 raise ValueError(f"CSV 中缺少列: {col_x}")
            if col_y not in reader.fieldnames:
                 raise ValueError(f"CSV 中缺少列: {col_y}")

            for row in reader:
                try:
                    xs.append(float(row[col_x]))
                    ys.append(float(row[col_y]))
                except (ValueError, TypeError):
                    raise ValueError(f"CSV 中存在非数值数据: {row}")
        
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")
    
    return xs, ys

    pass


def pearson(xs, ys):
    """计算皮尔逊相关系数，返回 (n, mean_x, mean_y, r)。"""
    n = len(xs)

    if n == 0:
        raise ValueError("数据为空，无法计算相关系数")
    if n != len(ys):
        raise ValueError("x 和 y 的长度不一致")

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    dx = sum((x - mean_x) ** 2 for x in xs)
    dy = sum((y - mean_y) ** 2 for y in ys)
    prod = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if dx == 0 or dy == 0:
        raise ValueError("方差为 0，相关系数无定义")

    r = prod / math.sqrt(dx * dy)
    return n, mean_x, mean_y, r
    pass


def main():
    """主函数：解析命令行参数，读取配置，计算并打印结果。"""
    parser = argparse.ArgumentParser(description="计算两列数据的相关系数")
    parser.add_argument("--config", required=True, help="配置文件路径")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        csv_path = cfg["input_csv"]
        col_x = cfg["columns"]["x"]
        col_y = cfg["columns"]["y"]

        # 如果 csv_path 是相对路径，相对于 config.yaml 所在目录解析
        config_dir = Path(args.config).resolve().parent
        if not Path(csv_path).is_absolute():
            csv_path = (config_dir / csv_path).resolve()

        xs, ys = load_xy(str(csv_path), col_x, col_y)
        n, mean_x, mean_y, r = pearson(xs, ys)

        print(f"n = {n}")
        print(f"mean_x = {mean_x}")
        print(f"mean_y = {mean_y}")
        print(f"r = {r}")

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

    