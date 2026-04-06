# Quantum-Server

### 概述

Quantum-Server是一个基于Flask的音乐同步服务，支持多用户房间、实时聊天和音乐同步播放。
当前项目尚不完善，代码健壮性不足。
有任何好的建议或修改可以通过以下联系方式反馈：

- 邮箱：xsheworking@126.com
- QQ：1960995065（请备注反馈）

### 安装方式

克隆本仓库后请自行配置Python环境（Python 3.12 推荐）。

本项目需要安装以下Python库（通过`pip install -r requirements.txt`安装）：

```
flask
flask-cors
apscheduler
pydub
audioop-lts
```

> **注意**：`json`、`time`、`threading`、`os`、`shutil`、`pathlib`、`sys` 均为Python标准库，**无需单独安装**。
> `audioop-lts` 用于兼容Python 3.13+（官方已移除`audioop`模块），Python 3.12及以下可忽略。

同时，请在你的系统中安装 [ffmpeg](https://ffmpeg.org/)。

#### 服务端指令

服务启动后，可在控制台输入以下指令进行管理：

| 指令 | 功能说明 |
|:-----|:--------|
| **ls** | 列出所有房间信息（房间名、人数、状态） |
| **sse** | 查看各房间当前SSE连接数 |
| **rm [房间名]** | 强制删除指定房间及其数据 |
| **set versionName [名称]** | 设置版本名称 |
| **set versionCode [号码]** | 设置版本号（整数） |
| **set updateURL [链接]** | 设置更新地址 |
| **exit** | 退出服务端并关闭程序 |

### Docker部署

Quantum-Server提供了Docker镜像，便于快速部署和运行。
本服务已发布至 Docker Hub，镜像名：`xsheplus/quantum-server:latest`

#### 拉取镜像
```bash
docker pull xsheplus/quantum-server:latest
```

#### 运行容器（基础方式）
```bash
docker run -d -p 6132:6132 xsheplus/quantum-server
```

#### 使用卷挂载持久化数据
```bash
# 创建主机目录
mkdir -p /host/data /host/example_musics

# 运行容器并挂载卷
docker run -d \
  -p 6132:6132 \
  -v /host/example_musics:/app/example_musics \
  -v /host/data:/app/data \
  xsheplus/quantum-server
```

#### 使用环境变量自定义路径
```bash
docker run -d \
  -p 6132:6132 \
  -v /custom/music:/custom_music \
  -v /custom/data:/custom_data \
  -e EXAMPLE_MUSICS_PATH=/custom_music \
  -e DATA_PATH=/custom_data \
  -e TEMP_PATH=/custom_data/temp \
  xsheplus/quantum-server
```

#### 环境变量说明
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATA_PATH` | `./data` | 数据目录路径，包含房间数据和配置文件 |
| `EXAMPLE_MUSICS_PATH` | `./example_musics` | 示例音乐目录路径 |
| `TEMP_PATH` | `{DATA_PATH}/temp` | 临时文件目录路径 |

#### 健康检查
容器包含健康检查配置，每30秒检查服务可用性，超时3秒，重试3次。健康检查端点：`/api/version`

#### 资源限制建议
对于生产环境，建议设置资源限制：
```bash
docker run -d \
  --memory=512m \
  --cpus=1.0 \
  -p 6132:6132 \
  xsheplus/quantum-server
```

### Docker Compose部署（推荐）

Quantum-Server提供了`docker-compose.yml`配置文件，简化部署和管理流程。

#### 快速开始

1. **确保docker compose已安装**
   ```bash
   docker compose version
   ```

2. **创建必要的目录**
   ```bash
   mkdir -p data example_musics
   ```

3. **启动服务**
   ```bash
   docker compose up -d
   ```

4. **查看日志**
   ```bash
   docker compose logs -f
   ```

5. **停止服务**
   ```bash
   docker compose down
   ```

#### 基础配置示例

`docker-compose.yml` 基础版本：
```yaml
services:
  quantum-server:
    build: .
    ports:
      - "6132:6132"
    volumes:
      - ./data:/app/data
      - ./example_musics:/app/example_musics
    environment:
      - DATA_PATH=/app/data
      - EXAMPLE_MUSICS_PATH=/app/example_musics
    restart: unless-stopped
```

#### 高级配置示例

自定义路径和资源限制：
```yaml
services:
  quantum-server:
    build: .
    ports:
      - "6132:6132"
    volumes:
      - /mnt/storage/quantum/data:/app/data
      - /mnt/music/library:/app/example_musics
      - /mnt/temp:/app/data/temp
    environment:
      - DATA_PATH=/app/data
      - EXAMPLE_MUSICS_PATH=/mnt/music/library
      - TEMP_PATH=/mnt/temp
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '2.0'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6132/api/version"]
      interval: 30s
      timeout: 3s
      retries: 3
```

#### 环境变量说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATA_PATH` | `/app/data` | 数据目录路径，包含房间数据和配置文件 |
| `EXAMPLE_MUSICS_PATH` | `/app/example_musics` | 示例音乐目录路径 |
| `TEMP_PATH` | `{DATA_PATH}/temp` | 临时文件目录路径 |
| `PYTHONUNBUFFERED` | `1` | 禁用Python输出缓冲，实时查看日志 |
| `TZ` | `Asia/Shanghai` | 时区设置（可选） |

### 代理配置指南

#### 构建时代理配置

在构建Docker镜像时，如果处于内网环境需要代理访问外部资源，可以通过以下方式配置：

**方式一：使用docker compose构建参数**
```bash
# 设置环境变量
export PROXY=http://127.0.0.1:7897

# 使用代理构建
docker compose build --build-arg PROXY=${PROXY}
```

**方式二：直接使用docker build**
```bash
docker build \
  --build-arg PROXY=http://host.docker.internal:7897 \
  -t quantum-server .
```

**方式三：在docker-compose.yml中直接指定**
```yaml
build:
  context: .
  args:
    PROXY: "http://host.docker.internal:7897"  # Docker Desktop
    # 或 "http://172.17.0.1:7897"  # Linux Docker
```

#### 代理地址说明

- **Docker Desktop（Windows/Mac）**: `http://host.docker.internal:7897`
- **Linux Docker**: `http://172.17.0.1:7897`
- **自定义代理**: `http://your-proxy-ip:port`

#### 运行时网络代理

如果容器运行时需要访问外部API，可以在docker-compose.yml中配置：
```yaml
environment:
  - http_proxy=http://proxy-server:port
  - https_proxy=http://proxy-server:port
  - no_proxy=localhost,127.0.0.1
```

### 自定义模板音乐配置

#### 目录结构示例

```
/your/music/library/
├── 流行音乐/
│   ├── 周杰伦 - 晴天.mp3
│   ├── 林俊杰 - 江南.mp3
│   └── 邓紫棋 - 光年之外.mp3
├── 古典音乐/
│   ├── 贝多芬 - 月光奏鸣曲.mp3
│   └── 莫扎特 - 小夜曲.mp3
├── 摇滚音乐/
│   └── 痛仰乐队 - 扎西德勒.mp3
└── 自定义分类/
    └── 你的音乐文件.mp3
```

#### 配置方法

**方法一：通过卷挂载**
```yaml
volumes:
  - /path/to/your/music/library:/app/example_musics
```

**方法二：通过环境变量指定路径**
```yaml
volumes:
  - /path/to/your/music/library:/custom/music
environment:
  - EXAMPLE_MUSICS_PATH=/custom/music
```

#### 支持的音乐格式

服务支持以下格式，启动时会自动转码为MP3：

- **音频格式**: `.mp3`、`.wav`、`.m4a`、`.flac`、`.aac`、`.ogg`
- **视频格式**: `.mp4`、`.mkv`（提取音频轨道）

#### 音乐文件命名建议

1. **使用标准格式**: `艺术家 - 歌曲名.mp3`
2. **避免特殊字符**: 不要使用 `<>:"/\|?*` 等字符
3. **中文支持**: 完全支持中文字符和标点
4. **元数据**: 建议在音乐文件中嵌入正确的ID3标签（标题、艺术家等）

#### 自动转码流程

首次启动或添加新音乐时：
1. 扫描 `EXAMPLE_MUSICS_PATH` 目录
2. 识别非MP3格式文件
3. 在后台线程中转码为MP3
4. 保留原始文件，生成 `歌曲名.mp3`
5. 提取音频元数据作为显示名称

### 常见问题解答

#### Q1: 容器启动失败，提示权限拒绝
**A**: 确保挂载的目录对容器用户（appuser，UID 1000）有读写权限：
```bash
# 修复目录权限
sudo chown -R 1000:1000 ./data ./example_musics
# 或
sudo chmod -R 755 ./data ./example_musics
```

#### Q2: 音乐文件无法播放或找不到
**A**: 检查以下事项：
1. 文件是否在正确的挂载目录中
2. 文件格式是否受支持
3. 查看容器日志确认转码是否成功：
   ```bash
   docker compose logs quantum-server | grep -i "转码\|标准化"
   ```

#### Q3: 首次启动时间很长
**A**: 这是正常现象，服务正在：
1. 扫描音乐目录并转码非MP3文件
2. 初始化数据目录结构
3. 启动后台调度任务（用户活跃监测30s、房间有效期检查420s）

可以通过日志监控进度：
```bash
docker compose logs -f
```

#### Q4: 如何更新服务
**A**:
```bash
# 拉取最新代码后
docker compose build --no-cache
docker compose down
docker compose up -d
```

#### Q5: 如何备份数据
**A**: 数据存储在挂载的卷中：
```bash
# 备份数据目录
tar -czf quantum-backup-$(date +%Y%m%d).tar.gz ./data

# 恢复数据
tar -xzf quantum-backup-20230401.tar.gz
docker compose down
docker compose up -d
```

#### Q6: 如何查看健康状态
**A**:
```bash
docker compose ps
docker inspect --format='{{json .State.Health}}' quantum-server
```

#### Q7: 容器内存占用过高
**A**: 调整资源限制：
```yaml
deploy:
  resources:
    limits:
      memory: 1G
      cpus: '1.5'
```

#### Q8: 如何自定义端口
**A**: 修改docker-compose.yml中的端口映射：
```yaml
ports:
  - "8080:6132"  # 主机端口:容器端口
```

#### Q9: Python版本兼容性说明
**A**: 本项目基于 **Python 3.12** 构建（见Dockerfile）。Python 3.13+ 已移除内置 `audioop` 模块，项目通过自动引入 `audioop-lts` 兼容包处理此问题，无需手动干预。

### 注意事项

1. **首次启动延迟**：首次启动时，服务会扫描音乐目录并转码非MP3文件，可能需要一些时间
2. **文件权限**：确保挂载的目录对容器用户（appuser，UID 1000）有读写权限
3. **存储空间**：音频转码需要临时存储空间，确保有足够磁盘空间
4. **代理配置**：构建时如需代理，请参考前面的代理配置指南
5. **网络访问**：确保主机防火墙允许6132端口访问
6. **Docker Compose版本**：请使用 Docker Compose V2（`docker compose`），旧版 `docker-compose` 命令已废弃