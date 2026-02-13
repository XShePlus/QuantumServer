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
    def transcode_to_mp3(source_path, target_path):
        try:
            # 提取封面数据
            cover_data = None
            try:
                flac_file = FLAC(source_path)
                if flac_file.pictures:
                    cover_data = flac_file.pictures[0].data
            except Exception as e:
                print(f"提取封面失败: {e}")

            # 执行转码
            audio = AudioSegment.from_file(source_path)
            audio.export(target_path, format="mp3", bitrate="320k")

            # 封面嵌入MP3
            if cover_data:
                try:
                    mp3_file = MP3(target_path, ID3=ID3)
                    try:
                        mp3_file.add_tags()
                    except error:
                        pass

                    mp3_file.tags.add(
                        APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,
                            desc=u'Cover',
                            data=cover_data
                        )
                    )
                    mp3_file.save()
                    print("封面嵌入成功")
                except Exception as e:
                    print(f"写入封面失败: {e}")

            print(f"转码完成: {target_path}")

        except Exception as e:
            print(f"转码异常: {str(e)}")
        finally:
            if os.path.exists(source_path):
                os.remove(source_path)