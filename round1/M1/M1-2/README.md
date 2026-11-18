# M1-2 Launch 编排：一键启动 + 命名空间隔离 + 参数文件 + 启动顺序

把 M1-1 的"三个终端敲三条 `ros2 run`"变成**一条命令**，并且能让**两组机器人同时跑、互不干扰**。

## 目录结构

```text
M1-2/
├── params_robot1.yaml          # robot1 参数（报警阈值 0.3，题面要求放在这里）
├── params_robot2.yaml          # robot2 参数（报警阈值 0.5）
├── README.md
└── src/
    ├── sensor_interfaces/      # 自定义 msg/srv（与 M1-1 同一契约，复制一份使本目录自包含）
    │   ├── CMakeLists.txt  package.xml  msg/SensorData.msg  srv/TriggerAlarm.srv
    └── m1_launch/              # 三节点 + launch + 参数（ament_python）
        ├── package.xml  setup.py  setup.cfg  resource/m1_launch
        ├── m1_launch/{__init__,node_a_sensor,node_b_filter,node_c_alarm}.py
        ├── launch/bringup.launch.py
        └── params/{params_robot1.yaml,params_robot2.yaml}
```

> 根目录的两个 YAML 与 `src/m1_launch/params/` 里内容一致：前者满足题面的交付清单，
> 后者随包安装（`colcon build` 后 launch 默认读的就是包里这份）。

## 编译

```bash
cd M1-2
colcon build --symlink-install
source install/setup.bash
```

## 用法（四种模式）

| 命令 | 效果 |
|---|---|
| `ros2 launch m1_launch bringup.launch.py` | **默认双组**：`/robot1` + `/robot2`，共 **6 个节点** |
| `ros2 launch m1_launch bringup.launch.py dual:=false` | 只起一组（`/robot1`，3 个节点） |
| `ros2 launch m1_launch bringup.launch.py namespace:=my_robot` | 单组、命名空间换成 `/my_robot` |
| `ros2 launch m1_launch bringup.launch.py params_file:=/abs/path/params.yaml` | 用你自己的参数文件（双组共用） |
| `ros2 launch m1_launch bringup.launch.py params_file:=/nope.yaml` | **清晰报错**并退出：`[M1-2][ERROR] 参数文件不存在: /nope.yaml ...` |

Launch 参数（题面契约）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `namespace` | `robot1` | 命名空间；给非 `robot1` 的值时只启动单组 |
| `params_file` | 空 | YAML 参数文件路径；留空则用包内 `params_robot{1,2}.yaml` |
| `use_sim_time` | `false` | 传给所有节点 |
| `dual` | `true` | `true` 起两组，`false` 只起一组 |

## 验证（对应考核四条）

```bash
# 1) 两组同时在跑：应看到 /robot1/... 与 /robot2/... 共 6 个
ros2 node list

# 2) 同一条 Launch，不同命名空间取到不同阈值：0.3 / 0.5
ros2 param get /robot1/node_c_alarm alarm_threshold
ros2 param get /robot2/node_c_alarm alarm_threshold

# 3) 话题自动隔离
ros2 topic list | grep sensor_data          # 应看到 /robot1/sensor_data 与 /robot2/sensor_data
ros2 topic hz /robot1/processed_distance    # 约 9~10 Hz（丢掉约 10% 无效数据）
ros2 topic hz /robot2/processed_distance

# 4) 不存在的参数文件：只报错、不崩栈
ros2 launch m1_launch bringup.launch.py params_file:=/nope.yaml
```

启动顺序的证据在终端日志里：每组都会先出现

```
[robot1] node_b_filter 已启动，1s 后启动 node_c_alarm
```

之后才是 `node_c_alarm` 的启动日志——说明节点 C 确实等到 B 起来之后才启动。

## 实现要点

1. **Python Launch + OpaqueFunction**
   `OpaqueFunction` 在 launch 展开阶段执行，可以在真正 spawn 进程之前读参数、校验文件、
   动态决定"起一组还是两组"，这是纯 `Node()` 列表做不到的。

2. **命名空间隔离**
   每个 `Node(namespace=<ns>, ...)`；节点内部所有话题/服务都用**相对名**（`sensor_data`、
   `processed_distance`、`trigger_alarm`），ROS 会自动补成 `/<ns>/...`。
   如果写成绝对名 `/sensor_data`，命名空间会被绕过，两组就串在一起了——这是本题第一大坑。

3. **参数文件与 `/**/` 通配 key**
   YAML 里写成：

   ```yaml
   /**/node_b_filter:
     ros__parameters:
       alpha: 0.3
   ```

   `/**/` 匹配任意命名空间。若写成 `node_b_filter:`，在 `/robot1/node_b_filter` 这种
   带命名空间的节点上匹配不到，参数会静默失效（`ros2 param get` 拿到的还是代码里的默认值）。

4. **启动顺序**
   `RegisterEventHandler(OnProcessStart(target_action=node_b, on_start=[...]))

   - 里放 `TimerAction(period=1.0, actions=[node_c])`：B 进程起来后等 1 秒再起 C，
   保证 C 创建服务/客户端时链路的上下游都已就绪。

5. **错误处理不抛栈**
   文件不存在时返回 `[LogError(msg=...), EmitEvent(event=Shutdown(reason=...))]`，
   launch 打印一行可读错误并退出。**不要用 `raise RuntimeError`**——那样会把 Python
   traceback 打到终端，正好违反题面要求。

6. **每组三个节点**
   题面要求每组 3 个节点，所以报警服务端并入 `node_c_alarm`（同一节点里既 `create_service`
   又 `create_client`，服务名相同、相对名，因此每组各有一个服务端，互不干扰）。
   M1-1 里单独拆出 `alarm_server` 是为了考"杀掉服务端看超时"，M1-2 不考这一点。

## 常见问题

**Q1：`ros2 param get` 读到的是 0.3/0.5 之外的默认值？**
YAML 的 key 没写 `/**/`，或者 `setup.py` 里没把 `params/*.yaml` 装进 share。先
`ros2 param dump /robot1/node_c_alarm` 看实际加载了什么。

**Q2：两组话题串了？**
节点里用了绝对名（`/sensor_data`）。改成相对名即可。

**Q3：报 "default params file missing"？**
没 `colcon build` 或没 `source install/setup.bash`，launch 找不到包内的 params 目录。

**Q4：为什么 `namespace` 给非 `robot1` 的值就只起一组？**
这是为了让 `ros2 launch ... namespace:=my_robot` 这种"改命名空间"的用法只产出一组，
而不是把 `my_robot` 和 `robot2` 混着起。需要两组时用默认命令或 `dual:=true`。
