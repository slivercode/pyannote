"""
环境声提取 API 路由
从视频中提取背景音（去除人声）
"""

import os
import sys
import uuid
import pathlib
import threading
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel

# 添加 scripts 目录到路径
current_dir = pathlib.Path(__file__).parent.parent.parent
scripts_dir = current_dir / "src" / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

router = APIRouter(prefix="/api/background-audio", tags=["环境声提取"])

# 任务存储
background_audio_tasks = {}
task_lock = threading.Lock()


class BackgroundAudioResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    message: str
    output_path: Optional[str] = None
    download_url: Optional[str] = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed
    progress: int
    message: str
    output_path: Optional[str] = None
    download_url: Optional[str] = None


def run_extraction_task(task_id: str, video_path: str, output_dir: str, engine: str, model: str, device: str):
    """后台执行环境声提取任务"""
    try:
        with task_lock:
            background_audio_tasks[task_id]["status"] = "running"
            background_audio_tasks[task_id]["progress"] = 10
        
        from mp4_to_wav import BackgroundAudioExtractor
        
        extractor = BackgroundAudioExtractor(
            engine=engine,
            model=model,
            device=device
        )
        
        with task_lock:
            background_audio_tasks[task_id]["progress"] = 30
        
        output_path = extractor.extract_background_audio(
            input_path=video_path,
            output_dir=output_dir,
            sample_rate=44100,
            channels=2,
            keep_temp=False
        )
        
        with task_lock:
            background_audio_tasks[task_id]["status"] = "completed"
            background_audio_tasks[task_id]["progress"] = 100
            background_audio_tasks[task_id]["output_path"] = output_path
            background_audio_tasks[task_id]["download_url"] = f"/output/{os.path.basename(output_path)}"
            background_audio_tasks[task_id]["message"] = "环境声提取完成"
            
    except Exception as e:
        with task_lock:
            background_audio_tasks[task_id]["status"] = "failed"
            background_audio_tasks[task_id]["message"] = f"提取失败: {str(e)}"
            background_audio_tasks[task_id]["progress"] = 0


@router.post("/extract", response_model=BackgroundAudioResponse, summary="从视频提取环境声音")
async def extract_background_audio(
    video: UploadFile = File(..., description="视频文件（MP4/AVI/MOV/MKV）"),
    engine: str = Form("demucs", description="分离引擎: demucs/spleeter/ffmpeg"),
    model: str = Form("htdemucs", description="Demucs模型: htdemucs/htdemucs_ft/mdx_extra"),
    device: str = Form("cpu", description="计算设备: cpu/cuda")
):
    """
    从视频中提取环境声音（背景音，去除人声）
    
    - **video**: 上传的视频文件
    - **engine**: 分离引擎（demucs效果最好，ffmpeg最快但效果差）
    - **model**: Demucs模型（htdemucs_ft效果最好）
    - **device**: 计算设备（有GPU选cuda更快）
    
    返回任务ID，可通过 /api/background-audio/status/{task_id} 查询进度
    """
    # 验证文件类型
    allowed_extensions = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"]
    file_ext = pathlib.Path(video.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}，仅支持: {', '.join(allowed_extensions)}"
        )
    
    # 验证引擎参数
    if engine not in ["demucs", "spleeter", "ffmpeg"]:
        raise HTTPException(status_code=400, detail="引擎参数错误，仅支持: demucs/spleeter/ffmpeg")
    
    if device not in ["cpu", "cuda"]:
        raise HTTPException(status_code=400, detail="设备参数错误，仅支持: cpu/cuda")
    
    # 生成任务ID
    task_id = str(uuid.uuid4())[:8]
    
    # 保存上传的视频文件
    input_dir = current_dir / "input"
    output_dir = current_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_filename = f"{timestamp}_{video.filename}"
    video_path = input_dir / safe_filename
    
    try:
        with open(video_path, "wb") as f:
            content = await video.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    
    # 初始化任务状态
    with task_lock:
        background_audio_tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待处理",
            "output_path": None,
            "download_url": None,
            "video_path": str(video_path),
            "engine": engine,
            "model": model,
            "device": device,
            "created_at": datetime.now().isoformat()
        }
    
    # 启动后台任务
    thread = threading.Thread(
        target=run_extraction_task,
        args=(task_id, str(video_path), str(output_dir), engine, model, device),
        daemon=True
    )
    thread.start()
    
    return BackgroundAudioResponse(
        success=True,
        task_id=task_id,
        message="任务已创建，正在处理中"
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task_status(task_id: str):
    """查询环境声提取任务的状态和进度"""
    with task_lock:
        if task_id not in background_audio_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = background_audio_tasks[task_id]
        return TaskStatusResponse(
            task_id=task_id,
            status=task["status"],
            progress=task["progress"],
            message=task["message"],
            output_path=task.get("output_path"),
            download_url=task.get("download_url")
        )


@router.get("/list", summary="获取所有任务列表")
async def list_tasks():
    """获取所有环境声提取任务的列表"""
    with task_lock:
        return {
            "success": True,
            "tasks": [
                {
                    "task_id": task_id,
                    "status": task["status"],
                    "progress": task["progress"],
                    "message": task["message"],
                    "created_at": task.get("created_at"),
                    "download_url": task.get("download_url")
                }
                for task_id, task in background_audio_tasks.items()
            ]
        }
