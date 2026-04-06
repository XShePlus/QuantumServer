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

    @staticmethod
    def safe_subprocess_run(cmd, timeout=30, **kwargs):
        """
        安全执行子进程命令，防止命令注入

        参数:
            cmd: 命令列表，如 ['ffprobe', '-v', 'quiet', ...]
            timeout: 超时时间（秒）
            **kwargs: 传递给subprocess.run的其他参数

        返回:
            subprocess.CompletedProcess对象

        异常:
            ValueError: 如果命令参数包含危险字符
            subprocess.TimeoutExpired: 如果命令超时
            subprocess.CalledProcessError: 如果命令返回非零状态码
        """
        # 验证所有参数都是字符串且不包含危险字符
        for arg in cmd:
            if not isinstance(arg, str):
                raise ValueError(f"非字符串参数: {arg}")
            # 检查危险字符（命令注入尝试）
            dangerous_chars = [';', '&', '|', '$', '`', '>', '<', '\n', '\r']
            for char in dangerous_chars:
                if char in arg:
                    raise ValueError(f"危险字符 '{char}' 在参数中: {arg}")

        # 设置默认参数
        kwargs.setdefault('capture_output', True)
        kwargs.setdefault('text', True)
        kwargs.setdefault('encoding', 'utf-8')

        # 执行命令，带超时
        return subprocess.run(cmd, timeout=timeout, **kwargs)

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
            # 使用安全的子进程执行
            result = Tools.safe_subprocess_run(cmd, timeout=10)
            data = json.loads(result.stdout)

            title = data.get('format', {}).get('tags', {}).get('title')

            if title and title.strip():
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    title = title.replace(char, '')
                return title.strip()
        except (ValueError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            print(f"提取元数据标题失败（安全错误）: {e}")
        except json.JSONDecodeError as e:
            print(f"解析FFprobe输出失败: {e}")
        except Exception as e:
            print(f"提取元数据标题失败（未知错误）: {e}")

        return os.path.splitext(default_name)[0]

    @staticmethod
    def transcode_to_mp3(source_path, target_dir, final_title, timeout=60):
        """
        将音频文件转码为MP3格式

        参数:
            source_path: 源文件路径
            target_dir: 目标目录
            final_title: 最终文件名（不含扩展名）
            timeout: 转码超时时间（秒）

        返回:
            bool: 转码是否成功
        """
        source_path = Path(source_path)
        target_path = Path(target_dir) / f"{final_title}.mp3"

        # 验证目标文件名
        if not final_title or not isinstance(final_title, str):
            print(f"错误：无效的文件名: {final_title}")
            return False

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
            # 使用安全的子进程执行
            Tools.safe_subprocess_run(cmd, timeout=timeout, check=True)
            print(f"转码成功: {target_path} (封面已保留)")

            # 只有在转码成功后才删除源文件
            if source_path.exists():
                source_path.unlink()
                print(f"已删除源文件: {source_path}")

            return True

        except ValueError as e:
            print(f"命令注入防护触发: {e}")
        except subprocess.TimeoutExpired as e:
            print(f"FFmpeg 转码超时（{timeout}秒）: {e}")
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg 转码失败（退出码 {e.returncode}）: {e.stderr}")
        except Exception as e:
            print(f"转码过程中发生未知错误: {e}")

        return False