"""M1-2 一键启动：三节点链路 + 参数文件 + 命名空间隔离 + 启动顺序 + 错误处理

用法：
  ros2 launch m1_launch bringup.launch.py                       # 默认双组：robot1 + robot2（6 个节点）
  ros2 launch m1_launch bringup.launch.py dual:=false           # 只起一组（robot1，3 个节点）
  ros2 launch m1_launch bringup.launch.py namespace:=my_robot   # 单组，改命名空间
  ros2 launch m1_launch bringup.launch.py params_file:=/path/params.yaml
"""
import os
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, LogInfo, OpaqueFunction,
    RegisterEventHandler, TimerAction,
)
from launch.event_handlers import OnProcessStart
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = 'm1_launch'


def _default_params(name):
    return os.path.join(get_package_share_directory(PKG), 'params', name)


def _make_group(namespace, params_file, use_sim_time):
    """一组：三个节点 + “B 启动后再起 C”的事件处理。话题/服务名都是相对名。"""
    node_a = Node(
        package=PKG, executable='node_a', name='node_a_sensor',
        namespace=namespace, output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
    )
    node_b = Node(
        package=PKG, executable='node_b', name='node_b_filter',
        namespace=namespace, output='screen',
        parameters=[params_file, {'use_sim_time': use_sim_time}],
    )
    node_c = Node(
        package=PKG, executable='node_c', name='node_c_alarm',
        namespace=namespace, output='screen',
        parameters=[params_file, {'use_sim_time': use_sim_time}],
    )

    # 事件：node_b 进程启动 → 打一条日志 → 1 秒后再启动 node_c
    start_c_after_b = RegisterEventHandler(
        OnProcessStart(
            target_action=node_b,
            on_start=[
                LogInfo(msg=f'[{namespace}] node_b_filter 已启动，1s 后启动 node_c_alarm'),
                TimerAction(period=1.0, actions=[node_c]),
            ],
        )
    )
    return [node_a, node_b, start_c_after_b]


def _setup(context):
    namespace = LaunchConfiguration('namespace').perform(context).strip()
    params_file = LaunchConfiguration('params_file').perform(context).strip()
    dual = LaunchConfiguration('dual').perform(context).strip().lower()
    use_sim = LaunchConfiguration('use_sim_time').perform(context).strip().lower()
    use_sim_time = use_sim in ('true', '1', 'yes')

    p1 = _default_params('params_robot1.yaml')
    p2 = _default_params('params_robot2.yaml')

    def fail(msg):
        # 只打印一行可读错误并关闭 launch，绝不抛异常（避免 Python 栈回溯）。
        # Humble 的 launch.actions 里没有 LogError，所以直接写 stderr。
        print(f'[M1-2][ERROR] {msg}', file=sys.stderr, flush=True)
        return [EmitEvent(event=Shutdown(reason=msg))]

    # 1) 用户显式给了 params_file 就校验它
    if params_file and not os.path.isfile(params_file):
        return fail(f'参数文件不存在: {params_file}（请检查 params_file:=... 路径）')

    # 2) 决定启动几组
    if dual == 'false' or (namespace and namespace != 'robot1'):
        groups = [(namespace or 'robot1', params_file or p1)]
    else:
        groups = [('robot1', params_file or p1), ('robot2', params_file or p2)]

    for ns, pf in groups:
        if not os.path.isfile(pf):
            return fail(f'默认参数文件缺失: {pf}（是否忘了 colcon build / source？）')

    actions = [LogInfo(msg=f'[M1-2] 启动 {len(groups)} 组: '
                           + ', '.join(f'/{ns}' for ns, _ in groups))]
    for ns, pf in groups:
        actions.append(LogInfo(msg=f'[M1-2] /{ns} 使用参数文件: {pf}'))
        actions.extend(_make_group(ns, pf, use_sim_time))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace', default_value='robot1',
            description='节点命名空间；给非 robot1 的值则只启动单组'),
        DeclareLaunchArgument(
            'params_file', default_value='',
            description='YAML 参数文件路径；留空则用包内 params_robot{1,2}.yaml'),
        DeclareLaunchArgument(
            'dual', default_value='true',
            description='true=同时起 robot1/robot2 两组；false=只起一组'),
        DeclareLaunchArgument(
            'use_sim_time', default_value='false',
            description='是否使用仿真时间'),
        OpaqueFunction(function=_setup),
    ])
