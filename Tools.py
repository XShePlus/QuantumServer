from pathlib import Path
import os
from pydub import AudioSegment
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
    def transcode_to_mp3(source_path, target_path):
        try:
            audio = AudioSegment.from_file(source_path)
            audio.export(target_path, format="mp3", bitrate="320k")
            print(f"转码成功: {target_path}")
        except Exception as e:
            print(f"转码失败: {str(e)}")
        finally:
            if os.path.exists(source_path):
                os.remove(source_path)