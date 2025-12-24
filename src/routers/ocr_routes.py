"""
OCR 字幕提取路由
提供视频字幕提取的API接口
"""
import os
import uuid
import threading
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from models.ocr_models import (
    OCRConfig, OCRTaskRequest, OCRTaskResponse, OCRProgress, 
    VideoInfo, SubtitleRegion, BatchOCRRequest, SystemResourceInfo
)
from models.responses import AudioUploadResponse
from services.ocr_service import OCRService
from config.dependencies import get_current_dir, get_input_dir, get_output_dir

router = APIRouter(prefix="/api/ocr", tags=["OCR字幕提取"])

# 全局OCR服务实例和任务管理
ocr_service = OCRService()
ocr_tasks: Dict[str, OCRTaskResponse] = {}
ocr_task_lock = threading.Lock()


class OCRUploadResponse(BaseModel):
    """OCR视频上传响应"""
    success: bool
    filename: str
    video_info: VideoInfo
    message: str


@router.post("/upload-video", summary="上传视频文件用于OCR处理", response_model=OCRUploadResponse)
async def upload_video_for_ocr(file: UploadFile = File(...)):
    """上传视频文件并获取视频信息"""
    
    # 验证文件格式
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的视频格式: {file_extension}。支持的格式: {', '.join(allowed_extensions)}"
        )
    
    # 检查文件大小（限制500MB）
    max_size = 500 * 1024 * 1024  # 500MB
    file_content = await file.read()
    
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，最大支持 {max_size // (1024*1024)}MB"
        )
    
    # 保存文件
    input_dir = get_input_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = input_dir / safe_filename
    
    try:
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # 获取视频信息
        video_info = ocr_service.get_video_info(str(file_path))
        if not video_info:
            # 删除无效文件
            os.remove(file_path)
            raise HTTPException(status_code=400, detail="无法解析视频文件")
        
        return OCRUploadResponse(
            success=True,
            filename=safe_filename,
            video_info=video_info,
            message="视频上传成功"
        )
        
    except Exception as e:
        # 清理文件
        if file_path.exists():
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")


@router.post("/extract", summary="开始OCR字幕提取", response_model=OCRTaskResponse)
async def start_ocr_extraction(
    request: OCRTaskRequest,
    background_tasks: BackgroundTasks
):
    """启动OCR字幕提取任务"""
    
    input_dir = get_input_dir()
    video_path = input_dir / request.video_file
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    
    # 创建任务
    task_id = str(uuid.uuid4())
    
    with ocr_task_lock:
        ocr_tasks[task_id] = OCRTaskResponse(
            task_id=task_id,
            status="pending",
            progress=OCRProgress(
                stage="initializing",
                progress=0,
                current_frame=0,
                total_frames=0,
                message="任务初始化中..."
            ),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
    
    # 启动后台任务
    background_tasks.add_task(
        _process_ocr_task,
        task_id,
        str(video_path),
        request.config,
        request.subtitle_region
    )
    
    return ocr_tasks[task_id]


@router.get("/tasks/{task_id}", summary="获取OCR任务状态", response_model=OCRTaskResponse)
def get_ocr_task_status(task_id: str):
    """获取OCR任务的处理状态和进度"""
    
    with ocr_task_lock:
        if task_id not in ocr_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return ocr_tasks[task_id]


@router.delete("/tasks/{task_id}", summary="取消OCR任务")
def cancel_ocr_task(task_id: str):
    """取消正在进行的OCR任务"""
    
    with ocr_task_lock:
        if task_id not in ocr_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = ocr_tasks[task_id]
        if task.status == "running":
            task.status = "cancelled"
            task.updated_at = datetime.now().isoformat()
        
        return {"message": "任务已取消"}


@router.get("/tasks/{task_id}/download/srt", summary="下载SRT字幕文件")
def download_srt_file(task_id: str):
    """下载生成的SRT字幕文件"""
    
    with ocr_task_lock:
        if task_id not in ocr_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = ocr_tasks[task_id]
        if task.status != "completed" or not task.result:
            raise HTTPException(status_code=400, detail="任务未完成或无结果")
    
    output_dir = get_output_dir()
    srt_filename = f"{task_id}.srt"
    srt_path = output_dir / srt_filename
    
    if not srt_path.exists():
        # 生成SRT文件
        success = ocr_service.export_srt(task.result.subtitles, str(srt_path))
        if not success:
            raise HTTPException(status_code=500, detail="SRT文件生成失败")
    
    return FileResponse(
        path=str(srt_path),
        filename=f"{Path(task.result.video_file).stem}.srt",
        media_type="text/plain"
    )


@router.get("/tasks/{task_id}/download/txt", summary="下载TXT字幕文件")
def download_txt_file(task_id: str):
    """下载生成的TXT字幕文件"""
    
    with ocr_task_lock:
        if task_id not in ocr_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = ocr_tasks[task_id]
        if task.status != "completed" or not task.result:
            raise HTTPException(status_code=400, detail="任务未完成或无结果")
    
    output_dir = get_output_dir()
    txt_filename = f"{task_id}.txt"
    txt_path = output_dir / txt_filename
    
    if not txt_path.exists():
        # 生成TXT文件
        success = ocr_service.export_txt(task.result.subtitles, str(txt_path))
        if not success:
            raise HTTPException(status_code=500, detail="TXT文件生成失败")
    
    return FileResponse(
        path=str(txt_path),
        filename=f"{Path(task.result.video_file).stem}.txt",
        media_type="text/plain"
    )


@router.post("/batch-extract", summary="批量OCR字幕提取")
async def start_batch_ocr_extraction(
    request: BatchOCRRequest,
    background_tasks: BackgroundTasks
):
    """启动批量OCR字幕提取任务"""
    
    input_dir = get_input_dir()
    task_ids = []
    
    for video_file in request.video_files:
        video_path = input_dir / video_file
        if not video_path.exists():
            continue
        
        # 为每个视频创建独立任务
        task_id = str(uuid.uuid4())
        
        with ocr_task_lock:
            ocr_tasks[task_id] = OCRTaskResponse(
                task_id=task_id,
                status="pending",
                progress=OCRProgress(
                    stage="initializing",
                    progress=0,
                    current_frame=0,
                    total_frames=0,
                    message="批量任务等待中..."
                ),
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
        
        # 启动后台任务
        background_tasks.add_task(
            _process_ocr_task,
            task_id,
            str(video_path),
            request.config,
            request.subtitle_region
        )
        
        task_ids.append(task_id)
    
    return {"task_ids": task_ids, "message": f"已创建 {len(task_ids)} 个批量处理任务"}


@router.get("/system-info", summary="获取系统资源信息", response_model=SystemResourceInfo)
def get_system_info():
    """获取当前系统资源使用情况"""
    return ocr_service.get_system_resource_info()


@router.get("/languages", summary="获取支持的语言列表")
def get_supported_languages():
    """获取OCR支持的语言列表"""
    return ocr_service.get_supported_languages()


@router.get("/tasks", summary="获取所有OCR任务列表")
def list_ocr_tasks():
    """获取所有OCR任务的状态列表"""
    with ocr_task_lock:
        return list(ocr_tasks.values())


async def _process_ocr_task(
    task_id: str,
    video_path: str,
    config: OCRConfig,
    subtitle_region: Optional[SubtitleRegion]
):
    """后台处理OCR任务"""
    
    def update_progress(progress: OCRProgress):
        """更新任务进度"""
        with ocr_task_lock:
            if task_id in ocr_tasks:
                ocr_tasks[task_id].progress = progress
                ocr_tasks[task_id].updated_at = datetime.now().isoformat()
    
    try:
        # 更新任务状态为运行中
        with ocr_task_lock:
            if task_id in ocr_tasks:
                ocr_tasks[task_id].status = "running"
                ocr_tasks[task_id].updated_at = datetime.now().isoformat()
        
        # 执行OCR处理
        result = ocr_service.process_video_ocr(
            video_path=video_path,
            config=config,
            subtitle_region=subtitle_region,
            progress_callback=update_progress
        )
        
        # 更新任务状态为完成
        with ocr_task_lock:
            if task_id in ocr_tasks:
                ocr_tasks[task_id].status = "completed"
                ocr_tasks[task_id].result = result
                ocr_tasks[task_id].progress = OCRProgress(
                    stage="completed",
                    progress=100,
                    current_frame=0,
                    total_frames=0,
                    message="OCR处理完成"
                )
                ocr_tasks[task_id].updated_at = datetime.now().isoformat()
        
    except Exception as e:
        # 更新任务状态为失败
        with ocr_task_lock:
            if task_id in ocr_tasks:
                ocr_tasks[task_id].status = "failed"
                ocr_tasks[task_id].error = str(e)
                ocr_tasks[task_id].updated_at = datetime.now().isoformat()