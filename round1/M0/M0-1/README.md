M0-1 排障笔记
一、遇到的问题及对应的解决方法
	1.问题：正常QQ邮箱无法接收broadcom注册发送的验证码
  	解决：换用google帐号或使用tempmail创建临时邮箱即可接收
	2.问题：找不到“安装VMware Tools”菜单项
	分析：Ubuntu22.04已预装open-vm-tools
	解决：用apt install 确认已安装，重启生效
	3.问题：curl访问Github报错Connection reset by peer
	分析：网络限制，无法直连Github原始域名
	解决：改用清华镜像源替换raw.githubusercontent.com
	4.问题：apt install ros-humble-desktop提示E: Unable to locate package
	分析：ROS2 软件源未成功添加（上一步密钥失败导致）
	解决：用清华源重新添加 ROS2 密钥和软件源，再执行安装
	经验一：3、4问题均存在无法正常执行指令的情况，可能是网络限制，改用清华镜像源均可解决问题
	5.问题：sudo 输密码时屏幕无任何显示
	分析：Linux 安全设计，不显示任何输入字符
	解决：正常输入后按回车即可
	6.问题：终端里无法用 Ctrl + V 粘贴
	分析：Ubuntu 终端默认快捷键不同
	解决：使用 Ctrl + Shift + V 粘贴或直接鼠标右键粘贴
	7.问题：VS Code 打开 test_git 时找不到文件夹
	分析：文件选择器默认不显示隐藏文件
	解决：按 Ctrl + L 显示隐藏文件，或直接输入完整路径
	经验2：Linux 系统里以 . 开头的文件（比如 .bashrc、.git）默认是隐藏的，VS Code 的文件夹选择器		默认也不显示隐藏文件
	8.问题：终端里打不出中文
	分析：Linux 终端本身不支持中文输入
	9.问题：Fcitx5 配置后仍无法切换中文
	分析：系统默认输入法框架仍是 IBus
	解决：设置里Region&Language里，键盘输入法系统改成Fcitx5,重启生效
	10.问题：VS Code 里始终无法输入中文
	分析： 对Fcitx5 不兼容
	解决：直接在文本编译器完成中文部分，复制过去即可
	经验3：Ctrl+空格可完成拼音和英文的切换
	11.问题：在挂起后，重新打开虚拟机会出现无法访问github等问题
	分析：网络连接可能断开了，刚恢复时，虚拟机的 DNS 或网络还没重新连上
	解决：终端指令：sudo systemctl restart NetworkManager，重启网络服务
	经验4：在退出虚拟机前，可以点开上侧菜单栏里的虚拟机找到快照并点击拍摄快照可保存当前虚拟机的状态
	12.问题：激活SSH后终端页面会卡在lines1-16/16 （END）
	解决：手动按Q退出
	经验5：确认本地仓库状态：cd ~/test_git
				git status
				git log --oneline -5  是检测问题的一个有效手段
	13.问题：终端输入指令git ～/test_git git push后github未更新
	分析：修改未提交导致的
	解决：加入指令git add . 将修改加入缓存区  git commit -m “更新。。。”进行提交
	
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

### 问题 1：找不到“安装 VMware Tools”选项
- **现象**：VMware 菜单栏里没有“安装 VMware Tools”选项，一度以为安装失败。
- **原因**：Ubuntu 22.04 安装时已自动预装 `open-vm-tools`。
- **解决**：通过 `apt install open-vm-tools` 确认已安装，重启后全屏、鼠标无缝切换、复制粘贴功能正常。

### 问题 2：curl 访问 GitHub 报错 Connection reset
- **现象**：执行 `curl` 下载 ROS2 密钥时报错 `OpenSSL SSL_connect: Connection reset by peer`。
- **原因**：国内网络无法直连 GitHub 原始域名。
- **解决**：改用清华镜像源替换 `raw.githubusercontent.com`。

### 问题 3：ros-humble-desktop 提示找不到包
- **现象**：`sudo apt install ros-humble-desktop` 提示 `E: Unable to locate package`。
- **原因**：上一步 ROS2 软件源未成功添加。
- **解决**：用清华源重新添加 ROS2 密钥和软件源，再执行安装。

### 问题 4：sudo 输密码时屏幕无显示
- **现象**：执行 `sudo` 命令时，输入密码屏幕没有任何反应。
- **原因**：Linux 安全设计，不显示任何输入字符。
- **解决**：正常输入后按回车即可，不要以为键盘坏了。

### 问题 5：终端里无法用 Ctrl + V 粘贴
- **现象**：在终端里按 `Ctrl + V` 无法粘贴。
- **原因**：Ubuntu 终端默认快捷键不同。
- **解决**：使用 `Ctrl + Shift + V` 粘贴。

### 问题 6：VS Code 打开 test_git 时找不到文件夹
- **现象**：文件选择器里看不到 `test_git` 文件夹。
- **原因**：文件选择器默认不显示隐藏文件。
- **解决**：按 `Ctrl + L` 显示隐藏文件，或直接输入完整路径。

### 问题 7：终端里打不出中文
- **现象**：在终端里无法输入中文。
- **原因**：Linux 终端本身不支持中文输入。
- **解决**：这是正常现象，去 VS Code、文本编辑器等图形界面测试。

### 问题 8：Fcitx5 配置后仍无法切换中文
- **现象**：装好 Fcitx5 后，按 `Ctrl + 空格` 无法切换。
- **原因**：系统默认输入法框架仍是 IBus。
- **解决**：在“语言支持”里把“键盘输入法系统”改成 Fcitx 5，重启生效。

### 问题 9：Ctrl + 空格弹出代码补全菜单而非切换输入法
- **现象**：在 VS Code 里按 `Ctrl + 空格` 弹出代码补全菜单。
- **原因**：VS Code 抢占了 `Ctrl + 空格` 快捷键。
- **解决**：用鼠标点右上角键盘图标切换，或修改 Fcitx5 全局快捷键为 `Super + 空格`。

### 问题 10：VS Code 里始终无法输入中文
- **现象**：在 VS Code 里按 `Ctrl + 空格` 始终无法打出中文。
- **原因**：Electron 框架对 Fcitx5 兼容性问题。
- **解决**：用系统自带“文本编辑器”写中文笔记，VS Code 专注写代码。

### 问题 11：挂起后重新打开虚拟机，网络连接断开了
- **现象**：虚拟机挂起后重新恢复，`ping baidu.com` 提示“域名解析出现暂时性错误”。
- **原因**：挂起恢复后网络服务未自动重连。
- **解决**：执行 `sudo systemctl restart NetworkManager`，网络恢复后即可正常推送。

### 问题 12：激活 SSH 后终端页面卡住
- **现象**：执行 `systemctl status ssh` 后终端页面卡在状态输出里。
- **原因**：`systemctl status` 展示状态后不会自动退出。
- **解决**：手动按 `q` 退出。

## 四、参考资料

- Ubuntu 22.04 官方文档：https://help.ubuntu.com
- ROS2 Humble 安装指南：https://docs.ros.org/en/humble/Installation.html
- 清华镜像源：https://mirrors.tuna.tsinghua.edu.cn
- VMware Workstation 官方文档：https://docs.vmware.com

## 五、完成判断

- 在本机环境跑通 `check_env.sh`，输出 `FAIL=0`。
- 已从 Windows 宿主机成功 SSH 远程登录 Ubuntu。
	
