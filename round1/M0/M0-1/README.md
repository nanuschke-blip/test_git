M0-1 README
# M0-1 从零搭建开发环境

## 一、任务说明

在 VMware 虚拟机上安装 Ubuntu 22.04，并完成 ROS2 Humble、编程环境、Git、SSH 远程登录的配置。

## 二、安装方法与环境

### 1. 操作系统
- 发行版：Ubuntu 22.04 LTS
- 运行形态：VMware 虚拟机
- 内核：6.8.0-138-generic
- 架构：x86_64

### 2. 开发工具
- Shell：bash
- 编译器：gcc / g++ / make / cmake
- Python：3.10.12
- 虚拟环境：uv 0.12.23（`.venv`）
- 编辑器：VS Code 1.146.0（含 Python、C/C++、ROS 插件）
- 版本控制：Git（已配置 user.name / user.email）

### 3. ROS2
- 版本：ROS2 Humble
- 环境变量已写入 `~/.bashrc`

### 4. 远程登录
- SSH 服务已开启（端口 22）
- 已生成 SSH 公钥并添加到 GitHub
- 已从 Windows 宿主机成功远程登录 Ubuntu

## 三、踩坑实录

### 问题 1：Broadcom账号收不到验证码
- **现象**：注册Broadcom 账号时，用 QQ 邮箱收不到验证码。
- **定位过程**：尝试重发验证码、检查垃圾邮件均无效，换 Gmail 后成功收到。
- **原因**：Broadcom 邮件系统对部分国内邮箱有风控拦截。
- **解决**：改用 Gmail 邮箱注册，成功收到验证码。

### 问题 2：找不到“安装 VMware Tools”选项
- **现象**：VMware 菜单栏里没有“安装 VMware Tools”选项，一度以为安装失败。
- **定位过程**：在Ubuntu终端执行sudo apt install open-vm-tools open-vm-tools-desktop -y，系统提示open-vm-tools is already the newest version。
- **原因**：Ubuntu 22.04 安装时已自动预装 `open-vm-tools`。
- **解决**：通过 `apt install open-vm-tools` 确认已安装，重启后全屏、鼠标无缝切换、复制粘贴功能正常。

### 问题 3：curl 访问 GitHub 报错 Connection reset
- **现象**：执行 `curl` 下载 ROS2 密钥时报错 `curl: (35) OpenSSL SSL_connect: Connection reset by peer`。
- **定位过程**：先ping github.com发现不通，再用curl -v看到连接被重置，判断是网络限制
- **原因**：国内网络往往无法直连 GitHub 原始域名。
- **解决**：改用清华镜像源替换密钥地址：
  ```bash
  sudo curl -sSL https://mirrors.tuna.tsinghua.edu.cn/rosdistro/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg。

### 问题 4：ros-humble-desktop 提示找不到包
- **现象**：终端输入`sudo apt install ros-humble-desktop` 提示 `E: Unable to locate package ros-humble-desktop`。
- **定位过程**：检查 /etc/apt/sources.list.d/ros2.list 发现内容为空或不存在，说明上一步 ROS2 软件源未成功添加。
- **原因**：上一步密钥导入失败，导致软件源未成功配置。
- **解决**：用清华源重新添加 ROS2 密钥和软件源，再执行安装。

- 经验1：3、4问题均存在无法正常执行指令的情况，可能是网络限制，改用清华镜像源均可解决问题。

### 问题 5：sudo 输密码时屏幕无显示
- **现象**：执行 `sudo` 命令时，输入密码屏幕没有任何反应。
- **原因**：Linux 安全设计，不显示任何输入字符。
- **解决**：正常输入后按回车即可。

### 问题 6：终端里无法用 Ctrl + V 粘贴
- **现象**：在终端里按 `Ctrl + V` 无法粘贴。
- **原因**：Ubuntu 终端默认快捷键不同。
- **解决**：使用 `Ctrl + Shift + V` 粘贴。

### 问题 7：VS Code 打开 test_git 时找不到文件夹
- **现象**：文件选择器里看不到 `test_git` 文件夹。
- **原因**：文件选择器默认不显示隐藏文件。
- **解决**：按 `Ctrl + L` 显示隐藏文件，或直接输入完整路径/home/car/test_git。

- 经验2：Linux 系统里以 . 开头的文件（比如 .bashrc、.git）默认是隐藏的，VS Code 的文件夹选择器		默认也不显示隐藏文件。

### 问题 8：Fcitx5 配置后无法切换中文
- **现象**：装好 Fcitx5 后，按 `Ctrl + 空格` 无法切换。
- **原因**：系统默认输入法框架仍是 IBus。
- **解决**：在“语言支持”里把“键盘输入法系统”改成 Fcitx 5，重启生效。

- 经验3：Ctrl+空格可完成拼音和英文的切换。

### 问题 9：VS Code 里始终无法输入中文
- **现象**：在 VS Code 里按 `Ctrl + 空格` 始终无法打出中文。
- **原因**：Electron 框架对 Fcitx5 兼容性问题。
- **解决**：中文可通过在文件编译器里处理完后复制粘贴过来即可。

### 问题 10：挂起后重新打开虚拟机，网络连接断开了
- **现象**：虚拟机挂起后重新恢复，`ping baidu.com` 提示“域名解析出现暂时性错误”。
- **定位过程**：终端报错 Temporary failure in name resolution，判断是网络服务未重连。
- **原因**：挂起恢复后网络服务未自动重连。
- **解决**：执行 `sudo systemctl restart NetworkManager`，网络恢复后即可正常推送。

- 经验4：在退出虚拟机前，可以点开上侧菜单栏里的虚拟机找到快照并点击拍摄快照可保存当前虚拟机的状态。

### 问题 11：激活 SSH 后终端页面卡住
- **现象**：执行 `systemctl status ssh` 后终端页面卡在状态输出里。
- **原因**：`systemctl status` 展示状态后不会自动退出。
- **解决**：手动按 `q` 退出。

- 经验5：确认本地仓库状态：cd ~/test_git
				git status
				git log --oneline -5  
	是检测问题的一个有效手段

### 问题 12：终端输入 git push 后 GitHub 未更新
- **现象**：终端显示推送成功，但 GitHub 页面还是旧的。
- **定位过程**：执行 git status 发现本地有未提交的修改。
- **原因**：修改未提交（git add + git commit）就直接推送。
- **解决**：先 git add .，再 git commit -m "更新说明"，最后 git push。

## 四、参考资料

- Ubuntu 22.04 官方文档：https://help.ubuntu.com
- ROS2 Humble 安装指南：https://docs.ros.org/en/humble/Installation.html
- 清华镜像源：https://mirrors.tuna.tsinghua.edu.cn
- VMware Workstation 官方文档：https://docs.vmware.com
- Git 官方文档：https://git-scm.com/doc
- systemd 使用手册：https://www.freedesktop.org/software/systemd/man/

## 五、完成判断

- Ubuntu 22.04 已安装，ROS2 Humble 已安装并验证 talker/listener 正常收发。
- Python 虚拟环境 `.venv` 已创建，`uv` 已安装。
- VS Code 已安装并配好 Python、C/C++、ROS 插件。
- Git 已配置 `user.name` / `user.email`。
- `check_env.sh` 跑通，输出 `FAIL=0`。
- 已从 Windows 宿主机成功 SSH 远程登录 Ubuntu（'ssh car@192.168.98.128`）。

### check_env.sh 运行结果
- e1205e2 (HEAD -> main, origin/main) docs: 完善 M0-1 踩坑实录，补充定位过程与参考资料
  8aca6c8 docs: M0-4 完成异常处理与 README，report.json 已生成
  8f60332 feat: M0-4 阶段5 实现彩色输出与 report.json 生成
  1c2f334 feat: M0-4 阶段4 实现全局超时控制
  607cbf3 feat: M0-4 阶段3 实现任务执行、失败重试与下游跳过
  65f8b8e feat: M0-4 阶段1 完成配置加载与命令行参数解析
  6ffd0e0 docs: 补充 M0-3 问题报告，完善脚本
  e1fe910 feat: 添加 M0-3 清洗后数据 cleaned_data.csv
  7e18b85 docs: 按官方要求补全 M0-1 README，整理踩坑实录与环境说明
  5e86a17 test: M0-1 环境验收脚本跑通，FAIL=0
  
## 环境选型说明

选择 VMware 虚拟机而非 WSL2，原因：
- M2 视觉开发需要图形界面和相机直通，虚拟机支持更完整。
- WSL2 对 USB 设备支持较弱，不利于后续视觉任务。

代价：
- 虚拟机占用更多内存和磁盘。
- 性能略低于物理机。




## 六、如何复现

- ```bash
  cd round1/M0/M0-1
  bash check_env.sh

	
