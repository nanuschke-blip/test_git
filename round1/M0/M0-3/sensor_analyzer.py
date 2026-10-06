#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sensor_analyzer.py  —— 上一届学长留下的"能用"的脚本

注释（学长原话）：
    "处理一下传感器数据就能用"

原本意图：
    1. 读取 sensor_data.csv（列：time, value）
    2. 计算 value 的平均值、标准差
    3. 剔除离群值（|value - mean| > 2 * std）
    4. 把清洗后的数据保存为 cleaned_data.csv
    5. 打印一份统计摘要

现状：跑不通 / 跑出来数不对。就交给你了。
"""

import csv
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="传感器数据分析与清洗")
    parser.add_argument("--input", default="sensor_data.csv", help="输入 CSV 文件路径")
    parser.add_argument("--output", default="cleaned_data.csv", help="输出 CSV 文件路径")
    return parser.parse_args()

def main():
    args = parse_args()
    INPUT_FILE = args.input
    OUTPUT_FILE = args.output

    data = []
    times = []


    print("=== 传感器数据分析 ===")

# --- 读取数据 ---
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    t = float(row["time"])
                    v = float(row["value"])
                except (KeyError, ValueError):
                    print("错误: CSV 中缺少 time/value 列或存在非数值内容")
                    exit(1)
                times.append(t)
                data.append(v)
    except FileNotFoundError:
        print("错误: 文件不存在: %s" % INPUT_FILE)
        exit(1)
    print("共读取 %d 条数据" % len(data))

# --- 计算平均值 ---
    total = 0
    for v in data:
        total += v
    mean = total / len(data)

# --- 计算标准差 ---
    acc = 0
    for v in data:
        acc += (v - mean) ** 2
    std = (acc / len(data)) ** 0.5

# --- 剔除离群值 ---
    cleaned_time = []
    cleaned_value = []
    for i in range(len(data)):
        if abs(data[i] - mean) <= 2 * std:
            cleaned_time.append(times[i])
            cleaned_value.append(data[i])

# --- 输出清洗后的数据 ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    f = open(output_path, "w")
    writer = csv.writer(f)
    writer.writerow(["time", "value"])
    for t, v in zip(cleaned_time, cleaned_value):
        writer.writerow([t, v])


    print("均值 mean = %.4f" % mean)
    print("标准差 std = %.4f" % std)
    print("清洗后剩余 %d 条" % len(cleaned_value))
    print("已保存到 %s" % output_path)

if __name__ == "__main__":
    main()