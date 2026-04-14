# Pyannote Audio Web UI

一个基于 FastAPI、Vue 和 pyannote.audio 的本地音频处理工具，用于上传音频、执行说话人分离、按说话人导出片段，并生成合并后的音频与时间记录。

项目主要面向 Windows 本地运行场景，预期项目目录中包含内置 Python、FFmpeg、PyTorch vendor 包和 Hugging Face 模型缓存。

## 功能概览

- 通过网页上传音频文件。
- 使用 pyannote 执行说话人分离。
- 支持自动识别说话人数，或手动指定固定人数、最小人数、最大人数。
- 将识别结果按说话人拆分为 `spk`、`mix`、`unknown` 等目录。
- 生成每个说话人的片段音频、合并音频和 JSON 时间记录。
- 支持按原始时间线保留空白间隔后再合并。
- 提供任务进度轮询、任务取消、输出目录打开等本地接口。
- 根据本机环境自动选择 CPU 或 GPU 版 PyTorch vendor 包。

## 目录结构

```text
pyannote/
├── config.ini
├── start.bat
├── src/
│   ├── main.py
│   ├── scripts/
│   │   ├── pyannote_audio_batch_handler.py
│   │   ├── merge.py
│   │   ├── torch_loader.py
│   │   └── util.py
│   └── static/
│       ├── index.html
│       ├── tool_merge.html
│       ├── axios.min.js
│       ├── vue.global.prod.js
│       └── wavesurfer.min.js
└── tools/
    ├── dynamically_import_tool.py
    ├── force_cpu.py
    └── test.py
```

运行时通常还需要以下目录，这些目录已在 `.gitignore` 中排除：

```text
ffmpeg/
hf_cache/
input/
output/
python/
vendor/
```

## 核心文件

- `src/main.py`: FastAPI 服务入口，负责静态页面、上传目录、输出目录、任务管理和本地工具接口。
- `src/static/index.html`: 主前端页面，负责上传文件、配置参数、启动分离任务、轮询进度和展示输出结果。
- `src/scripts/pyannote_audio_batch_handler.py`: 核心音频处理脚本，负责模型加载、转码、说话人分离、片段导出、合并和记录生成。
- `src/scripts/merge.py`: 用于对某个说话人目录中的片段重新合并。
- `src/scripts/util.py`: FFmpeg/FFprobe 工具函数，包含转码、截取片段、拼接、生成空白片段等逻辑。
- `src/scripts/torch_loader.py`: 检测 GPU 与 CUDA 环境，并从 `vendor/torch_gpu` 或 `vendor/torch_cpu` 加载 PyTorch。
- `start.bat`: Windows 启动脚本，检查内置 Python 和 FFmpeg 后启动 Web 服务。

## 运行方式

推荐在 Windows 下直接运行：

```bat
start.bat
```

启动脚本会检查：

- `python/python.exe`
- `src/main.py`
- `ffmpeg/bin/ffmpeg.exe`

服务启动后会自动寻找从 `8514` 开始的可用端口，并尝试打开浏览器，例如：

```text
http://127.0.0.1:8514
```

如果 `8514` 被占用，程序会向后尝试最多 10 个端口。

## 配置说明

`config.ini` 支持配置可选的 DashScope API Key：

```ini
[Config]
DASHSCOPE_API_KEY =
```

不要将真实密钥提交到仓库。建议在本地维护私有配置，或改为通过环境变量注入。

## 模型与缓存

处理脚本会加载：

```text
pyannote/speaker-diarization-community-1
```

服务入口中会将 Hugging Face、Transformers、ModelScope、Pyannote 相关缓存指向项目内的 `hf_cache` 目录，并设置离线模式：

```text
HF_HOME
HUGGINGFACE_HUB_CACHE
MODELSCOPE_CACHE
TRANSFORMERS_CACHE
PYANNOTE_CACHE
TRANSFORMERS_OFFLINE=1
HF_HUB_OFFLINE=1
```

因此，首次运行前需要确保模型文件已经存在于 `hf_cache` 中，或根据需要临时关闭离线模式并完成模型下载。

## API 概览

FastAPI 服务提供的主要接口：

- `GET /`: 重定向到 `/static/index.html`。
- `POST /api/upload-audio`: 上传音频文件到 `input/`。
- `GET /api/scripts`: 获取 `src/scripts/` 下可用 Python 脚本列表。
- `POST /api/tasks`: 启动脚本任务。
- `GET /api/tasks/{task_id}`: 查询任务进度、状态和日志输出。
- `GET /api/tasks/{task_id}/cancel`: 取消正在运行的任务。
- `POST /api/open-folder`: 在本机打开指定输出目录。

静态文件挂载：

- `/static`: 前端资源目录。
- `/input`: 上传文件访问目录。
- `/output`: 输出结果访问目录。

## 处理脚本参数

`pyannote_audio_batch_handler.py` 主要参数：

```text
--input-path              输入音频文件路径
--output-path             输出目录，默认 output
--translate               是否启用转写/翻译逻辑，默认 false
--extract-speech          是否提取说话人片段，默认 true
--preserve-timeline       合并时是否保留原始时间线，默认 false
--keep-tmp                是否保留临时片段，默认 false
--min-segment-duration    最短片段时长，默认 0.5 秒
--num-speakers            固定说话人数，0 表示自动
--min-speakers            最小说话人数，0 表示自动
--max-speakers            最大说话人数，0 表示自动
```

示例：

```powershell
python .\src\scripts\pyannote_audio_batch_handler.py `
  --input-path .\input\sample.wav `
  --output-path .\output `
  --num-speakers 2 `
  --preserve-timeline false
```

## 输出结果

处理完成后，结果会写入 `output/` 下以输入文件名命名的目录，常见内容包括：

```text
output/<输入文件名>/
├── 原始时间顺序记录.json
├── speaker_audios/
│   ├── spk00/
│   │   ├── seg_*.wav
│   │   ├── merged.wav
│   │   └── spk00_合并后时间顺序记录.json
│   ├── spk01/
│   ├── mix/
│   └── unknown/
└── tmp/
```

说明：

- `spkXX`: 明确识别出的单个说话人。
- `mix`: 多人重叠说话片段。
- `unknown`: 未识别或空白区间。
- `merged.*`: 当前说话人片段合并后的媒体文件。
- `*.json`: 原始时间线和合并后时间线记录。

## 重新合并说话人片段

可以使用 `merge.py` 对某个说话人目录重新合并：

```powershell
python .\src\scripts\merge.py `
  --input-dir .\output\<输入文件名>\speaker_audios\spk00 `
  --original-file .\input\sample.wav `
  --preserve-timeline false
```

## 注意事项

- 项目依赖 FFmpeg 和 FFprobe，运行前请确认 `ffmpeg/bin` 可用。
- GPU 加速依赖 NVIDIA 驱动、CUDA 兼容版本，以及 `vendor/torch_gpu` 中的匹配 PyTorch 包。
- 如果没有兼容 GPU，程序会尝试使用 `vendor/torch_cpu`。
- `input/` 和 `output/` 会在服务启动时自动创建，并且启动时会清理旧项目，仅保留最新的若干项。
- 代码中包含本地打开文件夹的能力，请只在可信本机环境中运行服务。
- 不要提交真实 API Key、Hugging Face Token、模型缓存、输入音频或输出结果。

## 开发状态

当前仓库没有 `requirements.txt`、`pyproject.toml` 或 README 之外的安装说明。依赖更像是通过项目内置 `python/`、`vendor/`、`ffmpeg/` 和 `hf_cache/` 管理。若要改造成可复现的开发环境，建议后续补充依赖锁定文件和环境初始化脚本。
祝看到这里的你有开心的一天。
