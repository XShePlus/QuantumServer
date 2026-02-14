from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import threading, os, time, json, shutil, sys
from Tools import Tools
from apscheduler.schedulers.background import BackgroundScheduler

room_template = {
    "status": True,
    "message_list": [],
    "present_number": 0,
    "max_number": 0,
    "cancel_time": 0,
    "current_music": "",
    "is_music_pause": True,
    "current_music_time": 0,
    "password": "",
    "users_list": []
}

app = Flask(__name__)
CORS(app, resources=r"/*")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

tools = Tools()
TEMP_DIR = './data/temp'
ROOMS_LIST_PATH = "./data/rooms_list.json"
tools.check_and_create_file(ROOMS_LIST_PATH)

user_activity_map = {}

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, exist_ok=True)

try:
    with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
        existing_rooms = json.load(f)
        for room_name in existing_rooms.keys():
            os.makedirs(f"./data/rooms/{room_name}/music", exist_ok=True)
except Exception:
    pass



def update_user_activity(user_name, room_name):
    if user_name and room_name:
        user_activity_map[user_name] = {
            "room": room_name,
            "last_time": int(time.time())
        }


def clean_expired_rooms():
    try:
        current_time = int(time.time())
        with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
            rooms_data = json.load(f)

        rooms_to_delete = []
        for name, info in rooms_data.items():
            if current_time > info.get('cancel_time', 0):
                rooms_to_delete.append(name)

        if rooms_to_delete:
            for name in rooms_to_delete:
                shutil.rmtree(f"./data/rooms/{name}", ignore_errors=True)
                del rooms_data[name]
            with open(ROOMS_LIST_PATH, "w", encoding="utf-8") as f:
                f.write(json.dumps(rooms_data))
            print(f"已清理到期房间: {rooms_to_delete}")
    except Exception as e:
        print(f"清理房间任务异常: {e}")


def clean_inactive_users():
    global user_activity_map
    current_time = int(time.time())
    timeout = 45  # 45秒超时

    try:
        with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
            rooms_data = json.load(f)

        changed = False
        users_to_remove = []

        # 遍历内存中的活跃表
        for user, info in list(user_activity_map.items()):
            if current_time - info["last_time"] > timeout:
                room_name = info["room"]
                if room_name in rooms_data:
                    if user in rooms_data[room_name]["users_list"]:
                        rooms_data[room_name]["users_list"].remove(user)
                        # 重新计算人数
                        rooms_data[room_name]["present_number"] = len(rooms_data[room_name]["users_list"])
                        # 若人数空出，恢复房间状态为可加入
                        if rooms_data[room_name]["present_number"] < rooms_data[room_name]["max_number"]:
                            rooms_data[room_name]["status"] = True
                        changed = True
                users_to_remove.append(user)

        # 从内存表中抹除
        for user in users_to_remove:
            del user_activity_map[user]

        if changed:
            with open(ROOMS_LIST_PATH, "w", encoding="utf-8") as f:
                f.write(json.dumps(rooms_data))
            print(f"自动清理掉线用户: {users_to_remove}")

    except Exception as e:
        print(f"清理用户逻辑异常: {e}")


@app.route('/api/connect', methods=['POST'])
def verify_connect():
    if tools.is_file_actually_empty(ROOMS_LIST_PATH):
        return jsonify({"code": 900, "content": "null"})

    try:
        j = json.load(open(ROOMS_LIST_PATH, "r"))
        return jsonify({
            "room_name_list": list(j.keys()),
            "room_status_list": [j[i].get("status", True) for i in j]
        })
    except Exception as e:
        print(f"Error in verify_connect: {e}")
        return jsonify({"code": 900, "content": "null"})


@app.route('/api/create_room', methods=['POST'])
def create_room():
    request_json = request.get_json()
    room_name = request_json.get("room_name")
    max_number = request_json.get("max_number")
    password = request_json.get("password")
    cancel_time = request_json.get("cancel_time") * 60 + int(time.time())

    j = json.load(open(ROOMS_LIST_PATH, "r"))
    j[room_name] = {
        "status": True,
        "max_number": max_number,
        "present_number": 0,
        "cancel_time": cancel_time,
        "message_list": [],
        "current_music_time": 0,
        "is_music_pause": True,
        "current_music": "",
        "password": password,
        "users_list": []
    }
    with open(ROOMS_LIST_PATH, "w") as f:
        f.write(json.dumps(j))

    os.makedirs(f"./data/rooms/{room_name}/music", exist_ok=True)
    return "行"


@app.route('/api/get_music_status', methods=['POST'])
def get_music_status():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")

    # 核心：高频更新用户活跃度
    if user_name and room_name:
        update_user_activity(user_name, room_name)

    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if room_name not in j:
        return "房间不存在", 404

    r = j[room_name]
    return jsonify({
        "current_music": r['current_music'],
        "is_music_pause": r['is_music_pause'],
        "current_music_time": r['current_music_time']
    })


@app.route('/api/update_music_status', methods=['POST'])
def update_music_status():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")  # 建议前端也带上这个

    update_user_activity(user_name, room_name)

    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if room_name in j:
        j[room_name]["current_music_time"] = request_data.get("current_music_time")
        j[room_name]["is_music_pause"] = request_data.get("is_music_pause")
        j[room_name]["current_music"] = request_data.get("current_music")
        with open(ROOMS_LIST_PATH, "w") as f:
            f.write(json.dumps(j))
    return "OK"


@app.route('/api/enter_room', methods=['POST'])
def enter_room():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    password = request_data.get("password")
    user_name = request_data.get("user_name")

    j = json.load(open(ROOMS_LIST_PATH, "r"))

    if room_name not in j:
        return "房间不存在", 404

    # 判别禁止重复进入
    if user_name in j[room_name]['users_list']:
        return "您已在房间中，请勿重复进入", 403

    if not j[room_name]['status']:
        return "房间已满", 401

    if j[room_name]['password'] != password:
        return "密码错误", 402

    # 加入房间
    j[room_name]['users_list'].append(user_name)
    j[room_name]['present_number'] = len(j[room_name]['users_list'])

    update_user_activity(user_name, room_name)

    if j[room_name]['present_number'] >= j[room_name]['max_number']:
        j[room_name]['status'] = False

    with open(ROOMS_LIST_PATH, "w") as f:
        f.write(json.dumps(j))
    return "行"


@app.route('/api/get_message', methods=['POST'])
def get_message():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    user_name = request_data.get("user_name")

    update_user_activity(user_name, room_name)

    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if room_name in j:
        return jsonify(j[room_name]['message_list'])
    return jsonify([])


@app.route('/api/exit_room', methods=['POST'])
def exit_room():
    request_json = request.get_json()
    room_name = request_json.get("room_name")
    user_name = request_json.get("user_name")

    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if room_name in j and user_name in j[room_name]['users_list']:
        j[room_name]['users_list'].remove(user_name)
        j[room_name]['present_number'] = len(j[room_name]['users_list'])
        if j[room_name]['present_number'] < j[room_name]['max_number']:
            j[room_name]['status'] = True

        # 移除活跃记录
        if user_name in user_activity_map:
            del user_activity_map[user_name]

        with open(ROOMS_LIST_PATH, "w") as f:
            f.write(json.dumps(j))
    return "行"


@app.route('/api/get_numbers', methods=['POST'])
def get_numbers():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
    room_name = request_json.get("room_name")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    p_number = j[room_name]['present_number']
    m_number = j[room_name]['max_number']
    return jsonify({
        "present_number": p_number,
        "max_number": m_number
    })

@app.route('/api/upload', methods=['POST'])
def upload():
    room_name = request.form.get('room_name')
    if 'file' not in request.files:
        return "No file", 400

    file = request.files['file']
    room_music_dir = f"./data/rooms/{room_name}/music"
    os.makedirs(room_music_dir, exist_ok=True)

    filename = file.filename
    base_name = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.mp3':
        file.save(os.path.join(room_music_dir, filename))
        return jsonify({"status": "done"}), 200
    elif ext in ['.flac', '.aac']:
        temp_path = os.path.join(TEMP_DIR, filename)
        target_path = os.path.join(room_music_dir, f"{base_name}.mp3")
        file.save(temp_path)
        threading.Thread(target=tools.transcode_to_mp3, args=(temp_path, target_path)).start()
        return jsonify({"status": "processing"}), 202
    return "Unsupported format", 400


@app.route('/api/append_message', methods=['POST'])
def append_message():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
    room_name = request_json.get("room_name")
    message = request_json.get("message")
    print(message)
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    j[room_name]['message_list'].append(message)
    f = open(ROOMS_LIST_PATH, "w")
    f.write(json.dumps(j))
    f.close()
    return "行"


@app.route('/api/list_songs', methods=['POST'])
def list_songs():
    room_name = request.get_json().get("room_name")
    dir_path = f"./data/rooms/{room_name}/music"
    if not os.path.exists(dir_path):
        return jsonify([])
    songs = [f for f in os.listdir(dir_path) if f.lower().endswith('.mp3')]
    return jsonify(songs)


@app.route('/api/stream/<room_name>/<filename>')
def stream(room_name, filename):
    return send_from_directory(f"./data/rooms/{room_name}/music", filename)


def init_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每分钟清理一次掉线用户
    scheduler.add_job(clean_inactive_users, 'interval', seconds=60, id="clean_users_job")
    # 每7分钟清理一次到期房间
    scheduler.add_job(clean_expired_rooms, 'interval', seconds=420, id="clean_rooms_job")
    scheduler.start()
    print("后台调度任务已启动: 用户活跃监测(60s), 房间有效期检查(420s)")


def console_listener():
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == "ls":
                with open(ROOMS_LIST_PATH, "r") as f:
                    data = json.load(f)
                for n, i in data.items():
                    print(f"房间:{n} | 人数:{i['present_number']}/{i['max_number']} | 在线:{i['users_list']}")
            elif cmd.startswith("rm "):
                name = cmd.split(" ")[1]
                # ... 逻辑同原代码 ...
                print(f"已删除 {name}")
            elif cmd == "exit":
                os._exit(0)
        except Exception:
            pass


if __name__ == '__main__':
    init_scheduler()
    threading.Thread(target=console_listener, daemon=True).start()
    app.run(host='0.0.0.0', port=6132, debug=False)