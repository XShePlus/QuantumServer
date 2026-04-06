try:
    import audioop
except ImportError:
    import audioop_lts as audioop  # type: ignore
    import sys
    sys.modules['audioop'] = audioop

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import threading, os, time, json, shutil, sys, shlex, re, random, queue, hashlib, secrets
from Tools import Tools
from apscheduler.schedulers.background import BackgroundScheduler
from threading import Lock

room_template = {
    "status": True,
    "message_list": [],
    "present_number": 0,
    "max_number": 0,
    "cancel_time": 0,
    "current_music": "",
    "is_music_pause": True,
    "current_music_time": 0,
    "password": {"hash": "", "salt": "", "algorithm": "none"},  # 默认无密码哈希
    "users_list": [],
    "is_playing_example": False,
    "last_update_time": 0,
    "last_operator": ""
}

# 安全验证函数
def validate_path_component(component: str) -> bool:
    """验证路径组件是否安全，防止路径遍历攻击"""
    if not component or not isinstance(component, str):
        return False
    # 禁止路径遍历字符
    if '..' in component or '/' in component or '\\' in component:
        return False
    # 仅允许字母、数字、中文、下划线、连字符、点号（用于文件扩展名）
    # Unicode范围：\u4e00-\u9fff 是基本中文汉字
    # 使用正确的正则表达式：\w 包含字母、数字、下划线
    # 添加中文范围，连字符放在字符类末尾避免转义问题
    return bool(re.match(r'^[\w.\- \u4e00-\u9fff]+$', component))

def validate_room_name(name: str) -> bool:
    """验证房间名格式"""
    if not name or not isinstance(name, str):
        return False
    if not 1 <= len(name) <= 32:
        return False
    # 房间名允许中文、英文、数字、下划线、连字符
    return bool(re.match(r'^[\w\-\u4e00-\u9fff]+$', name))

def validate_user_name(name: str) -> bool:
    """验证用户名格式"""
    if not name or not isinstance(name, str):
        return False
    if not 1 <= len(name) <= 20:
        return False
    # 用户名允许中文、英文、数字、下划线、连字符
    return bool(re.match(r'^[\w\-\u4e00-\u9fff]+$', name))

def sanitize_filename(filename: str) -> str:
    """净化文件名，移除危险字符"""
    if not filename or not isinstance(filename, str):
        return "unnamed"
    # 移除路径分隔符
    filename = filename.replace('/', '').replace('\\', '').replace('..', '')
    # 限制长度
    if len(filename) > 255:
        filename = filename[:255]
    return filename

# 密码安全函数
def hash_password(password: str, salt: str = None) -> dict:
    """
    使用PBKDF2算法对密码进行哈希加盐存储

    参数:
        password: 明文密码
        salt: 盐值（如果为None则生成随机盐）

    返回:
        包含哈希值、盐值和算法标识的字典
    """
    if not password:
        return {"hash": "", "salt": "", "algorithm": "none"}

    if salt is None:
        salt = secrets.token_hex(16)  # 128位随机盐

    # 使用PBKDF2-HMAC-SHA256，迭代次数100000
    hash_obj = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # 迭代次数，可根据性能调整
    )

    return {
        'hash': hash_obj.hex(),
        'salt': salt,
        'algorithm': 'pbkdf2_sha256'
    }

def verify_password(password: str, stored_password) -> bool:
    """
    验证密码是否匹配存储的密码信息

    参数:
        password: 待验证的密码
        stored_password: 存储的密码信息，可以是：
                       - 字符串（明文密码，向后兼容）
                       - 字典（哈希密码，包含hash、salt、algorithm）

    返回:
        bool: 密码是否匹配
    """
    if not password:
        password = ""

    # 处理None或空值
    if not stored_password:
        # 空密码存储，只有密码为空时才匹配
        return password == ""

    # 如果是字符串，直接比较（明文向后兼容）
    if isinstance(stored_password, str):
        # 明文比较（常量时间）
        return secrets.compare_digest(password, stored_password)

    # 如果是字典，检查哈希密码
    if not isinstance(stored_password, dict):
        return False

    algorithm = stored_password.get('algorithm', '')
    if algorithm == 'none':
        # 无密码存储
        return password == ""

    if algorithm != 'pbkdf2_sha256':
        # 不支持的算法
        return False

    salt = stored_password.get('salt')
    expected_hash = stored_password.get('hash')

    if not salt or not expected_hash:
        return False

    # 计算密码哈希
    hash_obj = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )

    # 常量时间比较，防止时序攻击
    return secrets.compare_digest(hash_obj.hex(), expected_hash)

app = Flask(__name__)
CORS(app, resources=r"/*")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# 环境变量配置
DATA_PATH = os.environ.get('DATA_PATH', './data')
EXAMPLE_MUSICS_PATH = os.environ.get('EXAMPLE_MUSICS_PATH', './example_musics')
TEMP_PATH = os.environ.get('TEMP_PATH', os.path.join(DATA_PATH, 'temp'))

file_lock = Lock()
_rooms_cache: dict | None = None
version_lock = Lock()
tools = Tools()
TEMP_DIR = TEMP_PATH
ROOMS_LIST_PATH = os.path.join(DATA_PATH, "rooms_list.json")
EXAMPLE_MUSICS = EXAMPLE_MUSICS_PATH
VERSION_PATH = os.path.join(DATA_PATH, "version.json")

tools.check_and_create_file(VERSION_PATH)
tools.check_and_create_file(ROOMS_LIST_PATH)

user_activity_map = {}

for path in [TEMP_DIR, EXAMPLE_MUSICS]:
    os.makedirs(path, exist_ok=True)

try:
    with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
        existing_rooms = json.load(f)
        for room_name in existing_rooms.keys():
            os.makedirs(os.path.join(DATA_PATH, "rooms", room_name, "music"), exist_ok=True)
except Exception:
    pass

# ---------------------------------------------------------------------------
# SSE 订阅管理
# ---------------------------------------------------------------------------

# room_name -> list of queue.Queue
# 每个连接的客户端持有一个 Queue，服务端通过 push_to_room 广播事件
_sse_queues: dict[str, list[queue.Queue]] = {}
_sse_lock = Lock()

def _sse_subscribe(room_name: str) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=32)
    with _sse_lock:
        _sse_queues.setdefault(room_name, []).append(q)
    return q

def _sse_unsubscribe(room_name: str, q: queue.Queue):
    with _sse_lock:
        lst = _sse_queues.get(room_name, [])
        if q in lst:
            lst.remove(q)

def push_to_room(room_name: str, event_type: str, data: dict):
    """向房间内所有 SSE 客户端广播一条事件，非阻塞，队列满则丢弃（客户端落后太多时保护服务端）"""
    msg = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with _sse_lock:
        queues = list(_sse_queues.get(room_name, []))
    for q in queues:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass  # 客户端处理太慢，丢弃本次推送

# ---------------------------------------------------------------------------
# 文件 / 版本工具
# ---------------------------------------------------------------------------

def safe_load_version():
    try:
        if not os.path.exists(VERSION_PATH) or os.path.getsize(VERSION_PATH) == 0:
            return {"versionName": "", "versionCode": 0, "updateURL": ""}
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"versionName": "", "versionCode": 0, "updateURL": ""}

def safe_save_version(data):
    try:
        with open(VERSION_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"版本信息写入失败: {e}")


def _load_rooms_unlocked() -> dict:
    try:
        if not os.path.exists(ROOMS_LIST_PATH) or os.path.getsize(ROOMS_LIST_PATH) == 0:
            return {}
        with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"读取异常: {e}")
        return {}

def _save_rooms_unlocked(data: dict):
    try:
        with open(ROOMS_LIST_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入异常: {e}")

def safe_load_rooms() -> dict:
    global _rooms_cache
    with file_lock:
        if _rooms_cache is None:
            _rooms_cache = _load_rooms_unlocked()
        return dict(_rooms_cache)

def safe_save_rooms(data: dict):
    global _rooms_cache
    with file_lock:
        _rooms_cache = dict(data)
        _save_rooms_unlocked(data)

def atomic_update_room(room_name: str, update_fn) -> bool:
    global _rooms_cache
    with file_lock:
        data = _rooms_cache if _rooms_cache is not None else _load_rooms_unlocked()
        if room_name not in data:
            return False
        update_fn(data[room_name])
        _rooms_cache = data
        _save_rooms_unlocked(data)
        return True

def is_valid_room_name(name: str) -> bool:
    return bool(re.match(r'^[\w\-\u4e00-\u9fff]{1,32}$', name))

def update_user_activity(user_name, room_name):
    if user_name and room_name:
        user_activity_map[user_name] = {
            "room": room_name,
            "last_time": int(time.time())
        }

# ---------------------------------------------------------------------------
# 定时清理任务
# ---------------------------------------------------------------------------

def clean_expired_rooms():
    try:
        current_time = int(time.time())
        rooms_data = safe_load_rooms()
        rooms_to_delete = []
        for name, info in rooms_data.items():
            if current_time > info.get('cancel_time', 0):
                rooms_to_delete.append(name)
        if rooms_to_delete:
            for name in rooms_to_delete:
                shutil.rmtree(os.path.join(DATA_PATH, "rooms", name), ignore_errors=True)
                del rooms_data[name]
            safe_save_rooms(rooms_data)
            print(f"已清理到期房间: {rooms_to_delete}")
    except Exception as e:
        print(f"清理房间任务异常: {e}")

def clean_inactive_users():
    global user_activity_map
    current_time = int(time.time())
    timeout = 45
    try:
        rooms_data = safe_load_rooms()
        changed = False
        users_to_remove = []
        for user, info in list(user_activity_map.items()):
            if current_time - info["last_time"] > timeout:
                room_name = info["room"]
                if room_name in rooms_data:
                    if user in rooms_data[room_name]["users_list"]:
                        rooms_data[room_name]["users_list"].remove(user)
                        rooms_data[room_name]["present_number"] = len(rooms_data[room_name]["users_list"])
                        if rooms_data[room_name]["present_number"] < rooms_data[room_name]["max_number"]:
                            rooms_data[room_name]["status"] = True
                        changed = True
                        # 通知房间内其他人成员变化
                        push_to_room(room_name, "room_update", {
                            "present_number": rooms_data[room_name]["present_number"],
                            "users_list": rooms_data[room_name]["users_list"]
                        })
                users_to_remove.append(user)
        for user in users_to_remove:
            del user_activity_map[user]
        if changed:
            safe_save_rooms(rooms_data)
            print(f"自动清理掉线用户: {users_to_remove}")
    except Exception as e:
        print(f"清理用户逻辑异常: {e}")

# ---------------------------------------------------------------------------
# SSE 端点
# ---------------------------------------------------------------------------

@app.route('/api/sse', methods=['GET'])
def sse_endpoint():
    """
    长连接 SSE 端点。客户端连接后：
    1. 立即下发当前音乐状态（对齐本地播放）
    2. 持续阻塞等待服务器推送事件
    3. 每 25 秒发一次 ping 心跳，防止中间代理断开连接
    客户端断开时自动取消订阅。
    """
    room_name = request.args.get("room", "")
    user_name = request.args.get("user", "")

    if not room_name:
        return "Missing room", 400

    # 更新用户活跃时间（SSE 连接本身也算活跃）
    if user_name:
        update_user_activity(user_name, room_name)

    q = _sse_subscribe(room_name)

    def generate():
        try:
            # 连接建立后立即推送一次当前状态，让客户端快速对齐
            rooms = safe_load_rooms()
            if room_name in rooms:
                r = rooms[room_name]
                initial = json.dumps({
                    "current_music": r.get("current_music", ""),
                    "is_music_pause": r.get("is_music_pause", True),
                    "current_music_time": r.get("current_music_time", 0),
                    "is_playing_example": r.get("is_playing_example", False)
                }, ensure_ascii=False)
                yield f"event: music_status\ndata: {initial}\n\n"

            HEARTBEAT_INTERVAL = 25  # 秒
            while True:
                try:
                    msg = q.get(timeout=HEARTBEAT_INTERVAL)
                    yield msg
                except queue.Empty:
                    # 超时没有新事件，发心跳保持连接
                    yield ": ping\n\n"
        except GeneratorExit:
            pass
        finally:
            _sse_unsubscribe(room_name, q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 禁用 Nginx 缓冲
            "Connection": "keep-alive",
        }
    )

# ---------------------------------------------------------------------------
# 原有 API 路由（在修改状态的地方加入 SSE 推送）
# ---------------------------------------------------------------------------

@app.route('/api/connect', methods=['POST'])
def verify_connect():
    j = safe_load_rooms()
    filtered_keys = [k for k in j.keys() if not k.startswith("__")]
    if not filtered_keys:
        return jsonify({"code": 900, "content": "null"})
    return jsonify({
        "room_name_list": filtered_keys,
        "room_status_list": [j[k].get("status", True) for k in filtered_keys]
    })

@app.route('/api/create_room', methods=['POST'])
def create_room():
    request_json = request.get_json()
    room_name = (request_json.get("room_name") or "").strip()
    if not is_valid_room_name(room_name):
        return "非法房间名", 400

    # 验证max_number参数
    max_number = request_json.get("max_number")
    try:
        max_number = int(max_number)
        if max_number < 1 or max_number > 100:  # 合理范围
            return "人数限制必须在1-100之间", 400
    except (ValueError, TypeError):
        return "无效的人数限制", 400

    password = request_json.get("password") or ""

    # 验证cancel_time参数
    cancel_time_minutes = request_json.get("cancel_time")
    try:
        cancel_time_minutes = int(cancel_time_minutes)
        if cancel_time_minutes < 1 or cancel_time_minutes > 1440:  # 1分钟到24小时
            return "房间有效期必须在1-1440分钟之间", 400
    except (ValueError, TypeError):
        return "无效的房间有效期", 400

    cancel_time = cancel_time_minutes * 60 + int(time.time())

    j = safe_load_rooms()

    # 哈希密码
    password_hash = hash_password(password)

    j[room_name] = {
        "status": True,
        "max_number": max_number,
        "present_number": 0,
        "cancel_time": cancel_time,
        "message_list": [],
        "current_music_time": 0,
        "is_music_pause": True,
        "current_music": "",
        "password": password_hash,  # 存储哈希字典而不是明文
        "users_list": [],
        "is_playing_example": False,
        "last_update_time": 0,
        "last_operator": ""
    }
    safe_save_rooms(j)
    os.makedirs(os.path.join(DATA_PATH, "rooms", room_name, "music"), exist_ok=True)
    return "行"


@app.route('/api/get_music_status', methods=['POST'])
def get_music_status():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")

    if user_name and room_name:
        update_user_activity(user_name, room_name)

    j = safe_load_rooms()
    if room_name not in j:
        return "房间不存在", 404

    r = j[room_name]
    return jsonify({
        "current_music": r['current_music'],
        "is_music_pause": r['is_music_pause'],
        "current_music_time": r['current_music_time'],
        "is_playing_example": r.get('is_playing_example', False)
    })

@app.route('/api/update_music_status', methods=['POST'])
def update_music_status():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")
    is_pause = request_data.get("is_music_pause")
    current_time_val = request_data.get("current_music_time")
    current_music = request_data.get("current_music")
    is_example = request_data.get("is_example", False)
    client_update_time = request_data.get("update_time", 0)

    update_user_activity(user_name, room_name)

    updated = {"changed": False}

    def _update(room):
        if client_update_time < room.get("last_update_time", 0):
            return
        room["current_music_time"] = current_time_val
        room["is_music_pause"] = is_pause
        room["current_music"] = current_music
        room["is_playing_example"] = is_example
        room["last_update_time"] = client_update_time
        updated["changed"] = True

    atomic_update_room(room_name, _update)

    # 只有状态真正被写入时才广播，避免被旧时间戳覆盖的请求触发无效推送
    if updated["changed"]:
        push_to_room(room_name, "music_status", {
            "current_music": current_music,
            "is_music_pause": is_pause,
            "current_music_time": current_time_val,
            "is_playing_example": is_example
        })

    return "OK"


@app.route('/api/search_example_songs')
def search_example_songs():
    keyword = request.args.get('q', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    all_songs = [f for f in os.listdir(EXAMPLE_MUSICS) if f.lower().endswith('.mp3')]
    if keyword:
        filtered = [f for f in all_songs if keyword in os.path.splitext(f)[0].lower()]
    else:
        filtered = all_songs
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    songs = [os.path.splitext(f)[0] for f in filtered[start:end]]
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'songs': songs
    })


@app.route('/api/set_example_mode', methods=['POST'])
def set_example_mode():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")
    example_mode = request_data.get("example_mode", False)

    j = safe_load_rooms()
    if room_name not in j:
        return "房间不存在", 404

    j[room_name]['is_playing_example'] = example_mode
    safe_save_rooms(j)
    update_user_activity(user_name, room_name)

    # 广播示例模式切换
    push_to_room(room_name, "music_status", {
        "current_music": j[room_name].get("current_music", ""),
        "is_music_pause": j[room_name].get("is_music_pause", True),
        "current_music_time": j[room_name].get("current_music_time", 0),
        "is_playing_example": example_mode
    })
    return "OK"


@app.route('/api/enter_room', methods=['POST'])
def enter_room():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    password = request_data.get("password") or ""
    user_name = request_data.get("user_name")

    # 验证输入
    if not room_name or not isinstance(room_name, str):
        return "房间名无效", 400

    if not validate_room_name(room_name):
        return "房间名格式不正确", 400

    if not user_name or not isinstance(user_name, str):
        return "用户名无效", 400

    if not validate_user_name(user_name):
        return "用户名格式不正确（1-20字符，允许中文、英文、数字、下划线、连字符）", 400

    j = safe_load_rooms()
    if room_name not in j:
        return "房间不存在", 404

    room_data = j[room_name]

    if user_name in room_data['users_list']:
        return "您已在房间中", 403

    if not room_data['status']:
        return "房间已满", 401

    # 使用verify_password验证密码（支持明文和哈希）
    stored_password = room_data.get('password', "")
    if not verify_password(password, stored_password):
        return "密码错误", 402

    room_data['users_list'].append(user_name)
    room_data['present_number'] = len(room_data['users_list'])
    update_user_activity(user_name, room_name)

    if room_data['present_number'] >= room_data['max_number']:
        room_data['status'] = False

    safe_save_rooms(j)

    # 广播成员变化
    push_to_room(room_name, "room_update", {
        "present_number": room_data["present_number"],
        "users_list": room_data["users_list"]
    })
    return "行"


@app.route('/api/get_message', methods=['POST'])
def get_message():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")
    update_user_activity(user_name, room_name)
    j = safe_load_rooms()
    if room_name in j:
        return jsonify(j[room_name]['message_list'])
    return jsonify([])

@app.route('/api/exit_room', methods=['POST'])
def exit_room():
    request_json = request.get_json()
    room_name = request_json.get("room_name")
    user_name = request_json.get("user_name")

    j = safe_load_rooms()
    if room_name in j and user_name in j[room_name]['users_list']:
        j[room_name]['users_list'].remove(user_name)
        j[room_name]['present_number'] = len(j[room_name]['users_list'])
        if j[room_name]['present_number'] < j[room_name]['max_number']:
            j[room_name]['status'] = True
        if user_name in user_activity_map:
            del user_activity_map[user_name]
        safe_save_rooms(j)

        # 广播成员变化
        push_to_room(room_name, "room_update", {
            "present_number": j[room_name]["present_number"],
            "users_list": j[room_name]["users_list"]
        })
    return "行"


@app.route('/api/append_message', methods=['POST'])
def append_message():
    request_json = request.get_json()
    room_name = request_json.get("room_name")
    # 新格式：{sender, content}；兼容旧格式纯字符串
    sender = request_json.get("sender", "")
    content = request_json.get("content", "") or request_json.get("message", "")

    message_obj = {"sender": sender, "content": content}

    j = safe_load_rooms()
    if room_name in j:
        # 存储统一用对象格式
        j[room_name]['message_list'].append(message_obj)
        safe_save_rooms(j)

        # 实时推送新消息给所有在线成员
        push_to_room(room_name, "chat_message", message_obj)
    return "行"


@app.route('/api/list_songs', methods=['POST'])
def list_songs():
    room_name = request.get_json().get("room_name")
    dir_path = os.path.join(DATA_PATH, "rooms", room_name, "music")
    if not os.path.exists(dir_path):
        return jsonify([])
    songs = [os.path.splitext(f)[0] for f in os.listdir(dir_path) if f.lower().endswith('.mp3')]
    return jsonify(songs)


@app.route('/api/check_is_in', methods=['POST'])
def check_is_in():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    room_name = data.get("room_name")
    user_name = data.get("user_name")
    if not room_name or not user_name:
        return jsonify({"error": "Missing room_name or user_name"}), 400
    try:
        rooms_data = safe_load_rooms()
        if room_name not in rooms_data:
            return jsonify({"status": "need_exit", "message": "Room does not exist"}), 200
        users_in_room = rooms_data[room_name].get("users_list", [])
        if user_name in users_in_room:
            return jsonify({"status": "in_room", "message": "User is still in the room"}), 200
        else:
            return jsonify({"status": "need_exit", "message": "User is not in the room"}), 200
    except Exception as e:
        print(f"Check is in error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/list_example_songs')
def list_example_songs():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    all_songs = [f for f in os.listdir(EXAMPLE_MUSICS) if f.lower().endswith('.mp3')]
    random.shuffle(all_songs)
    total = len(all_songs)
    start = (page - 1) * page_size
    end = start + page_size
    songs = [os.path.splitext(f)[0] for f in all_songs[start:end]]
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'songs': songs
    })

@app.route('/api/cover/<room_name>/<filename>')
def get_cover(room_name, filename):
    # 验证输入参数
    if not validate_path_component(room_name) or not validate_path_component(filename):
        return '', 400

    # 净化文件名
    safe_filename = sanitize_filename(filename)

    if room_name == "example":
        cover_path = os.path.join(EXAMPLE_MUSICS, f"{safe_filename}.jpg")
    else:
        # 额外验证房间名格式
        if not validate_room_name(room_name):
            return '', 400
        cover_path = os.path.join(DATA_PATH, "rooms", room_name, "music", f"{safe_filename}.jpg")

    if not os.path.exists(cover_path):
        cover_path = os.path.join(EXAMPLE_MUSICS, f"{safe_filename}.jpg")

    if os.path.exists(cover_path):
        return send_from_directory(os.path.dirname(cover_path), os.path.basename(cover_path))
    else:
        return '', 404

@app.route('/api/stream/<room_name>/<filename>')
def stream(room_name, filename):
    # 验证输入参数
    if not validate_room_name(room_name) or not validate_path_component(filename):
        return '', 400

    # 净化文件名
    safe_filename = sanitize_filename(filename)
    if not safe_filename.lower().endswith('.mp3'):
        safe_filename = f"{safe_filename}.mp3"

    # 验证最终文件名
    if not validate_path_component(safe_filename):
        return '', 400

    return send_from_directory(os.path.join(DATA_PATH, "rooms", room_name, "music"), safe_filename)

@app.route('/api/stream_example/<filename>')
def stream_example(filename):
    # 验证输入参数
    if not validate_path_component(filename):
        return '', 400

    # 净化文件名
    safe_filename = sanitize_filename(filename)
    if not safe_filename.lower().endswith('.mp3'):
        safe_filename = f"{safe_filename}.mp3"

    # 验证最终文件名
    if not validate_path_component(safe_filename):
        return '', 400

    return send_from_directory(EXAMPLE_MUSICS, safe_filename)

@app.route('/api/version', methods=['GET'])
def get_version():
    v = safe_load_version()
    return jsonify(v)

@app.route('/api/get_numbers', methods=['POST'])
def get_numbers():
    room_name = request.get_json().get("room_name")
    j = safe_load_rooms()
    if room_name not in j:
        return jsonify({"present_number": 0, "max_number": 0}), 200
    return jsonify({
        "present_number": j[room_name]['present_number'],
        "max_number": j[room_name]['max_number']
    })

@app.route('/api/upload', methods=['POST'])
def upload():
    room_name = request.form.get('room_name')
    file = request.files.get('file')
    if not file:
        return "No file", 400
    room_music_dir = os.path.join(DATA_PATH, "rooms", room_name, "music")
    os.makedirs(room_music_dir, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_filename = f"temp_{int(time.time())}_{file.filename}"
    temp_path = os.path.join(TEMP_DIR, temp_filename)
    file.save(temp_path)
    final_title = tools.get_music_title(temp_path, file.filename)
    threading.Thread(
        target=tools.transcode_to_mp3,
        args=(temp_path, room_music_dir, final_title)
    ).start()
    return jsonify({
        "status": "processing",
        "display_name": final_title
    }), 202

# ---------------------------------------------------------------------------
# 调度器 / 控制台
# ---------------------------------------------------------------------------

def init_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(clean_inactive_users, 'interval', seconds=30, id="clean_users_job")
    scheduler.add_job(clean_expired_rooms, 'interval', seconds=420, id="clean_rooms_job")
    scheduler.start()
    print("后台调度任务已启动: 用户活跃监测(30s), 房间有效期检查(420s)")


def console_listener():
    while True:
        try:
            cmd_line = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            print(f"输入读取异常: {e}")
            continue
        if not cmd_line:
            continue
        try:
            parts = shlex.split(cmd_line)
        except Exception as e:
            print(f"命令解析错误: {e}")
            continue
        command = parts[0].lower()
        try:
            if command == "ls":
                rooms_data = safe_load_rooms()
                if not rooms_data:
                    print("当前无房间")
                else:
                    for name, info in rooms_data.items():
                        print(f"房间: {name} | 人数: {info['present_number']} | 状态: {info['status']}")
            elif command == "sse":
                # 查看当前 SSE 连接数
                with _sse_lock:
                    for rn, qs in _sse_queues.items():
                        if qs:
                            print(f"房间: {rn} | SSE连接数: {len(qs)}")
            elif command == "rm":
                if len(parts) < 2:
                    print("用法: rm <房间名>")
                    continue
                room_name = parts[1]
                rooms_data = safe_load_rooms()
                if room_name in rooms_data:
                    shutil.rmtree(os.path.join(DATA_PATH, "rooms", room_name), ignore_errors=True)
                    del rooms_data[room_name]
                    safe_save_rooms(rooms_data)
                    print(f"已强制删除: {room_name}")
                else:
                    print("房间不存在")
            elif command == "set":
                if len(parts) < 3:
                    print("用法: set versionName '名称' | set versionCode '号码' | set updateURL '链接'")
                    continue
                field = parts[1].lower()
                value = ' '.join(parts[2:]).strip().strip("'\"")
                v = safe_load_version()
                if field == "versionname":
                    v["versionName"] = value
                    safe_save_version(v)
                    print(f"已设置 versionName = {value}")
                elif field == "versioncode":
                    try:
                        v["versionCode"] = int(value)
                        safe_save_version(v)
                        print(f"已设置 versionCode = {value}")
                    except ValueError:
                        print("versionCode 必须是整数")
                elif field == "updateurl":
                    v["updateURL"] = value
                    safe_save_version(v)
                    print(f"已设置 updateURL = {value}")
                else:
                    print(f"未知字段: {field}，可选: versionName / versionCode / updateURL")
            else:
                print(f"未知命令: {command}，支持的命令: ls, sse, rm <房间名>, set <字段> <值>")
        except Exception as e:
            print(f"执行命令时出错: {e}")


def initialize_example_musics():
    if not os.path.exists(EXAMPLE_MUSICS):
        os.makedirs(EXAMPLE_MUSICS, exist_ok=True)
        return
    print("正在初始化 example_musics 目录...")
    files = os.listdir(EXAMPLE_MUSICS)
    for filename in files:
        full_path = os.path.join(EXAMPLE_MUSICS, filename)
        if os.path.isdir(full_path):
            continue
        name, ext = os.path.splitext(filename)
        ext = ext.lower()
        if ext == '.mp3':
            continue
        support_exts = ['.wav', '.m4a', '.flac', '.aac', '.ogg', '.mp4', '.mkv']
        if ext in support_exts:
            print(f"发现非标准格式: {filename}，准备转码...")
            try:
                final_title = tools.get_music_title(full_path, filename)
                threading.Thread(
                    target=tools.transcode_to_mp3,
                    args=(full_path, EXAMPLE_MUSICS, final_title)
                ).start()
                print(f"成功标准化: {name}.mp3")
            except Exception as e:
                print(f"标准化文件 {filename} 失败: {e}")
        else:
            if filename != ".gitkeep":
                print(f"跳过未知格式文件: {filename}")


if __name__ == '__main__':
    init_scheduler()
    initialize_example_musics()
    threading.Thread(target=console_listener, daemon=True).start()
    app.run(host='0.0.0.0', port=6132, debug=False, threaded=True)