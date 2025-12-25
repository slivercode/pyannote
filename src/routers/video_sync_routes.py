"""
视频时间轴同步路由模块
"""
import os
import sys
import threading
import pathlib
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.dependencies import get_input_dir, get_output_dir, get_scripts_dir

router = APIRouter(prefix="/api/video-sync", tags=["视频同步"])


class VideoSyncRequest(BaseModel):
    """视频时间轴同步请求"""
    original_srt_filename: str  # 原始SRT文件名（中文）
    updated_audio_filename: str  # 更新后的音频文件名（日文配音）
    updated_srt_filename: str  # 更新后的SRT文件名（日文字幕）
    original_video_filename: Optional[str] = None  # 原始视频文件名（可选）
    max_slowdown_ratio: float = 2.0  # 最大慢放倍率
    quality_preset: str = "medium"  # 质量预设
    enable_frame_interpolation: bool = True  # 是否启用帧插值
    include_gaps: bool = True  # 是否包含字幕之间的间隔片段


# 视频同步任务字典
video_sync_tasks = {}
task_lock = threading.Lock()


def generate_task_id() -> str:
    """生成唯一任务ID"""
    import uuid
    return str(uuid.uuid4()).split("-")[0]


@router.post("/start", summary="启动视频时间轴同步任务")
async def start_video_sync(request: VideoSyncRequest):
    """
    启动视频时间轴同步任务
    
    处理流程：
    1. 解析原始SRT和更新SRT
    2. 分析时间轴差异
    3. 切割视频片段
    4. 慢放视频片段
    5. 拼接视频
    6. 替换音轨和嵌入字幕
    """
    input_dir = get_input_dir()
    output_dir = get_output_dir()
    scripts_dir = get_scripts_dir()
    
    task_id = generate_task_id()
    
    # 构建文件路径（所有上传的文件都在input_dir中）
    original_srt_path = input_dir / request.original_srt_filename
    updated_audio_path = input_dir / request.updated_audio_filename
    updated_srt_path = input_dir / request.updated_srt_filename
    
    # 验证文件存在
    if not original_srt_path.exists():
        raise HTTPException(status_code=404, detail=f"原始SRT文件不存在: {request.original_srt_filename}")
    if not updated_audio_path.exists():
        raise HTTPException(status_code=404, detail=f"更新后的音频文件不存在: {request.updated_audio_filename}")
    if not updated_srt_path.exists():
        raise HTTPException(status_code=404, detail=f"更新后的SRT文件不存在: {request.updated_srt_filename}")
    
    # 如果提供了视频文件，验证其存在
    original_video_path = None
    if request.original_video_filename:
        original_video_path = input_dir / request.original_video_filename
        if not original_video_path.exists():
            raise HTTPException(status_code=404, detail=f"原始视频文件不存在: {request.original_video_filename}")
    
    # 创建任务输出目录
    task_output_dir = output_dir / f"video_sync_{task_id}"
    task_output_dir.mkdir(parents=True, exist_ok=True)
    
    # 初始化任务状态
    with task_lock:
        video_sync_tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0,
            "stage": "初始化",
            "message": "任务已创建，等待处理...",
            "created_at": datetime.now().isoformat(),
            "output_path": None,
            "error": None
        }
    
    # 在后台线程中执行视频同步
    def run_video_sync():
        try:
            # 更新状态：开始处理
            with task_lock:
                video_sync_tasks[task_id]["status"] = "running"
                video_sync_tasks[task_id]["stage"] = "分析时间轴差异"
                video_sync_tasks[task_id]["progress"] = 10
            
            # 导入视频同步处理器
            sys.path.insert(0, str(scripts_dir))
            from video_timeline_sync_processor import VideoTimelineSyncProcessor
            
            # 创建处理器
            processor = VideoTimelineSyncProcessor(
                original_video_path=str(original_video_path) if original_video_path else None,
                original_srt_path=str(original_srt_path),
                updated_audio_path=str(updated_audio_path),
                updated_srt_path=str(updated_srt_path),
                output_dir=str(task_output_dir),
                max_slowdown_ratio=request.max_slowdown_ratio,
                quality_preset=request.quality_preset,
                enable_frame_interpolation=request.enable_frame_interpolation,
                include_gaps=request.include_gaps
            )
            
            # 如果没有提供视频文件，只进行差异分析
            if not original_video_path:
                with task_lock:
                    video_sync_tasks[task_id]["stage"] = "仅分析模式"
                    video_sync_tasks[task_id]["progress"] = 50
                
                # 只分析时间轴差异
                timeline_diffs = processor.analyze_timeline_diff()
                
                with task_lock:
                    video_sync_tasks[task_id]["status"] = "completed"
                    video_sync_tasks[task_id]["progress"] = 100
                    video_sync_tasks[task_id]["stage"] = "完成"
                    video_sync_tasks[task_id]["message"] = f"时间轴差异分析完成，共{len(timeline_diffs)}个片段"
                    video_sync_tasks[task_id]["timeline_diffs"] = len(timeline_diffs)
                    video_sync_tasks[task_id]["completed_at"] = datetime.now().isoformat()
                return
            
            # 执行完整的视频同步流程
            with task_lock:
                video_sync_tasks[task_id]["stage"] = "切割视频片段"
                video_sync_tasks[task_id]["progress"] = 30
            
            # 执行处理
            result = processor.process()
            
            if result['success']:
                with task_lock:
                    video_sync_tasks[task_id]["status"] = "completed"
                    video_sync_tasks[task_id]["progress"] = 100
                    video_sync_tasks[task_id]["stage"] = "完成"
                    video_sync_tasks[task_id]["message"] = "视频同步完成"
                    video_sync_tasks[task_id]["output_path"] = result['output_path']
                    video_sync_tasks[task_id]["segments_processed"] = result.get('segments_processed', 0)
                    video_sync_tasks[task_id]["completed_at"] = datetime.now().isoformat()
                    # 生成下载URL
                    output_filename = os.path.basename(result['output_path'])
                    video_sync_tasks[task_id]["download_url"] = f"/output/video_sync_{task_id}/{output_filename}"
            else:
                with task_lock:
                    video_sync_tasks[task_id]["status"] = "failed"
                    video_sync_tasks[task_id]["error"] = result.get('error', '未知错误')
                    video_sync_tasks[task_id]["completed_at"] = datetime.now().isoformat()
                    
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            with task_lock:
                video_sync_tasks[task_id]["status"] = "failed"
                video_sync_tasks[task_id]["error"] = error_msg
                video_sync_tasks[task_id]["completed_at"] = datetime.now().isoformat()
    
    # 启动后台线程
    thread = threading.Thread(target=run_video_sync, daemon=True)
    thread.start()
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "视频同步任务已创建"
    }


@router.get("/status/{task_id}", summary="获取视频同步任务状态")
async def get_video_sync_status(task_id: str):
    """获取视频同步任务的当前状态"""
    with task_lock:
        if task_id not in video_sync_tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        return video_sync_tasks[task_id]


@router.get("/download/{task_id}/{filename}", summary="下载同步后的视频")
async def download_synced_video(task_id: str, filename: str):
    """下载同步后的视频文件"""
    output_dir = get_output_dir()
    
    file_path = output_dir / f"video_sync_{task_id}" / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="video/mp4"
    )


@router.post("/analyze", summary="仅分析时间轴差异（不处理视频）")
async def analyze_timeline_diff(
    original_srt: UploadFile = File(..., description="原始SRT文件"),
    updated_srt: UploadFile = File(..., description="更新后的SRT文件")
):
    """
    仅分析两个SRT文件的时间轴差异，不处理视频
    用于快速预览需要慢放的片段
    """
    input_dir = get_input_dir()
    output_dir = get_output_dir()
    scripts_dir = get_scripts_dir()
    
    try:
        # 保存上传的文件
        original_srt_path = input_dir / f"temp_original_{generate_task_id()}.srt"
        updated_srt_path = input_dir / f"temp_updated_{generate_task_id()}.srt"
        
        with open(original_srt_path, "wb") as f:
            f.write(await original_srt.read())
        
        with open(updated_srt_path, "wb") as f:
            f.write(await updated_srt.read())
        
        # 导入处理器
        sys.path.insert(0, str(scripts_dir))
        from video_timeline_sync_processor import VideoTimelineSyncProcessor
        
        # 创建临时处理器（不需要视频文件）
        processor = VideoTimelineSyncProcessor(
            original_video_path="",  # 空路径
            original_srt_path=str(original_srt_path),
            updated_audio_path="",  # 空路径
            updated_srt_path=str(updated_srt_path),
            output_dir=str(output_dir / "temp_analysis")
        )
        
        # 分析时间轴差异
        timeline_diffs = processor.analyze_timeline_diff()
        
        # 清理临时文件
        original_srt_path.unlink()
        updated_srt_path.unlink()
        
        # 构建返回数据
        diffs_data = []
        for diff in timeline_diffs:
            diffs_data.append({
                "index": diff.index,
                "original_duration_ms": diff.original_entry.duration_ms,
                "updated_duration_ms": diff.updated_entry.duration_ms,
                "duration_diff_ms": diff.duration_diff_ms,
                "slowdown_ratio": diff.slowdown_ratio,
                "needs_slowdown": diff.needs_slowdown,
                "warning": diff.warning
            })
        
        return {
            "success": True,
            "total_entries": len(timeline_diffs),
            "needs_slowdown_count": sum(1 for d in timeline_diffs if d.needs_slowdown),
            "diffs": diffs_data
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"{str(e)}\n{traceback.format_exc()}"
        }
