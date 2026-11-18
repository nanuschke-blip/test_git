# M1-1 三节点链路与动态配参

一条最小的 ROS 2 数据闭环：**模拟传感器 → 一阶低通滤波 → 近距报警**。
三个节点各自独立进程，用话题串起来，报警通过自定义服务触发，滤波系数用 ROS 参数在运行时动态修改。

```
node_a_sensor  --/sensor_data (sensor_interfaces/msg/SensorData)-->  node_b_filter
node_b_filter  --/processed_distance (std_msgs/msg/Float32)-------->  node_c_alarm
node_c_alarm   --/trigger_alarm (sensor_interfaces/srv/TriggerAlarm)->  alarm_server
```

## 目录结构

```text
M1-1/
├── src/
│   ├── sensor_interfaces/          # 自定义接口包（ament_cmake）
│   │   ├── CMakeLists.txt
│   │   ├── package.xml
│   │   ├── msg/SensorData.msg
│   │   └── srv/TriggerAlarm.srv
│   └── m1_nodes/                   # 四个可执行节点（ament_python）
│       ├── package.xml
│       ├── setup.py
│       ├── setup.cfg
│       ├── resource/m1_nodes
│       └── m1_nodes/
│           ├── __init__.py
│           ├── node_a_sensor.py    # 节点A：10 Hz 发布模拟距离
│           ├── node_b_filter.py    # 节点B：低通滤波 + 动态 alpha
│           ├── node_c_alarm.py     # 节点C：近距报警 + 服务超时处理
│           └── node_c_server.py    # 报警服务端（独立进程，便于"杀掉服务端"测试）
└── README.md
```

## 环境

- Ubuntu 22.04 + ROS 2 Humble
- Python 3.10、`rclpy`
- 无第三方依赖

```bash
source /opt/ros/humble/setup.bash
```

## 编译

```bash
cd M1-1                     # 或你的工作空间根目录（含 src/）
colcon build --symlink-install
source install/setup.bash
```

> 建议加 `--symlink-install`：改完 Python 源码不用重新 `colcon build`，否则改完必须重新编译，
> 否则跑的还是安装目录里的旧拷贝（这是最容易踩的坑）。

## 运行（四个终端，顺序有讲究）

```bash
# 终端 1：报警服务端（先起，否则节点C 第一次报警会立刻判超时）
ros2 run m1_nodes alarm_server

# 终端 2：节点A 模拟传感器
ros2 run m1_nodes node_a

# 终端 3：节点B 滤波
ros2 run m1_nodes node_b

# 终端 4：节点C 报警
ros2 run m1_nodes node_c
```

节点名固定为 `node_a_sensor` / `node_b_filter` / `node_c_alarm` / `alarm_server`，
话题与服务名、消息字段严格按下方契约。

## 接口契约

### 自定义消息 `sensor_interfaces/msg/SensorData`

| 字段 | 类型 | 说明 |
|---|---|---|
| `distance` | `float32` | 模拟超声波距离（米） |
| `unit` | `string` | 单位，固定 `"m"` |
| `stamp` | `builtin_interfaces/Time` | 消息生成时间 |
| `status` | `uint8` | 0=正常，1=超量程，2=传感器错误 |

### 自定义服务 `sensor_interfaces/srv/TriggerAlarm`

```
float32 current_distance
---
bool success
string message
```

### 话题与服务

| 名称 | 类型 | 方向 |
|---|---|---|
| `/sensor_data` | `sensor_interfaces/msg/SensorData` | A → B |
| `/processed_distance` | `std_msgs/msg/Float32` | B → C |
| `/trigger_alarm` | `sensor_interfaces/srv/TriggerAlarm` | C 调用 |

### 参数

| 节点 | 参数 | 类型 | 默认值 |
|---|---|---|---|
| node_b_filter | `alpha` | double | 0.3 |
| node_c_alarm | `alarm_threshold` | double | 0.3 |
| node_c_alarm | `service_timeout` | double | 1.0 |

## 验证（对应考核的四条）

```bash
# 1) 三节点在跑、频率约 10 Hz
ros2 node list
ros2 topic list
ros2 topic hz /processed_distance

# 2) 动态改滤波系数，并观察平滑程度变化
ros2 param set /node_b_filter alpha 0.9
ros2 param get /node_b_filter alpha

# 3) 手动调一次服务，确认服务端有响应
ros2 service call /trigger_alarm sensor_interfaces/srv/TriggerAlarm \
    "{current_distance: 0.2}"

# 4) 杀掉服务端（Ctrl+C 终端 1），等下一次近距数据
#    节点C 必须打印：[WARN] 报警服务超时 (1.0 秒无响应)
#    而不是阻塞等待或崩溃
```

## 三个节点各自在做什么

**节点A（`node_a_sensor`）**：以 10 Hz 定时器发布 `SensorData`。距离用 **4 秒一周期的正弦扫掠**
（0.15 ~ 1.05 m，叠加 ±0.02 m 抖动），保证周期性地进入 `< 0.3 m` 的报警区，演示时不用干等；
另有 10% 的概率注入 `status=1`、距离 9.99 m 的超量程假数据，用来检验节点B 的无效数据过滤。

**节点B（`node_b_filter`）**：一阶低通滤波

```
y_k = alpha * x_k + (1 - alpha) * y_{k-1}
```

- `alpha` 通过 `declare_parameter` 声明为 double（默认 0.3），`add_on_set_parameters_callback`
  注册回调，`ros2 param set` 后立刻生效并在日志里打印新值；
- `status != 0` 的数据**不参与滤波**（不更新 `y_{k-1}`），只打印 `[WARN]` 警告；
- 第一帧用原始值初始化，避免从 0 慢慢爬升；
- 结果以 `std_msgs/msg/Float32` 发布到 `/processed_distance`。

**节点C（`node_c_alarm`）**：距离低于阈值时调用报警服务

- 阈值与超时都由参数控制（默认 0.3 m / 1.0 s），同样支持 `ros2 param set`；
- 用 `call_async` + `future.add_done_callback` 做**非阻塞**调用；
- 同时创建一个 `service_timeout` 周期的定时器：到点时若 `future` 还没完成，打印
  `[WARN] 报警服务超时`，并销毁定时器、释放"在途"标志；
- `pending` 标志保证同一时刻只有一个请求在飞，避免 10 Hz 下请求堆积。

**服务端（`alarm_server`）**：打印 `[ALARM] 距离过近！当前距离: x.xxm`，返回
`success=True, message="Alarm triggered successfully"`。
单独做成一个进程，是因为考核要求"杀掉服务端看节点C 是否超时"——如果服务端和节点C
在同一个进程里，杀掉服务端等于把客户端也杀了。

## 常见问题

**Q1：`ros2 topic hz /processed_distance` 只有约 9 Hz，不是 10 Hz？**
节点A 以 10 Hz 发布，节点B 会丢弃约 10% 的无效数据（`status != 0`），所以下游约 9 Hz。
要贴近 10 Hz 可把节点A 的异常概率调小。

**Q2：改完代码运行还是旧行为？**
没有 `--symlink-install`，必须重新 `colcon build` 并 `source install/setup.bash`。

**Q3：为什么不用同步的 `call()` 加 `time.sleep()` 判超时？**
同步调用会阻塞订阅回调，单线程 executor 下一个回调阻塞会让定时器、其它订阅全部停摆，
"超时"本身也会失去意义；用异步 future + 定时器才能既不阻塞又能知道超时。

**Q4：服务端还没起来就报警会怎样？**
`call_async` 会把请求挂起，1 秒内服务端就绪则正常返回；超过 1 秒就打印超时警告。
所以建议先起 `alarm_server` 再起 `node_c`。

## 已知限制

- 报警只做"打印 + 返回成功"，没有真实的声光执行器；
- 一次报警只发一次请求（`pending` 限流），如果目标持续过近，需要等上一次结束才会再次触发；
- 模拟数据是正弦扫掠 + 小幅抖动，没有实现真实超声波的噪声模型与刷新率抖动。
