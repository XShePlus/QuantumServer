from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import time
import os
from Tools import Tools
from apscheduler.schedulers.background import BackgroundScheduler

# 模板room
room = {
    "status": bool,  # 可否加入
    "message_list": list,  # 消息列表eg: ["a:hhh","b:hhh"]
    "present_number": int,  # 当前人数
    "max_number": int,  # 最大人数
    "cancel_time": int,  # 使用时间戳
}

app = Flask(__name__)
CORS(app, resources=r"/*")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

tools = Tools()
MUSIC_DIR = './data/music'
TEMP_DIR = './data/temp'
ROOMS_LIST_PATH = "./data/rooms_list.json"
tools.check_and_create_file(ROOMS_LIST_PATH)
for d in [MUSIC_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

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
    cancel_time = int(time.time()) + 3600
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    j[room_name] = {
        "status": True,
        "max_number": max_number,
        "present_number": 0,
        "cancel_time": cancel_time,
        "message_list": []
    }
    f = open(ROOMS_LIST_PATH, "w")
    f.write(json.dumps(j))
    f.close()
    return "行"


@app.route('/api/enter_room', methods=['POST'])
def enter_room():
    request_data = request.get_data().decode('utf-8')
    request_json = json.loads(request_data)
    room_name = request_json.get("room_name")
    j = json.load(open(ROOMS_LIST_PATH, "r"))
    if not j[room_name]['status']:
        return "不行"
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
    message=request_json.get("message")
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


@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return "No file", 400

    file = request.files['file']
    filename = file.filename
    if not filename:
        return "Empty filename", 400

    base_name = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.mp3':
        save_path = os.path.join(MUSIC_DIR, filename)
        file.save(save_path)
        return jsonify({"msg": "MP3 上传成功", "status": "done"}), 200

    elif ext == '.flac':
        temp_path = os.path.join(TEMP_DIR, filename)
        target_path = os.path.join(MUSIC_DIR, f"{base_name}.mp3")
        file.save(temp_path)

        thread = threading.Thread(target=tools.transcode_to_mp3, args=(temp_path, target_path))
        thread.start()
        return jsonify({"msg": "FLAC 上传成功，后台转码中...", "status": "processing"}), 202

    else:
        return "不支持的格式", 400
@app.route('/api/list_songs', methods=['GET'])
def list_songs():
    # 只列出音乐文件夹下的 mp3
    songs = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith('.mp3')]
    return jsonify(songs)

@app.route('/api/stream/<filename>')
def stream(filename):
    return send_from_directory(MUSIC_DIR, filename)

def clean_expired_rooms():
    try:
        with open(ROOMS_LIST_PATH, "r", encoding="utf-8") as f:
            if tools.is_file_actually_empty(ROOMS_LIST_PATH):
                return
            rooms_data = json.load(f)

        current_timestamp = int(time.time())
        valid_rooms = {}
        for room_name, room_info in rooms_data.items():
            if "cancel_time" in room_info and room_info["cancel_time"] > current_timestamp:
                valid_rooms[room_name] = room_info

        with open(ROOMS_LIST_PATH, "w", encoding="utf-8") as f:
            json.dump(valid_rooms, f, ensure_ascii=False)

        print(f"定时清理过期房间完成，当前剩余有效房间：{list(valid_rooms.keys())}")

    except Exception as e:
        print(f"定时清理过期房间时出现异常：{str(e)}")


def init_scheduler():
    # 初始化后台调度器
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 添加定时任务：每10分钟执行一次 clean_expired_rooms（可修改间隔）
    # interval 表示固定时间间隔，seconds=600 即 10分钟，也可使用 minutes=10
    scheduler.add_job(clean_expired_rooms, 'interval', seconds=600, id="clean_expired_rooms_job")
    # 启动调度器
    scheduler.start()
    print("定时任务调度器已启动，每10分钟清理一次过期房间")


init_scheduler()

app.run(host='0.0.0.0', port=6132, debug=True)
