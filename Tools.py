from pathlib import Path
import subprocess
import json
import os
from pydub import AudioSegment
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error

class Tools:
    def check_and_create_file(self, file_path):
        file = Path(file_path)

        # 创建目录
        if not file.parent.exists():
            file.parent.mkdir(parents=True, exist_ok=True)
            print(f"目录不存在，已创建：{file.parent}")

        # 如果文件不存在或为空，写入初始 JSON
        if not file.is_file() or file.stat().st_size == 0:
            with open(file_path, "w", encoding='utf-8') as f:
                f.write("{}")
        else:
            print(f"文件已存在且不为空：{file_path}")

    def is_file_actually_empty(self, file_path):
        file = Path(file_path)

        if not file.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        if not file.is_file():
            raise IsADirectoryError(f"路径不是有效文件：{file_path}")

        if file.stat().st_size == 0:
            return True

        try:
            with open(file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        return False
            return True
        except Exception as e:
            raise Exception(f"读取文件失败：{e}") from e

    @staticmethod
    def get_music_title(file_path, default_name):
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-show_entries', 'format_tags=title',
                '-of', 'json', file_path
            ]
            result = subprocess.check_output(cmd).decode('utf-8')
            data = json.loads(result)

            title = data.get('format', {}).get('tags', {}).get('title')

            if title and title.strip():
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    title = title.replace(char, '')
                return title.strip()
        except Exception as e:
            print(f"提取元数据标题失败: {e}")

        return os.path.splitext(default_name)[0]

    @staticmethod
    def transcode_to_mp3(source_path, target_dir, final_title):
        source_path = Path(source_path)
        target_path = Path(target_dir) / f"{final_title}.mp3"

        cmd = [
            'ffmpeg', '-y', '-i', str(source_path),
            '-map', '0:a?',           # 映射音频流（如果存在）
            '-map', '0:v?',           # 映射视频流（如果存在，通常是封面）
            '-c:a', 'libmp3lame', '-b:a', '192k',
            '-c:v', 'copy',            # 视频流直接复制
            '-disposition:v', 'attached_pic',  # 标记为附属封面
            '-id3v2_version', '3',
            '-map_metadata', '0',       # 保留原始元数据
            str(target_path)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"转码成功: {target_path} (封面已保留)")
            if source_path.exists():
                source_path.unlink()
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg 转码失败: {e.stderr.decode()}")
        except Exception as e:
            print(f"发生错误: {e}")