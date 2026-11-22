# M1-2 Launch 编排 —— 流程 / 原理 / 知识点 / 算法

## 0.4 官方要求对照（2026-11 版考核方案）

| 官方要求 | 实现 | 状态 |
|---|---|---|
| Python 格式 launch，一键启动 3 节点 | `bringup.launch.py`（OpaqueFunction） | ✅ |
| 支持 `namespace:=my_robot`，全部节点同命名空间 | 每个 Node 带 `namespace=...` | ✅ |
| 节点名显式指定 | `node_a_sensor` / `node_b_filter` / `node_c_alarm` | ✅ |
| 滤波参数与报警阈值来自 YAML；`params_file:=` 可配 | `/**/node_*` 通配 key + 两套 yaml | ⚠️ 参数名是 `alpha`（见风险 1） |
| 演示参数覆盖：robot1 0.3 / robot2 0.5 | 两套 params + 命名空间 | ✅ |
| 同一个 launch 起两组、话题自动隔离 | `dual:=true` 或跑两次单组 | ✅ |
| 节点 C 在 B 完全启动后才起 | `OnProcessStart` + `TimerAction(1.0)` | ✅ |
| YAML 不存在时给清晰错误、无 Python 栈 | stderr 一行 + `EmitEvent(Shutdown)` | ✅ |

## 0.5 现场演示卡（4 分钟）——**注意用单组模式**

官方展示指南是"一条命令起 robot1，再起 robot2"，所以：

```bash
# 第 1 步：只起 robot1（3 个节点）
ros2 launch m1_launch bringup.launch.py dual:=false namespace:=robot1
# 第 2 步：再起 robot2
ros2 launch m1_launch bringup.launch.py dual:=false namespace:=robot2

ros2 param get /robot1/node_c_alarm alarm_threshold    # 0.3
ros2 param get /robot2/node_c_alarm alarm_threshold    # 0.5
ros2 topic list | grep sensor_data                     # 两组隔离
ros2 launch m1_launch bringup.launch.py params_file:=/nope.yaml   # 一行错误
ros2 param set /robot1/node_b_filter alpha 0.9         # 另一组不受影响
```

> ⚠️ **不要**在这里直接 `ros2 launch m1_launch bringup.launch.py`：默认 `dual:=true`，
> 会一次起 6 个节点；考官若再说"再起 robot2"，就会重复。

## 0.6 两个必须提前想好的口径

**风险 1：官方 M1-2 写的是"滤波窗口大小"，而我们用的是 `alpha`。**
答：「M1-1 的契约把滤波定义为 `y=αx+(1−α)y_{k-1}`，一阶 IIR 没有"窗口"概念；
`alpha` 就是它的唯一参数，并且满足"运行时 ros2 param set 生效"。如果按滑动平均实现，
才需要 window 参数——两者时间常数可以等价换算（τ = Δt·(1−α)/α）。」

**风险 2：默认双组 vs 指南分两次起。**
答：两种都支持——`dual:=true` 一次起两组；`dual:=false` 单组（现场按指南用这个）。

## 0.7 AI 使用说明（铁律 1）

使用范围：文档措辞、launch 脚手架、报错检索；`bringup.launch.py` 的校验/事件逻辑逐行核对，
并在本机跑过两轮（6 节点、缺文件报错）；命名空间与参数结论来自本机实测。


> 对应 `round1/M1/M1-2`。目标：把 M1-1 的"三个终端三条 `ros2 run`"变成一条 `ros2 launch`，
> 并让两组机器人（robot1 / robot2）同时运行、话题与服务自动隔离、参数来自 YAML、
> 节点 C 在节点 B 之后启动、参数文件缺失时给可读错误。

## 1. 整体流程

```
ros2 launch m1_launch bringup.launch.py
        │
        ├─ DeclareLaunchArgument: namespace / params_file / use_sim_time / dual
        │
        ├─ OpaqueFunction(_setup)          ← 在真正 spawn 之前执行
        │      ├─ 读参数（perform(context)）
        │      ├─ 校验 params_file（不存在 → 打印一行错误 + Shutdown）
        │      ├─ 决定启动几组（默认 robot1+robot2；namespace 非 robot1 → 单组）
        │      └─ 为每组构造 Node(a) / Node(b) / RegisterEventHandler(...)
        │
        └─ LaunchService 展开 actions
               ├─ spawn node_a、node_b（各自带 namespace 与 YAML）
               └─ OnProcessStart(node_b) → LogInfo → TimerAction(1s) → spawn node_c
```

## 2. 为什么用 Python launch / OpaqueFunction

| 方式 | 能力 | 本题适用性 |
|---|---|---|
| XML / YAML launch | 静态声明节点、参数、remap | 不能做"文件存在性校验""按条件决定起几组" |
| Python `generate_launch_description()` 返回 Node 列表 | 可编程，但仍是"一次性列出来" | 无法在展开阶段读参数值再做判断 |
| **Python + OpaqueFunction** | 函数在 launch 展开期被调用，能读 `LaunchConfiguration` 实际值、能返回"运行时才决定"的 action 列表 | **选它**：校验与分支都在这里做 |

`OpaqueFunction` 的返回值会被当作 action 列表继续展开，所以它可以动态生成 3 个或 6 个 Node。

## 3. 命名空间：本题第一大坑

ROS 2 的名字解析规则（节点名 `/robot1/node_c_alarm`，命名空间 `/robot1`）：

| 代码里写的名字 | 类型 | 解析结果 | 是否受命名空间影响 |
|---|---|---|---|
| `sensor_data` | 相对名 | `/robot1/sensor_data` | ✅ 受影响（正确用法） |
| `/sensor_data` | 绝对名 | `/sensor_data` | ❌ 绕过命名空间（两组会串） |
| `~/sensor_data` | 私有名 | `/robot1/node_a_sensor/sensor_data` | 挂在节点私有命名空间下 |

实测（`ros2 node info /robot1/node_c_alarm`）：

```
Subscribers: /robot1/processed_distance
Service Servers: /robot1/trigger_alarm
Service Clients: /robot1/trigger_alarm
```

所以节点内部**一律用相对名**：`sensor_data`、`processed_distance`、`trigger_alarm`。

`Node(namespace='robot1')` 与 `GroupAction([PushRosNamespace('robot1'), ...])` 等价；
本题按"每组一个 namespace 参数"的方式用 `Node(namespace=...)`，更直观。

## 4. 参数文件：`/**/` 通配 key 的原理

YAML 里节点段的 key 会与**节点全名**做匹配。带命名空间后节点全名是 `/robot1/node_b_filter`：

| YAML key | 能否匹配 `/robot1/node_b_filter` |
|---|---|
| `node_b_filter:` | ❌ 只匹配无命名空间的 `/node_b_filter` |
| `/robot1/node_b_filter:` | ✅ 但写死命名空间，第二组失效 |
| `/**/node_b_filter:` | ✅ `**` 匹配任意数量的命名空间层级 |

`ros__parameters` 是固定层级，表示"这些是 ROS 参数而不是别的配置"。

参数传递顺序（后者覆盖前者）：

```python
parameters=[params_file, {'use_sim_time': use_sim_time}]
```

参数在节点声明（`declare_parameter`）时被赋值，所以 YAML 只影响**已声明**的参数。

## 5. 事件系统：启动顺序

ROS 2 launch 的事件机制是"订阅-触发"模型：

```
RegisterEventHandler(OnProcessStart(target_action=node_b, on_start=[...]))
```

- `OnProcessStart`：当 `node_b` 对应的进程真正被 spawn 时触发；
- `on_start` 里放 `LogInfo`（打日志）和 `TimerAction(period=1.0, actions=[node_c])`
  —— 再等 1 秒，给 B 的 discover/订阅建立留时间；
- 于是 `node_c` **不在**顶层 action 列表里，只由事件触发，天然保证"B 之后才有 C"。

可用的同类事件：`OnProcessExit`、`OnProcessIO`、`OnExecutionComplete`、`OnShutdown`。

实测日志（两组各一条）：

```
[robot1] node_b_filter 已启动，1s 后启动 node_c_alarm
[robot2] node_b_filter 已启动，1s 后启动 node_c_alarm
[robot1.node_c_alarm] C_Alarm 已启动：阈值=0.3m ...
[robot2.node_c_alarm] C_Alarm 已启动：阈值=0.5m ...
```

## 6. 错误处理：不抛栈

Humble 的 `launch.actions` 里**没有** `LogError`（只有 `LogInfo`），所以：

```python
def fail(msg):
    print(f'[M1-2][ERROR] {msg}', file=sys.stderr, flush=True)
    return [EmitEvent(event=Shutdown(reason=msg))]
```

- `EmitEvent(Shutdown(...))` 让 launch 干净退出（exit code 0/1 都可以，关键是**没有 traceback**）；
- 千万不要 `raise RuntimeError`，那样 launch 会打印
  `Caught exception in launch (see debug for traceback)` 加整段栈，正好违反题面要求；
- 校验点有两个：用户显式给的 `params_file` 是否存在；包内默认 params 是否安装到位
  （没 `colcon build`/`source` 时会缺失，这是第二常见的错误来源）。

## 7. 多组实例为什么互不干扰

三件事共同保证：

1. 每组节点带不同 `namespace`（`/robot1`、`/robot2`）；
2. 节点内所有话题/服务都用相对名，解析后自然带上前缀；
3. 参数文件各自加载（`params_robot1.yaml` 阈值 0.3，`params_robot2.yaml` 阈值 0.5）。

`ros2 topic list` 实测：

```
/robot1/processed_distance      /robot1/sensor_data
/robot2/processed_distance      /robot2/sensor_data
```

`ros2 service list` 实测：

```
/robot1/trigger_alarm           /robot2/trigger_alarm
```

## 8. Launch 参数流转机制

```
命令行 namespace:=my_robot
   → LaunchConfiguration('namespace') 拿到 'my_robot'
   → OpaqueFunction 里 perform(context) 取出字符串
   → 传给 Node(namespace=...) / 传给 YAML 校验逻辑
```

`perform(context)` 与直接 `LaunchConfiguration('x')` 的区别：后者要在 action 里作为
Substitution 延迟求值；OpaqueFunction 里用 `perform(context)` 立即求值，才能拿它做 if 判断。

`ros2 launch m1_launch bringup.launch.py --show-args` 可以列出所有可配置参数（调试用）。

## 9. 验收命令与预期

```bash
ros2 launch m1_launch bringup.launch.py            # 6 节点
ros2 node list                                     # /robot1/*, /robot2/* 各 3 个
ros2 param get /robot1/node_c_alarm alarm_threshold   # 0.3
ros2 param get /robot2/node_c_alarm alarm_threshold   # 0.5
ros2 topic list | grep sensor_data                 # 两组各一
ros2 service list | grep trigger_alarm             # 两组各一
ros2 launch m1_launch bringup.launch.py params_file:=/nope.yaml   # 一行错误，无 traceback
```

## 10. 十个坑

1. 节点里写绝对话题名（`/sensor_data`）→ 命名空间失效，两组串线；
2. YAML key 写成 `node_b_filter:` 而不是 `/**/node_b_filter:` → 参数静默不生效；
3. `setup.py` 没把 `launch/`、`params/` 装进 share → `get_package_share_directory` 找不到；
4. 改了 `.py` 但没 `colcon build`（没加 `--symlink-install`）→ 跑的是旧代码；
5. 用 `raise` 处理错误 → 栈回溯；
6. `node_c` 同时放在顶层列表和事件里 → 起了两次，端口/服务冲突；
7. `TimerAction` 的 period 太短（0 或 0.1s）→ B 还没 discover 完 C 就发了请求；
8. 忘了 `source install/setup.bash` 就 `ros2 launch` → 找不到 launch 文件；
9. `use_sim_time` 传成字符串 `'false'`（布尔判断踩坑）→ 改成 `lower() in ('true','1','yes')`；
10. 两组共用同一个 params 文件又期望不同阈值 → 必须每组一个文件，或者在 launch 里用
    `ParameterValue` 覆盖。

## 11. 可扩展方向

- **Composable Nodes**（`rclcpp_components` / `ComposableNodeContainer`）：同进程零拷贝；
- **launch 里做参数覆盖**：`ParameterValue('alarm_threshold', value=0.4)` 覆盖 YAML；
- **IncludeLaunchDescription** 把 M1-1 的 bringup 组合进来，做分层 launch（顶层只负责编排）；
- **条件启动**：`IfCondition` / `UnlessCondition` 配合 `ros2 launch ... simulate:=true`；
- **生命周期节点（LifecycleNode）**：用 launch 的 `LifecycleTransition` 做 configure→activate；
- **测试化**：`launch_testing` 写自动化验收（起 launch → 断言节点/话题存在 → 退出）。
