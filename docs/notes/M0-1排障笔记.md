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
	
