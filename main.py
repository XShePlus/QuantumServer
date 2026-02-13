from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import threading, os, time, json, shutil, sys
from Tools import Tools
from apscheduler.schedulers.background import BackgroundScheduler

# 模板room
room = {
    "status": bool,  # 可否加入
    "message_list": list,  # 消息列表eg: ["a:hhh","b:hhh"]
    "present_number": int,  # 当前人数
    "max_number": int,  # 最大人数
    "cancel_time": int,  # 使用时间戳
    "current_music": int,  # 当前播放的音乐
    "is_music_pause": bool,  # 音乐是否暂停
    "current_music_time": int,  # 当前音乐播放进度
    "password": str  # 房间密码
}

app = Flask(__name__)
CORS(app, resources=r"/*")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

tools = Tools()
TEMP_DIR = './data/temp'
ROOMS_LIST_PATH = "./data/rooms_list.json"
tools.check_and_create_file(ROOMS_LIST_PATH)
low_occupancy_rooms = {}

if json.load(open(ROOMS_LIST_PATH, "r")) != {}:
    for i in json.load(open(ROOMS_LIST_PATH, "r")).keys():
        os.makedirs(f"./data/rooms/{i}/music", exist_ok=True)

os.makedirs(TEMP_DIR, exist_ok=True)


@app.route('/api/connect', methods=['POST'])
def verify_connect():
    request_data = request.get_data()

    print(f"收到{request_data}")

    if tools.is_file_actually_empty(ROOMS_LIST_PATH):
        return jsonify({
            "code": 900,
            "content": "null"
        })
    else:
        j = json.load(open(ROOMS_LIST_PATH, "r"))
        s = []
        for i in list(j):
            s.append(j[i]["status"])
        print(list(j) + list(s))
        return jsonify({
            "room_name_list": list(j),
            "room_status_list": list(s)
        })


@app.route('/api/create_room', methods=['POST'])
def create_room():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
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
        "password": password
    }
    f = open(ROOMS_LIST_PATH, "w")
    f.write(json.dumps(j))
    f.close()
    return "行"


@app.route('/api/get_music_status', methods=['POST'])
def get_music_status():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    r = j.get(room_name, {})
    return jsonify({
        "current_music_time": r.get("current_music_time", 0),
        "is_music_pause": r.get("is_music_pause", True),
        "current_music": r.get("current_music", "")
    })


@app.route('/api/update_music_status', methods=['POST'])
def update_music_status():
    request_data = request.get_json()
    room_name = request_data.get("room_name")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if room_name in j:
        # 更新服务端数据
        j[room_name]["current_music_time"] = request_data.get("current_music_time")
        j[room_name]["is_music_pause"] = request_data.get("is_music_pause")
        j[room_name]["current_music"] = request_data.get("current_music")
        with open(ROOMS_LIST_PATH, "w") as f:
            f.write(json.dumps(j))
    return "OK"


@app.route('/api/enter_room', methods=['POST'])
def enter_room():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
    room_name = request_json.get("room_name")
    password = request_json.get("password")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if not j[room_name]['status']:
        return "不行", 401
    if not j[room_name]['password'] == password:
        return "不行", 402
    j[room_name]['present_number'] += 1
    if j[room_name]['present_number'] >= j[room_name]['max_number']:
        j[room_name]['status'] = False
    f = open(ROOMS_LIST_PATH, "w")
    f.write(json.dumps(j))
    f.close()
    return "行"


@app.route('/api/get_message', methods=['POST'])
def get_message():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
    room_name = request_json.get("room_name")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    return j[room_name]['message_list']


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


@app.route('/api/exit_room', methods=['POST'])
def exit_room():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
    room_name = request_json.get("room_name")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if j[room_name]['present_number'] < j[room_name]['max_number']:
        j[room_name]['status'] = True
    j[room_name]['present_number'] -= 1
    f = open(ROOMS_LIST_PATH, "w")
    f.write(json.dumps(j))
    f.close()
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
    if not room_name:
        return "Missing room_name", 400

    room_music_dir = f"./data/rooms/{room_name}/music"
    os.makedirs(room_music_dir, exist_ok=True)

    if 'file' not in request.files:
        return "No file", 400

    file = request.files['file']
    filename = file.filename
    if not filename:
        return "Empty filename", 400

    base_name = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.mp3':
        save_path = os.path.join(room_music_dir, filename)
        file.save(save_path)
        return jsonify({"msg": f"房间 {room_name} MP3 上传成功", "status": "done"}), 200

    elif ext in ['.flac', '.aac']:
        temp_path = os.path.join(TEMP_DIR, filename)
        # 目标统一转码为 mp3 存入房间目录
        target_path = os.path.join(room_music_dir, f"{base_name}.mp3")
        file.save(temp_path)

        # 启动转码线程
        thread = threading.Thread(target=tools.transcode_to_mp3, args=(temp_path, target_path))
        thread.start()

        format_name = "FLAC" if ext == '.flac' else "AAC"
        return jsonify({
            "msg": f"{format_name} 上传成功，后台转码中...",
            "status": "processing"
        }), 202

    else:
        return "不支持的格式", 400


@app.route('/api/list_songs', methods=['POST'])
def list_songs():
    request_data = request.get_json()
    room_name = request_data.get("room_name")

    room_music_dir = f"./data/rooms/{room_name}/music"

    if not os.path.exists(room_music_dir):
        return jsonify([])

    songs = [f for f in os.listdir(room_music_dir) if f.lower().endswith('.mp3')]
    return jsonify(songs)


@app.route('/api/stream/<room_name>/<filename>')
def stream(room_name, filename):
    room_music_dir = f"./data/rooms/{room_name}/music"
    return send_from_directory(room_music_dir, filename)


def clean_expired_rooms():
    global low_occupancy_rooms
    try:
        if tools.is_file_actually_empty(ROOMS_LIST_PATH):
            return

        with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
            rooms_data = json.load(f)

        current_timestamp = int(time.time())
        rooms_to_delete = []

        for room_name, room_info in rooms_data.items():
            is_expired = "cancel_time" in room_info and room_info["cancel_time"] <= current_timestamp
            current_people = room_info.get("present_number", 0)
            is_low_occupancy = False

            if current_people <= 1:
                count = low_occupancy_rooms.get(room_name, 0) + 1
                low_occupancy_rooms[room_name] = count
                if count >= 2:
                    is_low_occupancy = True
            else:
                if room_name in low_occupancy_rooms:
                    del low_occupancy_rooms[room_name]

            if is_expired or is_low_occupancy:
                rooms_to_delete.append(room_name)

        if rooms_to_delete:
            for room_name in rooms_to_delete:
                room_dir = f"./data/rooms/{room_name}"
                if os.path.exists(room_dir):
                    shutil.rmtree(room_dir)

                rooms_data.pop(room_name, None)
                low_occupancy_rooms.pop(room_name, None)

            with open(ROOMS_LIST_PATH, "w", encoding="utf-8") as f:
                f.write(json.dumps(rooms_data))

            print(f"清理完成。删除房间: {rooms_to_delete}，剩余有效房间：{list(rooms_data.keys())}")

    except Exception as e:
        print(f"定时清理过期房间时出现异常：{str(e)}")


def init_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(clean_expired_rooms, 'interval', seconds=300, id="clean_expired_rooms_job")
    scheduler.start()
    print("定时任务调度器已启动")


def console_listener():
    while True:
        cmd = input().strip().lower()

        if cmd == "ls":
            with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
                rooms_data = json.load(f)
            if not rooms_data:
                print("当前无房间")
            else:
                for name, info in rooms_data.items():
                    print(f"房间: {name} | 人数: {info['present_number']} | 状态: {info['status']}")

        elif cmd.startswith("rm "):
            room_name = cmd.split(" ", 1)[1]
            with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
                rooms_data = json.load(f)
            if room_name in rooms_data:
                shutil.rmtree(f"./data/rooms/{room_name}", ignore_errors=True)
                del rooms_data[room_name]
                with open(ROOMS_LIST_PATH, "w", encoding="utf-8") as f:
                    f.write(json.dumps(rooms_data))
                print(f"已强制删除: {room_name}")
            else:
                print("房间不存在")

        elif cmd == "exit":
            print("正在关闭服务器...")
            os._exit(0)


init_scheduler()
threading.Thread(target=console_listener, daemon=True).start()
app.run(host='0.0.0.0', port=6132, debug=False)
