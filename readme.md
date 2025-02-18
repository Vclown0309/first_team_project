# 智能养殖系统(目前为测试版，针对于养殖猪纯视觉识别)
本项目是一个智能养殖系统，通过计算机视觉技术实时监测猪的休息时长，分析猪的健康状态，并提供历史数据查询和异常预警功能。
同时，系统还包含用户管理模块，支持用户注册、登录、修改密码等操作。仅实现了训练视频中猪的识别以及本地的测试运行，未实现猪的行为控制。
### 环境要求
- Python 3.10 （我是3.10）
- MySQL 数据库 （我是5.7.26）

### 安装依赖项
首先，克隆项目仓库或者直接下载zip：
```bash
git clone https://github.com/Vclown0309/first_team_project.git
```
然后，进入项目目录并安装依赖项：
```python
cd first_team_project
cd yolov5-master
# 在下载依赖前，先前往官网安装torch相关依赖，然后再安装yolov5：
# pytorch官网：pytorch.org
'''
进入官网后点击`get started`，
然后找到 `install previous versions of PyTorch`，
然后根据自己的系统以及有无英伟达显卡选择cuda版本和cpu版本
总之选择对应的版本， ->本人是win11，没有英伟达显卡，所以选择cpu版本，效果也不错
pytorch只要没有冲突用最新版选好用cpu还是cuda都可以
然后安装。
通过命令行安装即可
'''
# 对了再提一嘴，最好是在conda环境下安装torch，方便切换python版本
# 还有一件事，如果使用了pip安装库的话，就记得不要用conda install来安装库，会报错，
# 因为pip和conda是两个不同的包管理工具，不要混用。
"""
安装完后，进入yolov5-master目录，
先用vscode打开requirements.txt文件，
然后注释下，含torch的库，
然后用命令行安装：
输入：
pip install -r requirements.txt
下的慢的话建议使用国内镜像源或梯子
"""
r'''
具体镜像源问ai即可,梯子推荐独角兽[官网：https://91unicorn.yeahfast.com/dashboard]，->邀请码：pWxxKbAu
然后视觉识别模型依赖就配置好了
然后就可以运行了
感兴趣的可以去看yolov5的官网下载训练好的模型，
然后替换掉yolov5-master\run\train\weights\best.pt
'''
```
###python文件说明
- `run.py`：程序后端文件，包含了整个系统后端处理的逻辑。 
###一般来说，你需要修改其中的部分代码，主要就是关于数据库连接信息
```Bash
pip install opencv-python # 安装opencv-python库 这个似乎安装torch的时候就自动安装了，但以防万一
pip install flask # 安装flask库
pip install flask-cors # 安装flask-cors库
pip install pymysql # 安装pymysql库
pip install email-validator # 安装email-validator库
pip install pandas # 安装pandas库
```
如果一切顺利，打开数据库，
你就可以运行`run.py`文件了。
然后打开login.html，输入用户名和密码，点击登录即可。
若未注册，可自行注册。
```python
"""
简单说哈关于数据库的配置，
我是用的是pymysql库，版本为5.7.26，
所以你需要在run.py文件中修改数据库连接信息，
比如：
修改前：
# 数据库连接配置
dic = {
    "host": '127.0.0.1',  # 数据库的地址，127.0.0.1 ->主机
    "port": 3306,  # 具体位置3306 ->端口（int） 字符串形式会报错
    "user": 'root',  # 用户
    "password": 'root',  # 密码
    "db": 'test',  # 仓库db（DataBase）
    "charset": 'utf8'  # 编码格式 直接填无需‘-’
}
修改后：
# 数据库连接配置
dic = {
    "host": '127.0.0.1',  # 数据库的地址，127.0.0.1 ->主机
    "port": 3306,  # 具体位置3306 ->默认的端口（int）
    "user": '用户名',  # 用户
    "password": '连接数据库的密码',  # 密码
    "db": '仓库名称',  # 仓库db（DataBase）
    "charset": '填写你选择的数据库编码格式即可'  # 编码格式 直接填无需‘-’
}
"""
```
- `login.html`：前端登录页面。
- `register.html`：前端注册页面。
- `index.html`：前端主页面。
- `all_pigs_history.html`：前端总历史数据页面。
- `pig_history.html`：前端单个猪的历史数据页面。
- `user_info.html`：前端用户信息页面。
- `wangji_mima.html`：前端忘记密码页面。
   - `vue.js`：前端框架。
   - `axios.js`：前端请求库。
   - `chart.umd.js`：前端图表库。
   - `vue router.js`：前端路由库。
***总之，经过以上步骤，你就可以运行这个智能养殖系统了。***


