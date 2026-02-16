# 1. 使用 Python 3.14 轻量版镜像
FROM python:3.14-slim

# 2. 设置工作目录
WORKDIR /app

# 3. 安装系统级依赖
# pydub 必须依赖 ffmpeg 来处理 flac/mp3 转换
# 这里的 apt-get update 和 install 写在一起减少层数
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 4. 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 复制项目代码
COPY main.py .
COPY Tools.py .

# 6. 预创建数据目录 (重要：防止权限问题)
RUN mkdir -p /app/data

# 7. 暴露端口
EXPOSE 6132

# 8. 环境变量：防止 Python 缓冲输出，方便看日志
ENV PYTHONUNBUFFERED=1

# 9. 启动命令
CMD ["python", "main.py"]