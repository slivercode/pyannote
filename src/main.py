import asyncio
from asyncio import SelectorEventLoop
import os
import uuid
import time
import threading
import subprocess
from typing import Dict, Optional, List
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timedelta
import sys
from fastapi.responses import RedirectResponse  # 新增：导入重定向响应类
import socket
import webbrowser
import pathlib
import shutil
import platform
import configparser

#阿里账户信息
DASHSCOPE_API_KEY = ""  # 从config.ini读取（如需使用阿里云服务）

# 获取项目内缓存路径
current_dir = pathlib.Path(__file__).parent.parent
print(f"使用项目内缓存目录：{current_dir}")


# -------------------------- 1：Input/Output目录初始化 --------------------------
# 定义与src平级的input（上传音频）和output（生成音频）目录
input_dir = current_dir / "input"  # 音频上传目录
output_dir = current_dir / "output"  # 音频生成目录
# 确保目录存在（不存在则自动创建，避免报错）
input_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)
print(f"音频上传目录（Input）：{input_dir}")
print(f"音频生成目录（Output）：{output_dir}")

# 2. 给 Hugging Face 模型设置缓存路径（HUGGINGFACE_HUB_CACHE）
hf_cache = current_dir / "hf_cache"
os.environ["HF_HOME"] = str(hf_cache)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_cache)  # Hugging Face 库会读取这个变量
os.environ["MODELSCOPE_CACHE"] = str(hf_cache)  # datasets 库额外兼容
os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)  # transformers 库额外兼容
os.environ["PYANNOTE_CACHE"] = str(hf_cache)
os.environ["TRANSFORMERS_OFFLINE"] = "1"  # Transformers 库离线
os.environ["HF_HUB_OFFLINE"] = "1"  # Hugging Face Hub 离线

# -------------------------- 添加 Python/Scripts 目录到 PATH --------------------------
# 构造 Scripts 目录路径（项目根目录下的 python/Scripts）
scripts_dir = current_dir / "python" / "Scripts"
# 确保 Scripts 目录存在（避免路径无效）
if not scripts_dir.exists():
    raise FileNotFoundError(f"Python Scripts 目录不存在：{scripts_dir}，请检查环境安装")
# 追加到 PATH（用 os.pathsep 实现跨平台兼容：Windows用;，Linux/mac用:）
os.environ["PATH"] = str(scripts_dir) + os.pathsep + os.environ["PATH"]
print(f"✅ 已将 Python Scripts 目录添加到 PATH：{scripts_dir}")


# 假设你的嵌入式 FFmpeg 在项目的 ffmpeg/bin 目录
FFMPEG_BIN_DIR = current_dir / "ffmpeg" / "bin"
# 把路径加到环境变量 PATH 中
os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ["PATH"]
# 验证是否能找到 ffmpeg
try:
    import subprocess

    subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
    print("✅ FFmpeg 找到并可用")
except Exception as e:
    print("❌ FFmpeg 未找到或不可用:", e)


# -------------------------- 基础配置 --------------------------
app = FastAPI(title="Python脚本轮询进度服务")
# 挂载static目录，用于访问Vue3前端
# 获取 main.py 所在的目录（即 src 目录）
# 拼接 static 目录的路径（src/static）
static_dir = current_dir / "src" / "static"
# 脚本目录（固定为scripts）
SCRIPTS_DIR = current_dir / "src" / "scripts"

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=static_dir), name="static")
# -------------------------- 挂载Input/Output目录，支持HTTP访问 --------------------------
# 访问规则：
# - Input文件：http://localhost:端口/input/文件名（如http://127.0.0.1:8514/input/20240520_123456_test.mp3）
# - Output文件：http://localhost:端口/output/文件名（如http://127.0.0.1:8514/output/result.wav）
app.mount(
    "/input",  # HTTP访问路径
    StaticFiles(directory=input_dir),  # 对应本地input目录
    name="input_files",  # 别名（用于FastAPI内部引用，可选）
)
app.mount(
    "/output",  # HTTP访问路径
    StaticFiles(directory=output_dir),  # 对应本地output目录
    name="output_files",
)


# 任务状态字典：key=任务ID，value=任务信息（进度、输出、状态等）
tasks: Dict[str, Dict] = {}
# 线程锁：保证多请求下任务字典的线程安全
task_lock = threading.Lock()
# 任务过期时间：完成后30分钟清理（避免内存占用）
TASK_EXPIRE_MINUTES = 30


# -------------------------- 配置文件读取 --------------------------
def load_config_from_ini():
    """从config.ini读取配置（如DASHSCOPE_API_KEY）"""
    config_path = current_dir / "config.ini"  # config.ini在项目根目录
    if config_path.exists():
        try:
            config = configparser.ConfigParser()
            config.read(config_path, encoding="utf-8")
            # 读取阿里云API密钥（如果存在）
            if config.has_section("Config") and config.has_option("Config", "DASHSCOPE_API_KEY"):
                dashscope_key = config.get("Config", "DASHSCOPE_API_KEY").strip()
                if dashscope_key:
                    os.environ["DASHSCOPE_API_KEY"] = dashscope_key
                    print(f"✅ 已加载 DASHSCOPE_API_KEY 配置")
        except Exception as e:
            print(f"⚠️ 读取配置文件失败：{e}")
    else:
        print(f"⚠️ 配置文件不存在：{config_path}")


# -------------------------- 数据模型 --------------------------
class TaskRequest(BaseModel):
    """启动任务的请求参数：脚本名 + 脚本参数"""

    script_name: str  # 脚本文件名（如long_task.py）
    script_args: Optional[List[str]] = []  # 传递给脚本的参数（可选）


class TaskStatus(BaseModel):
    """返回给前端的任务状态"""

    task_id: str
    status: str  # running:运行中, completed:完成, failed:失败
    progress: int  # 进度百分比（0-100）
    output: str  # 脚本所有输出内容（按行拼接）
    error: Optional[str] = None  # 错误信息（仅status=failed时有）
    start_time: str  # 任务启动时间
    end_time: Optional[str] = None  # 任务结束时间（仅完成/失败时有）


class AudioUploadResponse(BaseModel):
    """音频上传成功后的返回信息（给前端用）"""

    success: bool
    filename: str  # 保存后的文件名（含时间戳，避免重名）
    save_path: str  # 本地完整保存路径（如D:/project/input/20240520_123456_test.mp3）
    access_url: str  # HTTP访问URL（如/input/20240520_123456_test.mp3）
    file_size: int  # 文件大小（字节）
    message: str  # 提示信息


# 新增：打开文件夹的请求体模型（接收前端JSON）
class OpenFolderRequest(BaseModel):
    folder_path: str  # 对应前端发送的 "folder_path" 字段


# -------------------------- 工具函数 --------------------------
def get_script_path(script_name: str) -> str:
    """获取脚本的绝对路径，验证脚本是否存在"""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"脚本不存在：{script_name}")
    if not script_path.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持.py脚本")
    return script_path


def generate_task_id() -> str:
    """生成唯一任务ID（UUID简化版）"""
    return str(uuid.uuid4()).split("-")[0]


def clean_expired_tasks():
    """定时清理过期任务（后台线程，每10分钟执行一次）"""
    while True:
        time.sleep(3 * 60)  # 3分钟检查一次
        now = datetime.now()
        with task_lock:
            # 筛选出：完成时间存在 + 已过期的任务
            expired_task_ids = [
                task_id
                for task_id, task in tasks.items()
                if task["end_time"]
                and (now - datetime.strptime(task["end_time"], "%Y-%m-%d %H:%M:%S"))
                > timedelta(minutes=TASK_EXPIRE_MINUTES)
            ]
            for task_id in expired_task_ids:
                del tasks[task_id]
    # print(f"清理过期任务：共{len(expired_task_ids)}个")


async def stop_script_async(task_id: str) -> Dict:
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    with task_lock:
        task_info = tasks[task_id]
        process = task_info.get("process")
        if not process or process.returncode is not None:
            task_info["output"] += "\n[系统信息] 任务已结束，无需终止"
            return task_info

        # 异步终止子进程（适配 asyncio 子进程）
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)  # 等待5秒终止
        except asyncio.TimeoutError:
            process.kill()  # 超时则强制杀死
            await process.wait()

        # 更新任务状态
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_info["status"] = "stopped"
        task_info["end_time"] = end_time
        task_info["output"] += "\n[系统信息] 任务已被手动终止"
        return task_info


def clean_old_items(output_dir, keep_count=3, skip_hidden=True):
    """
    清理输出目录，只保留最新的指定数量的文件或文件夹

    参数:
        output_dir: 输出目录路径
        keep_count: 要保留的最新项目数量
        skip_hidden: 是否跳过隐藏文件/文件夹
    """
    if not os.path.exists(output_dir):
        print(f"错误: 目录 {output_dir} 不存在")
        return

    items = []
    with os.scandir(output_dir) as it:
        for entry in it:
            # 跳过隐藏文件/文件夹
            if skip_hidden and entry.name.startswith("."):
                continue

            if entry.is_file() or entry.is_dir():
                try:
                    # 获取修改时间
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                    items.append((entry.name, entry.path, mtime, entry.is_dir()))
                except Exception as e:
                    print(f"警告: 无法获取 {entry.name} 的信息，跳过。错误: {e}")

    # 按修改时间排序，最新的在后面
    items.sort(key=lambda x: x[2])

    if len(items) <= keep_count:
        print(f"当前项目数量({len(items)})不超过保留数量({keep_count})，无需清理")
        return

    items_to_delete = items[:-keep_count]
    items_to_keep = items[-keep_count:]

    print(f"发现 {len(items)} 个项目，将保留最新的 {keep_count} 个:")
    for item in items_to_keep:
        print(f"  保留: {item[0]} ({'文件夹' if item[3] else '文件'})")

    for item in items_to_delete:
        try:
            if item[3]:  # 文件夹
                shutil.rmtree(item[1])
            else:  # 文件
                os.remove(item[1])
            print(f"已删除: {item[0]}")
        except Exception as e:
            print(f"删除 {item[0]} 失败: {str(e)}")


def parse_script_output(line: str, task_info: Dict):
    """解析脚本输出，提取进度（兼容行首带空格/换行的情况）"""
    # 1. 保留原始输出（包括空格和换行），直接追加到output中
    # 避免strip()导致原始格式丢失，影响后续其他信息解析
    task_info["output"] += line + "\n"

    # 2. 处理行首空白（仅去除左侧空白，保留右侧和中间的格式）
    # 应对：行首有空格、换行符、制表符等情况
    processed_line = line.lstrip()  # 只去掉左侧空白，右侧空白不影响判断

    # 3. 解析进度（约定脚本输出PROGRESS:XX%格式的行表示进度）
    if processed_line.startswith("PROGRESS:"):
        try:
            # 分割后处理可能的空格（如"PROGRESS:  50%"）
            progress_part = processed_line.split(":", 1)[1].strip()
            progress_str = progress_part.rstrip("%").strip()
            # 去除百分号并转换为整数（兼容"50%"或"50"的情况）
            # 支持小数
            progress_float = float(progress_str)

            # 四舍五入成整数百分比（如果需要保留小数，可以直接存 float）
            progress = round(progress_float)

            # 确保进度在 0-100 之间
            task_info["progress"] = max(0, min(100, progress))
        except (ValueError, IndexError):
            # 格式错误时忽略，不影响其他输出解析
            pass


async def run_script_async(task_id: str, script_path: str, script_args: List[str]):
    """异步启动子进程，避免与 asyncio 事件循环冲突"""
    task_info = tasks[task_id]
    try:
        # 1. 获取主程序路径（打包后是 vocal_separation.exe，开发时是 python.exe）
        main_exe_path = pathlib.Path(sys.executable)
        if not main_exe_path.exists():
            raise FileNotFoundError(f"找不到主程序：{main_exe_path}")
        print(f"子进程使用的主程序路径：{main_exe_path}")

        # 2. 验证子脚本存在（script_path 已由 get_script_path 处理为绝对路径）
        script_abs_path = pathlib.Path(script_path)
        if not script_abs_path.exists():
            raise FileNotFoundError(f"脚本不存在：{script_abs_path}")
        print(f"子进程执行的脚本路径：{script_abs_path}")

        # -------------------------- 关键修改：添加UTF-8环境变量 --------------------------
        # 复制父进程环境变量，新增 PYTHONIOENCODING 强制子程序用UTF-8输出
        sub_env = os.environ.copy()
        # 强制Python子程序的 stdin/stdout/stderr 编码为UTF-8（核心解决乱码）
        sub_env["PYTHONIOENCODING"] = "utf-8"
        # 将 scripts_dir 添加到 PYTHONPATH 中（若已有其他路径，用分隔符拼接）
        # os.pathsep 是系统路径分隔符（Windows 是 ';'，Linux/macOS 是 ':'）
        # 正确：将 Path 对象转换为字符串（用 str() 或 .resolve() 确保绝对路径）
        scripts_dir_str = str(SCRIPTS_DIR.resolve())  # resolve() 获得规范绝对路径，避免符号链接问题
        if "PYTHONPATH" in sub_env:
            sub_env["PYTHONPATH"] = scripts_dir_str + os.pathsep + sub_env["PYTHONPATH"]
        else:
            sub_env["PYTHONPATH"] = scripts_dir_str
        # 可选：额外指定系统编码（增强兼容性）
        sub_env["LC_ALL"] = "en_US.UTF-8"
        sub_env["LANG"] = "en_US.UTF-8"

        # -------------------------- 3. 启动子进程（用嵌入的 Python 解释器） --------------------------
        # 开发环境：直接用 Python 解释器运行子脚本（无需--run-script）
        print(f"子进程 PYTHONPATH：{sub_env.get('PYTHONPATH')}")  # 关键：验证路径是否包含 src/scripts
        print(f"子进程使用的 Python 解释器：{str(main_exe_path)}")  # 验证是否是项目内嵌入式 Python
        cmd = [
            str(main_exe_path),  # Python解释器（python.exe）
            str(script_abs_path),  # 子脚本路径
            *script_args,  # 子脚本参数
        ]
        print(f"子进程启动命令：{' '.join(cmd)}")

        # 关键修改：使用字节模式（text=False），避免参数冲突
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,  # 字节流输出
            stderr=asyncio.subprocess.PIPE,
            env=sub_env,
            # 移除 text=True，默认 text=False（字节模式）
            # 不指定 encoding，避免冲突
        )
        task_info["process"] = process

        # 2. 异步读取 stdout（字节流 -> 手动解码为 UTF-8）
        async def read_stdout_async():
            async for line_bytes in process.stdout:  # type: ignore # line_bytes 是 bytes 类型
                # 手动解码：字节 -> 字符串（处理可能的编码错误）
                line = line_bytes.decode("utf-8", errors="replace")  # 无效字符用 � 替换
                if line:
                    print(line, end="")
                with task_lock:
                    parse_script_output(line, task_info)

        # 3. 异步读取 stderr（同样处理字节流）
        async def read_stderr_async():
            async for line_bytes in process.stderr: # type: ignore
                line = line_bytes.decode("utf-8", errors="replace")
                if line:
                    print(f"[ERROR] {line}", end="", file=sys.stderr)
                with task_lock:
                    task_info["output"] += f"[ERROR] {line}\n"

        # 5. 并发执行两个异步读取任务（用 asyncio.gather）
        await asyncio.gather(read_stdout_async(), read_stderr_async())

        # 6. 等待子进程结束并更新状态
        returncode = await process.wait()

        with task_lock:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task_info["end_time"] = end_time
            if returncode == 0:
                task_info["status"] = "completed"
                task_info["progress"] = min(task_info["progress"], 100)
            else:
                task_info["status"] = "failed"
                task_info["error"] = f"脚本返回码：{returncode}"

    except Exception as e:
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with task_lock:
            task_info["status"] = "failed"
            task_info["error"] = str(e)
            task_info["end_time"] = end_time
            task_info["output"] += f"\n[系统错误] {str(e)}"
    


# 在 API接口 部分最上方，添加根路径（/）的路由
@app.get("/", summary="默认首页：重定向到静态页面")
def read_root():
    # 重定向到 static 目录下的 index.html（静态首页文件）
    # 注意：需确保 src/static 目录下有 index.html 文件（你的前端首页）
    return RedirectResponse(url="/static/index.html")


@app.post(
    "/api/upload-audio",
    summary="上传音频文件到input目录",
    response_model=AudioUploadResponse,
)
async def upload_audio(
    file: UploadFile = File(..., description="音频文件（支持mp3、wav、flac、m4a格式）")
):
    """
    音频上传规则：
    1. 仅支持 mp3/wav/flac/m4a 格式
    2. 文件名自动添加时间戳（避免重名）
    3. 上传后自动保存到项目根目录的 input 文件夹
    """
    # 1. 验证文件类型（双重验证：MIME类型 + 文件后缀，防止恶意文件）
    allowed_content_types = [
        "audio/mpeg",  # mp3
        "audio/wav",  # wav
        "audio/flac",  # flac
        "audio/mp4",  # m4a
    ]
    allowed_extensions = [".mp3", ".wav", ".flac", ".m4a"]

    # 验证MIME类型
    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：{file.content_type}，仅允许 mp3/wav/flac/mp4",
        )

    # 验证文件后缀（防止改后缀的恶意文件）
    file_ext = pathlib.Path(file.filename).suffix.lower() # type: ignore
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件后缀：{file_ext}，仅允许 .mp3/.wav/.flac/.mp4",
        )

    # 2. 处理文件名：添加时间戳（避免重名）+ 清理恶意路径
    safe_filename = os.path.basename(file.filename) # type: ignore
    # 防止路径遍历攻击（如"../etc/passwd"）
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")  # 时间戳：20240520123456
    saved_filename = (
        f"{timestamp}_{safe_filename}"  # 最终保存的文件名：20240520123456_test.mp3
    )

    # 3. 保存文件到 input 目录
    save_path = pathlib.Path(input_dir) / saved_filename
    save_path_str = str(save_path)  # 本地完整路径（给前端/脚本参考）

    try:
        file_size = 0
        # 分块读取保存（避免大文件占用过多内存）
        with open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 每次读取1MB
                f.write(chunk)
                file_size += len(chunk)
        await file.close()  # 关闭文件流
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")

    # 4. 构建HTTP访问URL（前端可直接拼接服务地址使用）
    # 示例：服务地址是 http://127.0.0.1:8514，则完整访问URL是 http://127.0.0.1:8514/input/20240520123456_test.mp3
    access_url = f"/input/{saved_filename}"

    # 5. 返回上传结果
    return AudioUploadResponse(
        success=True,
        filename=saved_filename,
        save_path=save_path_str,
        access_url=access_url,
        file_size=file_size,
        message="音频文件上传成功",
    )


# -------------------------- API接口 --------------------------
@app.get("/api/scripts", summary="获取所有可用脚本列表")
def get_scripts() -> List[str]:
    """返回scripts目录下所有.py脚本的文件名"""
    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)
    return [
        f
        for f in os.listdir(SCRIPTS_DIR)
        if os.path.isfile(os.path.join(SCRIPTS_DIR, f)) and f.endswith(".py")
    ]


@app.post("/api/tasks", summary="启动一个脚本任务", response_model=TaskStatus)
async def create_task(req: TaskRequest) -> TaskStatus:  # 改为 async 接口
    script_path = get_script_path(req.script_name)
    task_id = generate_task_id()
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 初始化任务状态（与原逻辑一致）
    with task_lock:
        tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 10,
            "output": f"任务启动时间：{start_time}\n脚本路径：{script_path}\n参数：{req.script_args}\n\n",
            "error": None,
            "start_time": start_time,
            "end_time": None,
        }

    # 关键修改：用 asyncio 任务启动异步子进程（而非普通线程）
    asyncio.create_task(
        run_script_async(task_id, pathlib.Path(script_path), req.script_args) # type: ignore
    )

    return tasks[task_id] # type: ignore


@app.get("/api/tasks/{task_id}", summary="轮询获取任务进度", response_model=TaskStatus)
def get_task_progress(task_id: str) -> TaskStatus:
    """根据任务ID获取当前进度、输出和状态"""
    with task_lock:
        if task_id not in tasks:
            raise HTTPException(
                status_code=404, detail=f"任务不存在：{task_id}（可能已过期清理）"
            )
        # 返回当前任务状态（深拷贝避免外部修改）
        return tasks[task_id].copy() # type: ignore


# 对应的 API 接口改为异步
@app.get("/api/tasks/{task_id}/cancel", summary="取消任务", response_model=TaskStatus)
async def cancel_task_progress(task_id: str) -> TaskStatus:
    return await stop_script_async(task_id) # type: ignore


@app.post("/api/open-folder")
async def open_folder(req: OpenFolderRequest):  # 关键：用模型接收请求体
    # 1. 先校验路径非空
    if not req.folder_path.strip():
        raise HTTPException(status_code=400, detail="文件夹路径不能为空")

    folder_path = req.folder_path.strip()  # 去除首尾空格（避免前端传空字符）

    # 2. 校验路径是否存在
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=404, detail=f"文件夹不存在：{folder_path}")

    # 3. 校验路径是否为目录（避免传成文件路径）
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"不是有效的文件夹：{folder_path}")

    # 4. 跨平台打开文件夹（原有逻辑保留，优化错误信息）
    try:
        if platform.system() == "Windows":
            os.startfile(folder_path)  # Windows专用
        elif platform.system() == "Darwin":
            subprocess.run(
                ["open", folder_path], check=True, capture_output=True
            )  # Mac
        else:
            subprocess.run(
                ["xdg-open", folder_path], check=True, capture_output=True
            )  # Linux
        return {"status": "success", "message": f"已尝试打开文件夹：{folder_path}"}
    except Exception as e:
        # 捕获更详细的错误（如权限不足、路径含特殊字符）
        raise HTTPException(status_code=500, detail=f"打开文件夹失败：{str(e)}")


# -------------------------- 工具函数：找空闲端口（避免端口占用）--------------------------
def find_free_port(default_port: int) -> int:
    """自动找到可用端口，优先用.env的PORT，占用则递增"""
    port = default_port
    while port < default_port + 10:  # 最多尝试10个端口
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:  # 端口未占用
                return port
        port += 1
    raise RuntimeError("连续10个端口被占用，请关闭其他服务后重试")


# -------------------------- 启动服务 --------------------------
if __name__ == "__main__":

        # -------------------------- 新增：全局事件循环异常处理 --------------------------
    def handle_loop_exception(loop, context):
        """捕获并忽略子进程结束后的冗余 ConnectionResetError"""
        exception = context.get("exception")
        # 仅过滤 Windows 子进程管道关闭导致的特定错误
        if isinstance(exception, ConnectionResetError):
            # 忽略所有 ConnectionResetError，这是 Windows 子进程正常结束时的预期行为
            return
        # 其他错误正常打印
        loop.default_exception_handler(context)

    # --------------------------------------------------------------------------
    print("="*50)
    # 加载配置文件
    load_config_from_ini()
    # -------------------------- 修改：统一事件循环类型 --------------------------
    loop = None
    if platform.system() == "Windows":
        # Windows 推荐使用 ProactorEventLoop（适配子进程管道处理）
        loop = asyncio.ProactorEventLoop()
        print("✅ Windows 平台：使用 ProactorEventLoop")
    else:
        # Linux/macOS 使用 SelectorEventLoop
        loop = asyncio.SelectorEventLoop()
        print("✅ 非 Windows 平台：使用 SelectorEventLoop")
    asyncio.set_event_loop(loop)
    # 为新创建的事件循环注册异常处理器（必须在 set_event_loop 之后）
    loop.set_exception_handler(handle_loop_exception)
    # --------------------------------------------------------------------------
    print("="*50)


    # 获取output目录路径（根据你的目录结构）
    output_dir = os.path.join(current_dir, "output")
    # 获取input目录路径（根据你的目录结构）
    input_dir = os.path.join(current_dir, "input")
    # 保留最新的3个文件夹
    clean_old_items(output_dir, keep_count=3)
    # 保留最新的3个文件夹
    clean_old_items(input_dir, keep_count=3)

    # 启动后台清理过期任务的线程
    threading.Thread(target=clean_expired_tasks, daemon=True).start()

    # 1. 找到空闲端口
    free_port = find_free_port(8514)
    print(f"找到空闲端口：{free_port}")
    # 启动FastAPI服务（uvicorn）
    import uvicorn

    # 2. 自动打开浏览器（延迟1秒，等服务启动）
    url = f"http://127.0.0.1:{free_port}"
    print(f"服务即将启动，访问地址：{url}")
    webbrowser.open(url, new=2)  # new=2：打开新标签页

    uvicorn.run(
        app=app,  # ✅ 直接传入已定义的app实例
        host="127.0.0.1",  # 允许局域网访问（用户可在本地访问127.0.0.1）
        port=free_port,
        reload=False,  # 生产模式关闭热重载
        log_level="warning",  # ✅ 日志级别设为WARNING，INFO级日志全部不打印
    )
