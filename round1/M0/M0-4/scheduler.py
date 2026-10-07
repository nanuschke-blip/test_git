#!/usr/bin/env python3
"""M0-4 命令行任务调度模拟器"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import yaml


def load_config(path):
    """读取 YAML 或 JSON 配置文件，返回配置字典。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(p, "r", encoding="utf-8") as f:
        if p.suffix in (".yaml", ".yml"):
            cfg = yaml.safe_load(f)
        elif p.suffix == ".json":
            cfg = json.load(f)
        else:
            raise ValueError(f"不支持的配置文件格式: {p.suffix}")

    if not isinstance(cfg, dict):
        raise ValueError("配置文件内容必须是一个字典")
    return cfg


def main():
    parser = argparse.ArgumentParser(description="任务调度模拟器")
    parser.add_argument("--config", required=True, help="任务配置文件路径")
    parser.add_argument("--timeout", type=float, default=None, help="全局超时（秒）")
    parser.add_argument("--report", default="report.json", help="报告输出路径")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    try:
        cfg = load_config(args.config)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    print("配置加载成功，任务数:", len(cfg.get("tasks", [])))
    # TODO: 下一步实现拓扑排序、执行、报告


if __name__ == "__main__":
    main()