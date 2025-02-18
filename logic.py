import string
import smtplib
import torch
import cv2
import time
from flask import Flask, Response, jsonify, request
import sys
from flask_cors import CORS
import pymysql
# import logging
from datetime import datetime,timedelta
import random
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email_validator import validate_email, EmailNotValidError
logging.basicConfig(level = logging.INFO)
# sort为选择视频还是监控的变量
mp4_demo_list = ["../output.mp4", "../2.mp4"]
sort = mp4_demo_list[1]

# 将克隆的 YOLOv5 仓库路径添加到系统路径中
sys.path.append('../yolov5-master')

#  加载yolov5模型
yolov5_dir = '../yolov5-master'  # YOLOv5 代码所在目录
model_demo_list = ['../yolov5-master/runs/train/exp12/weights/best.pt', '../yolov5-master/runs/train/exp13/weights/best.pt']
model_path = model_demo_list[1]  # 本地模型文件路径
model = torch.hub.load(yolov5_dir, 'custom', path=model_path, source='local')
# 设置置信度阈值为 0.6
model.conf = 0.45
# 设置 IoU 阈值为 0.3
model.iou = 0.3

app = Flask(__name__)
# 允许来自任何源的跨域请求
CORS(app)
# 存储验证码的字典，这里简单使用内存存储，实际项目中可使用 Redis 等
verification_codes = {}
# 数据库连接配置
dic = {
    "host": '127.0.0.1',  # 数据库的地址，127.0.0.1 ->主机
    "port": 3306,  # 具体位置3306 ->端口（int） 字符串形式会报错
    "user": 'root',  # 用户
    "password": 'root',  # 密码
    "db": 'test',  # 仓库db（DataBase）
    "charset": 'utf8'  # 编码格式 直接填无需‘-’
}

# 设定猪的正常休息时长范围（秒）
NORMAL_REST_TIME_MIN = 43200
NORMAL_REST_TIME_MAX = 79200

# 生成一些历史数据用于测试前端展示功能
def insert_default_history():
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        # 假设生成过去 7 天的默认数据
        today = datetime.now().date()
        for i in range(7):
            record_date = today - timedelta(days=i + 1)
            for animal_id in ['pig1', 'pig2', 'pig3']:  # 假设猪的 ID
                rest_duration = random.randint(NORMAL_REST_TIME_MIN, NORMAL_REST_TIME_MAX)
                record_time = datetime.combine(record_date, datetime.min.time())
                sql = "INSERT INTO rest_records (animal_id, rest_duration, record_time) VALUES (%s, %s, %s)"
                cursor.execute(sql, (animal_id, rest_duration, record_time))

        conn.commit()
        logging.info("默认历史数据插入成功")
    except pymysql.Error as e:
        logging.error(f"插入默认历史数据时出错: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def create_table_and_index():
    conn = None
    cursor = None
    try:
        # 建立数据库连接
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        # 检查 rest_records 表是否存在
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME ='rest_records'
        """, (dic['db'],))
        table_exists = cursor.fetchone()

        if not table_exists:
            # 若表不存在，则创建 rest_records 表
            create_table_sql = """
                CREATE TABLE rest_records (
                    record_id INT AUTO_INCREMENT PRIMARY KEY,
                    animal_id VARCHAR(50) NOT NULL,
                    rest_duration FLOAT(10, 2) NOT NULL,
                    record_time DATETIME NOT NULL
                )
            """
            cursor.execute(create_table_sql)
            print("rest_records 表创建成功")
        else:
            print("rest_records 表已存在")

        # 尝试创建联合索引
        try:
            create_index_sql = "CREATE INDEX idx_animal_record_time ON rest_records (animal_id, record_time)"
            cursor.execute(create_index_sql)
            print("idx_animal_record_time 索引创建成功")
        except pymysql.Error as e:
            if e.args[0] == 1061:  # 索引已存在错误码
                print("idx_animal_record_time 索引已存在")
            else:
                logging.error(f"创建索引时出错: {e}")

        # 检查 users 表是否存在
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'
        """, (dic['db'],))
        users_table_exists = cursor.fetchone()

        if not users_table_exists:
            # 若表不存在，则创建 users 表
            create_users_table_sql = """
                CREATE TABLE users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password VARCHAR(120) NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """
            cursor.execute(create_users_table_sql)
            print("users 表创建成功")
        else:
            print("users 表已存在")

        # 提交事务
        conn.commit()
    except pymysql.Error as e:
        print(f"操作数据库时出现错误: {e}")
        # 若出现错误，回滚事务
        if conn:
            conn.rollback()
    finally:
        # 关闭游标和数据库连接
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def format_time(timestamp):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def check_duplicates(pig_ids, start_time, end_time):
    """
    批量检查猪的休息时长数据是否已存在于数据库中
    :param pig_ids: 猪的ID列表
    :param start_time: 时间窗口的开始时间
    :param end_time: 时间窗口的结束时间
    :return: 已存在于数据库中的猪ID集合
    """
    if not pig_ids:
        return set()
    conn = None
    cursor = None
    try:
        # 建立数据库连接
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        placeholders = ', '.join(['%s'] * len(pig_ids))
        check_sql = f"SELECT DISTINCT animal_id FROM rest_records WHERE animal_id IN ({placeholders}) AND record_time BETWEEN %s AND %s"
        values = pig_ids + [format_time(start_time), format_time(end_time)]
        cursor.execute(check_sql, values)
        existing_pig_ids = set([row[0] for row in cursor.fetchall()])
        return existing_pig_ids
    except pymysql.Error as e:
        logging.error(f"检查重复数据时出错: {e}")
        return set()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# 打开视频文件或摄像头
cap = cv2.VideoCapture(sort)
print("视频准备就绪")

# 用于存储每头猪的信息
pig_info = {}
start_time = time.time()
# 获取视频的 FPS
fps = cap.get(cv2.CAP_PROP_FPS)
interval = 1/fps  # 时间间隔，用于计算休息时长
time_window = 60  # 时间窗口，单位：秒
accumulated_rest_times = {}  # 存储每头猪在时间窗口内累加的休息时长
print("全局变量初始化完成")

def generate_frames():
    global pig_info, start_time, accumulated_rest_times
    while True:
        ret, frame = cap.read()
        if not ret:
            # 视频播放完毕，重置cap重新开始读取视频
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                # 若再次读取失败，可能是严重错误，这里可以适当处理，例如记录日志
                break
        else:
            # 进行目标检测
            results = model(frame)
            # 获取检测结果
            detections = results.pandas().xyxy[0]
            current_time = time.time()
            for _, detection in detections.iterrows():
                x1, y1, x2, y2 = int(detection['xmin']), int(detection['ymin']), int(detection['xmax']), int(
                    detection['ymax'])
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                pig_id = detection['name'] + str(int(detection['class']))  # 为每头猪分配一个唯一的 ID
                if pig_id not in pig_info:
                    pig_info[pig_id] = {
                        'last_center': (center_x, center_y),
                       'rest_time': 0,
                        'is_resting': True
                    }
                    accumulated_rest_times[pig_id] = 0
                else:
                    last_center = pig_info[pig_id]['last_center']
                    distance = ((center_x - last_center[0]) ** 2 + (center_y - last_center[1]) ** 2) ** 0.5
                    if distance <= 5:  # 判断是否移动距离小于阈值
                        if pig_info[pig_id]['is_resting']:
                            pig_info[pig_id]['rest_time'] += interval
                            accumulated_rest_times[pig_id] += interval
                    else:
                        pig_info[pig_id]['is_resting'] = False
                    pig_info[pig_id]['last_center'] = (center_x, center_y)
                # 在图像上绘制检测框和休息时长信息
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{pig_id}: {pig_info[pig_id]['rest_time']:.2f}s", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            # 检查时间窗口是否结束
            if current_time - start_time >= time_window:
                valid_data = []
                pig_ids = list(accumulated_rest_times.keys())
                existing_pig_ids = check_duplicates(pig_ids, start_time, current_time)
                for pig_id, rest_time in accumulated_rest_times.items():
                    # 异常值检测
                    if 0 < rest_time <= time_window:
                        if pig_id not in existing_pig_ids:
                            valid_data.append((pig_id, rest_time, current_time))
                # 批量插入有效数据
                if valid_data:
                    conn = None
                    cursor = None
                    try:
                        # 建立数据库连接
                        conn = pymysql.connect(**dic)
                        cursor = conn.cursor()
                        sql = "INSERT INTO rest_records (animal_id, rest_duration, record_time) VALUES (%s, %s, FROM_UNIXTIME(%s))"
                        cursor.executemany(sql, valid_data)
                        conn.commit()
                        print("数据插入成功")
                    except pymysql.Error as e:
                        logging.error(f"插入数据时出错: {e}")
                        if conn:
                            conn.rollback()
                    finally:
                        if cursor:
                            cursor.close()
                        if conn:
                            conn.close()
                # 重置累加数据和开始时间
                accumulated_rest_times = {}
                start_time = current_time
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(interval)
def is_valid_email(email):
    try:
        valid = validate_email(email)
        normalized_email = valid.email
        # 这里可以对规范化后的邮箱地址进行其他操作，比如记录到日志中
        print(f"规范化后的邮箱地址: {normalized_email}")
        return True
    except EmailNotValidError:
        return False
# 生成一个6位的随机验证码
def generate_verification_code(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))
# 获取当前用户信息
@app.route('/uinfo', methods=['GET'])
def get_user_info():
    # 前端会在参数中携带用户名
    username = request.args.get('username')
    if not username:
        return jsonify({'message': '请提供用户名'}), 400
    conn = pymysql.connect(**dic)
    cursor = conn.cursor()
    sql = "SELECT id, username, email, create_time FROM users WHERE username = %s"
    cursor.execute(sql, (username,))
    try:
        user = cursor.fetchone()
        if user:
            user_data = {
                'id': user[0],
                'username': user[1],
                'email': user[2],
                'create_time': str(user[3])
            }
            return jsonify(user_data), 200
        else:
            return jsonify({'message': '未找到该用户'}), 404
    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        return jsonify({'message': '查询用户信息失败，请稍后重试'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# 修改用户密码
@app.route('/change_password', methods=['POST'])
def change_password():
    data = request.get_json()
    username = data.get('username')
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    if not all([username, old_password, new_password]):
        return jsonify({'message': '请提供用户名、旧密码和新密码'}), 400
    conn = pymysql.connect(**dic)
    cursor = conn.cursor()
    # 验证旧密码是否正确
    sql = "SELECT * FROM users WHERE username = %s AND password = %s"
    cursor.execute(sql, (username, old_password))
    user = cursor.fetchone()
    if not user:
        return jsonify({'message': '旧密码不正确'}), 401
    try:
        # 更新密码
        sql = "UPDATE users SET password = %s WHERE username = %s"
        cursor.execute(sql, (new_password, username))
        conn.commit()
        return jsonify({'message': '密码修改成功'}), 200
    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        conn.rollback()
        return jsonify({'message': '密码修改失败，请稍后重试'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# 用户登录路由
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    # 验证输入是否为空
    if not username or not password:
        return jsonify({'message': '用户名和密码不能为空'}), 400
    # 连接数据库
    conn = pymysql.connect(**dic)
    cursor = conn.cursor()
    if is_valid_email(username):
        # 查询用户记录
        sql = "SELECT * FROM users WHERE email = %s AND password = %s"
        cursor.execute(sql, (username, password))
    else:
        # 查询用户记录
        sql = "SELECT * FROM users WHERE username = %s AND password = %s"
        cursor.execute(sql, (username, password))
    try:
        user = cursor.fetchone()
        if user:
            return jsonify({'message': '登录成功','username': user[1]}), 200
        else:
            return jsonify({'message': '用户名或密码错误'}), 401

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        return jsonify({'message': '登录失败，请稍后重试'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@app.route('/send_verification_code', methods=['POST'])
# 发送邮件
def send_verification_code():
    data = request.get_json()
    to_email = data.get('email')
    code = generate_verification_code()
    if not to_email:
        return jsonify({'message': '请提供邮箱地址'}), 400
    from_email = '3011588309@qq.com'
    from_password = 'xfiabxnguyzydedj'
    server = None
    if not is_valid_email(to_email):
        return jsonify({'message': '无效的邮箱地址'}), 400
    # 创建邮件内容
    subject = '智能养殖验证码'
    body = f'您的验证码是：{code}'
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        # 设置邮件服务器
        server = smtplib.SMTP('smtp.qq.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        # 发送邮件
        server.sendmail(from_email, to_email, msg.as_string())
        print("验证码已发送")
        verification_codes[to_email] = code  # 存储验证码，后续注册时验证
        return jsonify({'message': '验证码已发送，请查收'}), 200
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return jsonify({'message': '请检查邮箱地址'}), 400
    finally:
        if server:
            server.quit()
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    confirm_password = data.get('confirm_password')
    email = data.get('email')
    code = data.get('code')

    # 检查是否所有必填字段都已填写
    if not all([username, password, confirm_password, email, code]):
        return jsonify({'message': '请填写所有必填字段'}), 400

    # 检查两次输入的密码是否一致
    if password != confirm_password:
        return jsonify({'message': '两次输入的密码不一致'}), 400

    # 检查验证码是否有效
    stored_code = verification_codes.get(email)
    if not stored_code or stored_code != code:
        return jsonify({'message': '验证码无效'}), 400
        # 连接数据库
    connection = pymysql.connect(**dic)
    try:
        with connection.cursor() as cursor:
            # 检查用户名是否已存在
            sql = "SELECT * FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            if cursor.fetchone():
                return jsonify({'message': '用户名已存在'}), 400

            # 检查邮箱是否已被注册
            sql = "SELECT * FROM users WHERE email = %s"
            cursor.execute(sql, (email,))
            if cursor.fetchone():
                return jsonify({'message': '邮箱已被注册'}), 400

            # 插入新用户数据，同时自动记录创建时间（利用数据库默认值）
            sql = "INSERT INTO users (username, password, email) VALUES (%s, %s, %s)"
            cursor.execute(sql, (username, password, email))

        # 提交数据库事务
        connection.commit()
        # 注册成功后删除验证码
        del verification_codes[email]
        return jsonify({'message': '注册成功'}), 201
    except pymysql.Error as e:
        # 打印数据库错误信息
        print(f"数据库错误: {e}")
        # 回滚数据库事务
        if connection:
            connection.rollback()
        return jsonify({'message': '注册失败，请稍后重试'}), 500
    finally:
        # 关闭数据库连接
        if connection:
            connection.close()
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/rest_data')
def rest_data():
    # 从 pig_info 中获取当前检测到的猪 ID
    pig_ids = list(pig_info.keys())
    if not pig_ids:
        return jsonify({'data': {}, 'health_status': {}, 'last_updated': int(time.time())})

    conn = None
    cursor = None
    try:
        # 连接数据库
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        # 生成占位符
        placeholders = ', '.join(['%s'] * len(pig_ids))

        # 查询每头猪的最新休息时长和健康状态
        sql = f"""
            SELECT 
                r.animal_id, 
                r.rest_duration,
                CASE 
                    WHEN r.rest_duration BETWEEN %s AND %s THEN '正常'
                    ELSE '异常'
                END AS health_status
            FROM 
                rest_records r
            JOIN (
                SELECT 
                    animal_id, 
                    MAX(record_time) AS max_record_time
                FROM 
                    rest_records
                WHERE 
                    animal_id IN ({placeholders})
                GROUP BY 
                    animal_id
            ) sub ON r.animal_id = sub.animal_id AND r.record_time = sub.max_record_time
        """
        values = [NORMAL_REST_TIME_MIN, NORMAL_REST_TIME_MAX] + pig_ids
        cursor.execute(sql, values)
        results = cursor.fetchall()

        rest_data_dict = {row[0]: row[1] for row in results}
        health_status_dict = {row[0]: row[2] for row in results}

        last_updated = int(time.time())

        return jsonify({
            'data': rest_data_dict,
            'health_status': health_status_dict,
            'last_updated': last_updated
        })
    except pymysql.Error as e:
        error_info = {
            'error': 'DatabaseError',
          'message': str(e)
        }
        return jsonify(error_info), 500
    except Exception as e:
        error_info = {
            'error': 'InternalServerError',
          'message': str(e)
        }
        return jsonify(error_info), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/daily_health_status', methods=['GET'])
def daily_health_status():
    conn = None
    cursor = None
    try:
        # 连接数据库
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        # 按天统计休息时长并判断健康状态
        sql = """
            SELECT 
                DATE(record_time) AS record_date,
                SUM(rest_duration) AS total_rest_duration,
                CASE 
                    WHEN SUM(rest_duration) BETWEEN %s AND %s THEN '正常'
                    ELSE '异常'
                END AS health_status
            FROM 
                rest_records
            GROUP BY 
                DATE(record_time)
        """
        values = (NORMAL_REST_TIME_MIN, NORMAL_REST_TIME_MAX)
        cursor.execute(sql, values)
        results = cursor.fetchall()

        daily_status = []
        for row in results:
            record_date = row[0].strftime('%Y-%m-%d')
            total_rest_duration = row[1]
            health_status = row[2]
            daily_status.append({
                'record_date': record_date,
                'total_rest_duration': total_rest_duration,
                'health_status': health_status
            })

        return jsonify({
            'daily_status': daily_status
        })
    except pymysql.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@app.route('/abnormal_days', methods=['GET'])
def abnormal_days():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    conn = None
    cursor = None
    try:
        # 连接数据库
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        # 查询指定日期范围内有异常的日期
        base_sql = """
            SELECT 
                DATE(record_time) AS record_date
            FROM 
                rest_records
            GROUP BY 
                DATE(record_time)
            HAVING 
                SUM(rest_duration) NOT BETWEEN %s AND %s
        """
        values = [NORMAL_REST_TIME_MIN, NORMAL_REST_TIME_MAX]
        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days = 1) - timedelta(microseconds = 1)
            base_sql += ' AND record_time BETWEEN %s AND %s'
            values.extend([start_date, end_date])

        cursor.execute(base_sql, values)
        results = cursor.fetchall()

        abnormal_dates = [row[0].strftime('%Y-%m-%d') for row in results]
        return jsonify({
            'abnormal_dates': abnormal_dates
        })
    except pymysql.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/history/<animal_id>', methods=['GET'])
def get_animal_history(animal_id):
    # 获取分页参数，默认 page 为 1，perPage 为 10
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('perPage', 10))
    offset = (page - 1) * per_page

    conn = None
    try:
        # 连接数据库
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        # 查询该动物的历史记录（除了今天），并进行分页
        now = datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        sql = """
            SELECT record_time, rest_duration 
            FROM rest_records 
            WHERE animal_id = %s AND record_time < %s
            ORDER BY record_time DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(sql, (animal_id, start_of_day, per_page, offset))
        results = cursor.fetchall()

        history = []
        for row in results:
            record_time = row[0]
            rest_duration = row[1]
            health_status = '正常' if NORMAL_REST_TIME_MIN <= rest_duration <= NORMAL_REST_TIME_MAX else '异常'
            history.append({
                'record_time': record_time.strftime('%Y-%m-%d %H:%M:%S'),
                'rest_duration': rest_duration,
                'health_status': health_status
            })

        return jsonify({
            'history': history
        })
    except pymysql.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/all_history_data')
def all_history_data():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    abnormal = request.args.get('abnormal')
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = max(1, int(request.args.get('per_page', 10)))
    except ValueError:
        page = 1
        per_page = 10

    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        base_sql = """
            SELECT 
                record_id,
                animal_id, 
                rest_duration, 
                record_time,
                CASE 
                    WHEN rest_duration BETWEEN %s AND %s THEN '正常'
                    ELSE '异常'
                END AS health_status
            FROM 
                rest_records
        """
        values = [NORMAL_REST_TIME_MIN, NORMAL_REST_TIME_MAX]
        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)
            base_sql += ' WHERE record_time BETWEEN %s AND %s'
            values.extend([start_date, end_date])
        elif start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            base_sql += ' WHERE record_time >= %s'
            values.append(start_date)
        elif end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)
            base_sql += ' WHERE record_time <= %s'
            values.append(end_date)
        elif abnormal:
            base_sql += ' WHERE rest_duration NOT BETWEEN %s AND %s'
            values.extend([NORMAL_REST_TIME_MIN, NORMAL_REST_TIME_MAX])

        base_sql += ' ORDER BY animal_id, record_time LIMIT %s OFFSET %s'
        offset = (page - 1) * per_page
        values.extend([per_page, offset])

        cursor.execute(base_sql, values)
        results = cursor.fetchall()

        history_data = []

        history_data = {}
        for row in results:
            record_id = row[0]
            animal_id = row[1]
            rest_duration = row[2]
            record_time = row[3].strftime('%Y-%m-%d %H:%M:%S')
            health_status = row[4]

            if animal_id not in history_data:
                history_data[animal_id] = []

            history_data[animal_id].append({
                'record_id': record_id,
                'rest_duration': rest_duration,
                'record_time': record_time,
                'health_status': health_status,
            })

        return jsonify({
            'history_data': history_data
        })
    except pymysql.Error as e:
        error_info = {
            'error': 'DatabaseError',
           'message': str(e)
        }
        return jsonify(error_info), 500
    except Exception as e:
        error_info = {
            'error': 'InternalServerError',
           'message': str(e)
        }
        return jsonify(error_info), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@app.route('/daily_rest_data_by_animal', methods=['GET'])
def daily_rest_data_by_animal():
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()
        sql = """
            SELECT 
                animal_id, 
                DATE(record_time) AS record_date, 
                SUM(rest_duration) AS total_rest_duration
            FROM 
                rest_records
            GROUP BY 
                animal_id, DATE(record_time)
            ORDER BY 
                animal_id, record_date
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        data = {}
        for row in results:
            animal_id = row[0]
            record_date = row[1].strftime('%Y-%m-%d')
            total_rest_duration = row[2]
            if animal_id not in data:
                data[animal_id] = []
            data[animal_id].append({
               'record_date': record_date,
                'total_rest_duration': total_rest_duration
            })
        return jsonify({
            'daily_rest_data': data
        })
    except pymysql.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@app.route('/all_pig_ids')
def all_pig_ids():
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**dic)
        cursor = conn.cursor()

        sql = "SELECT DISTINCT animal_id FROM rest_records"
        cursor.execute(sql)
        results = cursor.fetchall()

        pig_ids = [row[0] for row in results]

        return jsonify({'pig_ids': pig_ids})
    except pymysql.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
if __name__ == '__main__':
    insert_default_history()
    create_table_and_index()
    app.run(debug=False)