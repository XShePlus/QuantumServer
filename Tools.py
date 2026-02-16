from pathlib import Path
import os
from pydub import AudioSegment
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error
class Tools:
    def check_and_create_file(self, file_path):
        file = Path(file_path)

        # 创建目录逻辑保持不变
        if not file.parent.exists():
            file.parent.mkdir(parents=True, exist_ok=True)
            print(f"目录不存在，已创建：{file.parent}")

        # 修改文件创建逻辑
        if not file.is_file() or file.stat().st_size == 0:  # 如果文件不存在，或者文件大小为0
            with open(file_path, "w", encoding='utf-8') as f:
                f.write("{}")  # 写入初始的 JSON 结构
        else:
            print(f"文件已存在且不为空：{file_path}")

    def is_file_actually_empty(self,file_path):
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
        try:
            target_path = os.path.join(target_dir, f"{final_title}.mp3")

            # 探测是否有封面流
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name',
                         '-of', 'csv=p=0', source_path]
            has_cover = subprocess.check_output(probe_cmd).decode('utf-8').strip()

            if has_cover:
                cmd = [
                    'ffmpeg', '-y', '-i', source_path,
                    '-map', '0:a:0', '-map', '0:v:0?',
                    '-c:a', 'libmp3lame', '-ab', '192k',
                    '-c:v', 'copy', '-id3v2_version', '3',
                    target_path
                ]
            else:
                cmd = [
                    'ffmpeg', '-y', '-i', source_path,
                    '-vn', '-acodec', 'libmp3lame', '-ab', '192k',
                    target_path
                ]

            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"最终生成文件: {target_path}")
        except Exception as e:
            print(f"转码或重命名过程出错: {e}")
        finally:
            if os.path.exists(source_path):
                os.remove(source_path)