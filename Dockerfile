# 1. 使用 Python 3.12 轻量版镜像
FROM python:3.12-slim-bookworm

# 2. 设置工作目录
WORKDIR /app

# 3. 代理构建参数（可选）
ARG PROXY

# 4. 安装系统级依赖（ffmpeg + curl 用于健康检查）
RUN if [ -n "$PROXY" ]; then \
        echo "使用代理: $PROXY"; \
        echo "Acquire::http::Proxy \"$PROXY\";" > /etc/apt/apt.conf.d/99proxy; \
        echo "Acquire::https::Proxy \"$PROXY\";" >> /etc/apt/apt.conf.d/99proxy; \
        apt-get update && apt-get install -y ffmpeg curl; \
        rm -f /etc/apt/apt.conf.d/99proxy; \
    else \
        echo "未使用代理"; \
        apt-get update && apt-get install -y ffmpeg curl; \
    fi && \
    rm -rf /var/lib/apt/lists/*

# 【关键】5. 先复制 requirements.txt（利用 Docker 缓存）
COPY requirements.txt .

# 6. 安装 Python 依赖（支持代理）
RUN if [ -n "$PROXY" ]; then \
        http_proxy=$PROXY https_proxy=$PROXY pip install --no-cache-dir -r requirements.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# 7. 复制项目代码
COPY main.py Tools.py ./

# 8. 创建数据目录并设置权限
RUN mkdir -p /app/data /app/example_musics && \
    groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app

# 9. 切换用户
USER appuser

# 10. 暴露端口
EXPOSE 6132

# 11. 环境变量：防止 Python 缓冲输出
ENV PYTHONUNBUFFERED=1

# 12. 启动命令
CMD ["python", "main.py"]