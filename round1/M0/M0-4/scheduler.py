#!/usr/bin/env python3
"""M0-4 命令行任务调度模拟器"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import yaml

COLORS = {
    "SUCCESS": "\033[92m",  # 绿色
    "FAILED":  "\033[91m",  # 红色
    "RETRY":   "\033[93m",  # 黄色
    "SKIPPED": "\033[94m",  # 蓝色
    "TIMEOUT": "\033[95m",  # 洋红
    "RESET":   "\033[0m",
}

USE_COLOR = sys.stdout.isatty()


def colored(status, text):
    """给状态文本加上颜色（非 TTY 环境自动降级）。"""
    if not USE_COLOR:
        return text
    return f"{COLORS.get(status, '')}{text}{COLORS['RESET']}"

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

from collections import deque


def topological_sort(tasks):
    """按依赖关系对任务做拓扑排序，返回执行顺序列表。

    tasks: {name: {"duration": ..., "success_rate": ..., "dependencies": [...]}}
    返回: [name1, name2, ...]
    异常: 依赖不存在 / 存在环
    """
    # 1. 校验依赖是否存在
    for name, task in tasks.items():
        for dep in task.get("dependencies", []):
            if dep not in tasks:
                raise ValueError(f"任务 {name} 依赖了不存在的任务: {dep}")

    # 2. 计算入度
    indegree = {name: 0 for name in tasks}
    for name, task in tasks.items():
        for dep in task.get("dependencies", []):
            indegree[name] += 1

    # 3. 入度为 0 的入队
    queue = deque([name for name, deg in indegree.items() if deg == 0])
    order = []

    # 4. BFS
    while queue:
        name = queue.popleft()
        order.append(name)
        for other, task in tasks.items():
            if name in task.get("dependencies", []):
                indegree[other] -= 1
                if indegree[other] == 0:
                    queue.append(other)

    # 5. 环检测
    if len(order) != len(tasks):
        raise ValueError("任务依赖存在环，无法排序")

    return order

def run_tasks(tasks, order, timeout=None, start_time=None):
    """按顺序执行任务，处理重试、下游跳过与超时控制。"""
    if start_time is None:
        start_time = time.time()

    status_map = {}
    records = {}
    timed_out = False

    for name in order:
        # 超时检查
        if timeout is not None and (time.time() - start_time) > timeout:
            timed_out = True
            # 当前及后续任务全部标记 TIMEOUT
            for remaining in order[order.index(name):]:
                if remaining not in status_map:
                    status_map[remaining] = "TIMEOUT"
                    records[remaining] = {
                        "name": remaining,
                        "status": "TIMEOUT",
                        "attempts": 0,
                        "duration": 0.0,
                    }
                    print(colored("TIMEOUT", f"[TIMEOUT] {remaining}"))
            break

        task = tasks[name]
        deps = task.get("dependencies", [])

        if not all(status_map.get(dep) == "SUCCESS" for dep in deps):
            status_map[name] = "SKIPPED"
            records[name] = {
                "name": name,
                "status": "SKIPPED",
                "attempts": 0,
                "duration": 0.0,
            }
            print(colored("SKIPPED", f"[SKIPPED] {name}"))
            continue

        success = False
        attempts = 0
        task_start = time.time()
        for attempt in range(1, 4):
            attempts = attempt
            time.sleep(task.get("duration", 0))
            if random.random() < task.get("success_rate", 1.0):
                success = True
                break
            else:
                print(colored("RETRY", f"[RETRY] {name} 第 {attempt} 次失败"))
        elapsed = time.time() - task_start

        if success:
            status_map[name] = "SUCCESS"
            records[name] = {
                "name": name,
                "status": "SUCCESS",
                "attempts": attempts,
                "duration": round(elapsed, 2),
            }
            print(colored("SUCCESS", f"[SUCCESS] {name}"))
        else:
            status_map[name] = "FAILED"
            records[name] = {
                "name": name,
                "status": "FAILED",
                "attempts": attempts,
                "duration": round(elapsed, 2),
            }
            print(colored("FAILED", f"[FAILED] {name}"))

    return records, timed_out

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

    tasks_list = cfg.get("tasks", [])
    if not tasks_list:
        print("错误: 配置中没有任务", file=sys.stderr)
        sys.exit(1)

    tasks = {t["name"]: t for t in tasks_list}
    try:
        order = topological_sort(tasks)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    print("拓扑排序结果:", " -> ".join(order))

    start_time = time.time()

    try:
        records, timed_out = run_tasks(tasks, order, timeout=args.timeout, start_time=start_time)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    total_duration = time.time() - start_time
    print(f"\n总耗时: {total_duration:.2f}s")
    print(f"是否超时: {timed_out}")
        
    report = {
        "timeout": timed_out,
        "total_duration": round(total_duration, 2),
        "tasks": [records[name] for name in order if name in records],
    }

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存到: {args.report}")


if __name__ == "__main__":
    main()