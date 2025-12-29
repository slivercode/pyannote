#!/usr/bin/env python3
"""
重构后应用的完整启动脚本
基于debug_start.py的成功经验
"""
import sys
import pathlib
import traceback
import asyncio
import os
import platform
import socket
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from typing import Dict
import configparser

# 添加src目录到Python路径
src_dir = pathlib.Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

print("🚀 启动重构后的应用...")
print(f"Python路径已添加: {src_dir}")

try:
    # 导入FastAPI相关模块
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    # 导入路由模块
    from routers import file_management, task_management
    from routers import video_merger as video_merger_router
    from routers import tts_routes, config_management
    from config.dependencies import init_config

    # 获取项目目录
    current_dir = pathlib.Path(__file__).parent
    print(f"使用项目内缓存目录：{current_dir}")

    # 初始化目录（跨平台兼容）
    input_dir = current_dir / "input"
    output_dir = current_dir / "output"
    
    # 创建目录
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 在Linux/Mac上设置目录权限
    if os.name != 'nt':
        try:
            os.chmod(input_dir, 0o755)
            os.chmod(output_dir, 0o755)
            print(f"✅ 已设置目录权限（Linux/Mac）")
        except Exception as e:
            print(f"⚠️ 设置目录权限失败（可能无需修改）: {e}")
    
    print(f"音频上传目录（Input）：{input_dir}")
    print(f"音频生成目录（Output）：{output_dir}")

    # 设置环境变量
    hf_cache = current_dir / "hf_cache"
    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_cache)
    os.environ["MODELSCOPE_CACHE"] = str(hf_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)
    os.environ["PYANNOTE_CACHE"] = str(hf_cache)
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"

    # 添加Python Scripts到PATH
    scripts_dir = current_dir / "python" / "Scripts"
    if scripts_dir.exists():
        os.environ["PATH"] = str(scripts_dir) + os.pathsep + os.environ["PATH"]
        print(f"✅ 已将 Python Scripts 目录添加到 PATH：{scripts_dir}")

    # FFmpeg配置
    FFMPEG_BIN_DIR = current_dir / "ffmpeg" / "bin"
    os.environ["PATH"] = str(FFMPEG_BIN_DIR) + os.pathsep + os.environ["PATH"]

    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
        print("✅ FFmpeg 找到并可用")
    except Exception as e:
        print("❌ FFmpeg 未找到或不可用:", e)

    # 创建FastAPI应用
    app = FastAPI(title="Python脚本轮询进度服务")

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载静态文件
    static_dir = current_dir / "src" / "static"
    SCRIPTS_DIR = current_dir / "src" / "scripts"
    
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    if input_dir.exists():
        app.mount("/input", StaticFiles(directory=input_dir), name="input_files")
    if output_dir.exists():
        app.mount("/output", StaticFiles(directory=output_dir), name="output_files")

    # 初始化全局变量
    tasks = {}
    task_lock = threading.Lock()
    video_merge_tasks = {}
    tts_dubbing_tasks = {}

    # 初始化视频合并器
    video_merger = None
    try:
        scripts_path = str(current_dir / "src" / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        
        from video_merger import VideoMerger
        
        ffmpeg_path = "ffmpeg"
        project_ffmpeg = current_dir / "ffmpeg" / "bin" / "ffmpeg.exe"
        if project_ffmpeg.exists():
            ffmpeg_path = str(project_ffmpeg)
        
        video_merger = VideoMerger(ffmpeg_path=ffmpeg_path)
        print(f"✅ 视频合并器初始化成功，FFmpeg路径: {ffmpeg_path}")
    except Exception as e:
        print(f"⚠️ 视频合并器初始化失败: {e}")
        video_merger = None

    # 初始化依赖注入配置
    init_config(
        current_dir=current_dir,
        input_dir=input_dir,
        output_dir=output_dir,
        scripts_dir=SCRIPTS_DIR,
        tasks=tasks,
        task_lock=task_lock,
        video_merger=video_merger,
        video_merge_tasks=video_merge_tasks,
        tts_dubbing_tasks=tts_dubbing_tasks
    )

    # 注册路由
    app.include_router(file_management.router)
    app.include_router(task_management.router)
    app.include_router(video_merger_router.router)
    app.include_router(tts_routes.router)
    app.include_router(config_management.router)
    
    # 导入并注册OCR路由
    from routers import ocr_routes
    app.include_router(ocr_routes.router)
    
    # 导入并注册视频同步路由
    from routers import video_sync_routes
    app.include_router(video_sync_routes.router)

    # 根路径路由
    @app.get("/", summary="默认首页：重定向到静态页面")
    def read_root():
        return RedirectResponse(url="/static/index.html")

    # 配置文件读取
    def load_config_from_ini():
        config_path = current_dir / "config.ini"
        if config_path.exists():
            try:
                config = configparser.ConfigParser()
                config.read(config_path, encoding="utf-8")
                if config.has_section("Config") and config.has_option("Config", "DASHSCOPE_API_KEY"):
                    dashscope_key = config.get("Config", "DASHSCOPE_API_KEY").strip()
                    if dashscope_key:
                        os.environ["DASHSCOPE_API_KEY"] = dashscope_key
                        print(f"✅ 已加载 DASHSCOPE_API_KEY 配置")
            except Exception as e:
                print(f"⚠️ 读取配置文件失败：{e}")

    # 清理函数
    def clean_expired_tasks():
        while True:
            time.sleep(3 * 60)
            now = datetime.now()
            with task_lock:
                expired_task_ids = [
                    task_id for task_id, task in tasks.items()
                    if task.get("end_time") and 
                    (now - datetime.strptime(task["end_time"], "%Y-%m-%d %H:%M:%S")) > timedelta(minutes=30)
                ]
                for task_id in expired_task_ids:
                    del tasks[task_id]

    def find_free_port(default_port: int) -> int:
        port = default_port
        while port < default_port + 10:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", port)) != 0:
                    return port
            port += 1
        raise RuntimeError("连续10个端口被占用，请关闭其他服务后重试")

    # 启动服务
    def handle_loop_exception(loop, context):
        exception = context.get("exception")
        if isinstance(exception, ConnectionResetError):
            return
        loop.default_exception_handler(context)

    print("="*50)
    load_config_from_ini()
    
    # 设置事件循环
    if platform.system() == "Windows":
        loop = asyncio.ProactorEventLoop()
        print("✅ Windows 平台：使用 ProactorEventLoop")
    else:
        loop = asyncio.SelectorEventLoop()
        print("✅ 非 Windows 平台：使用 SelectorEventLoop")
    
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(handle_loop_exception)
    print("="*50)

    # 启动后台清理线程
    threading.Thread(target=clean_expired_tasks, daemon=True).start()

    # 启动服务
    free_port = find_free_port(8514)
    print(f"找到空闲端口：{free_port}")
    
    import uvicorn
    url = f"http://127.0.0.1:{free_port}"
    print(f"服务即将启动，访问地址：{url}")
    
    # 延迟打开浏览器
    def open_browser():
        time.sleep(2)
        webbrowser.open(url, new=2)
    
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        app=app,
        host="127.0.0.1",
        port=free_port,
        reload=False,
        log_level="warning",
    )

except Exception as e:
    print(f"❌ 启动失败: {e}")
    print("详细错误信息:")
    traceback.print_exc()
    input("按回车键退出...")