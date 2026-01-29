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
    # 支持两种模式：
    # 1. 文件名模式（旧）：提供文件名，从input_dir读取
    # 2. 绝对路径模式（新）：提供完整路径，直接使用
    original_srt_filename: Optional[str] = None  # 原始SRT文件名（中文）
    updated_audio_filename: Optional[str] = None  # 更新后的音频文件名（日文配音）
    updated_srt_filename: Optional[str] = None  # 更新后的SRT文件名（日文字幕）
    original_video_filename: Optional[str] = None  # 原始视频文件名（可选）
    background_audio_filename: Optional[str] = None  # 环境声文件名（可选）
    
    # 绝对路径模式（优先使用）
    original_srt_path: Optional[str] = None  # 原始SRT文件的绝对路径
    updated_audio_path: Optional[str] = None  # 更新后的音频文件的绝对路径
    updated_srt_path: Optional[str] = None  # 更新后的SRT文件的绝对路径
    original_video_path: Optional[str] = None  # 原始视频文件的绝对路径（可选）
    background_audio_path: Optional[str] = None  # 环境声文件的绝对路径（可选）
    
    max_slowdown_ratio: float = 0  # 最大慢放倍率（0=无限制，需要多少就放多少）
    quality_preset: str = "medium"  # 质量预设
    enable_frame_interpolation: bool = True  # 是否启用帧插值
    include_gaps: bool = True  # 是否包含字幕之间的间隔片段
    
    # GPU加速选项
    use_gpu: Optional[bool] = None  # 是否使用GPU加速（None=自动检测，True=强制启用，False=禁用）
    gpu_id: int = 0  # GPU设备ID
    
    # 性能优化选项（新增）
    use_optimized_mode: bool = True  # 是否使用优化模式（一次性处理，默认启用）
    max_segments_per_batch: int = 180  # 每批最多处理的片段数（默认180，避免命令行过长）
    
    # 环境声混合选项（新增）
    background_audio_volume: float = 0.3  # 环境声音量（0.0-1.0，默认30%）
    enable_background_audio: bool = False  # 是否启用环境声混合


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
    
    支持两种模式：
    1. 文件名模式：提供 *_filename 参数，从 input_dir 读取文件
    2. 绝对路径模式：提供 *_path 参数，直接使用文件的绝对路径
    
    处理流程：
    1. 解析原始SRT和更新SRT
    2. 分析时间轴差异
    3. 切割视频片段
    4. 慢放视频片段
    5. 拼接视频
    6. 替换音轨和嵌入字幕
    """
    from pathlib import Path
    
    input_dir = get_input_dir()
    output_dir = get_output_dir()
    scripts_dir = get_scripts_dir()
    
    task_id = generate_task_id()
    
    # 解析文件路径（优先使用绝对路径，否则使用文件名）
    def resolve_path(abs_path: Optional[str], filename: Optional[str], file_desc: str) -> Optional[Path]:
        """
        解析文件路径，优先使用绝对路径
        
        清理路径中的不可见Unicode控制字符
        """
        if abs_path:
            # 清理路径中的不可见Unicode控制字符
            # 移除常见的控制字符：LTR/RTL标记、零宽字符等
            cleaned_path = abs_path.strip()
            # 移除Unicode控制字符（U+200E, U+200F, U+202A-U+202E等）
            import unicodedata
            cleaned_path = ''.join(
                char for char in cleaned_path 
                if unicodedata.category(char) not in ('Cc', 'Cf', 'Cn', 'Co', 'Cs')
                or char in ('\n', '\r', '\t')  # 保留常见的空白字符
            )
            cleaned_path = cleaned_path.strip()
            
            # 使用绝对路径
            path = Path(cleaned_path)
            if not path.exists():
                raise HTTPException(
                    status_code=404, 
                    detail=f"{file_desc}不存在: {cleaned_path}\n原始路径: {repr(abs_path)}"
                )
            return path
        elif filename:
            # 使用文件名（从input_dir读取）
            path = input_dir / filename
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"{file_desc}不存在: {filename}")
            return path
        return None
    
    # 解析必需文件
    original_srt_path = resolve_path(
        request.original_srt_path, 
        request.original_srt_filename, 
        "原始SRT文件"
    )
    updated_audio_path = resolve_path(
        request.updated_audio_path, 
        request.updated_audio_filename, 
        "更新后的音频文件"
    )
    updated_srt_path = resolve_path(
        request.updated_srt_path, 
        request.updated_srt_filename, 
        "更新后的SRT文件"
    )
    
    # 验证必需文件
    if not original_srt_path:
        raise HTTPException(status_code=400, detail="必须提供原始SRT文件（original_srt_path 或 original_srt_filename）")
    if not updated_audio_path:
        raise HTTPException(status_code=400, detail="必须提供更新后的音频文件（updated_audio_path 或 updated_audio_filename）")
    if not updated_srt_path:
        raise HTTPException(status_code=400, detail="必须提供更新后的SRT文件（updated_srt_path 或 updated_srt_filename）")
    
    # 解析可选的视频文件
    original_video_path = resolve_path(
        request.original_video_path, 
        request.original_video_filename, 
        "原始视频文件"
    )
    
    # 解析可选的环境声文件
    background_audio_path = None
    if request.enable_background_audio:
        background_audio_path = resolve_path(
            request.background_audio_path, 
            request.background_audio_filename, 
            "环境声文件"
        )
        if background_audio_path:
            print(f"🎶 环境声文件: {background_audio_path}")
    
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
            
            # 根据优化模式选择处理器
            if request.use_optimized_mode:
                print("🚀 使用优化模式（一次性处理）")
                from video_timeline_sync_processor_optimized import OptimizedVideoTimelineSyncProcessor
                from video_timeline_sync_processor import VideoTimelineSyncProcessor
                
                # 先用标准处理器分析时间轴
                analyzer = VideoTimelineSyncProcessor(
                    original_video_path=str(original_video_path) if original_video_path else None,
                    original_srt_path=str(original_srt_path),
                    updated_audio_path=str(updated_audio_path),
                    updated_srt_path=str(updated_srt_path),
                    output_dir=str(task_output_dir),
                    max_slowdown_ratio=request.max_slowdown_ratio,
                    quality_preset=request.quality_preset,
                    enable_frame_interpolation=request.enable_frame_interpolation,
                    include_gaps=request.include_gaps,
                    use_gpu=request.use_gpu,
                    gpu_id=request.gpu_id
                )
                
                # 创建优化处理器（自动检测FFmpeg路径）
                processor = OptimizedVideoTimelineSyncProcessor(
                    # ffmpeg_path 参数移除，让处理器自动检测
                    use_gpu=request.use_gpu,  # None=自动检测，True=强制启用，False=禁用
                    gpu_device=request.gpu_id,
                    quality_preset=request.quality_preset,
                    enable_frame_interpolation=request.enable_frame_interpolation,
                    max_segments_per_batch=request.max_segments_per_batch,  # 传递每批片段数参数
                    background_audio_volume=request.background_audio_volume  # 传递环境声音量参数
                )
            else:
                print("💻 使用标准模式（多次处理）")
                from video_timeline_sync_processor import VideoTimelineSyncProcessor
                
                processor = VideoTimelineSyncProcessor(
                    original_video_path=str(original_video_path) if original_video_path else None,
                    original_srt_path=str(original_srt_path),
                    updated_audio_path=str(updated_audio_path),
                    updated_srt_path=str(updated_srt_path),
                    output_dir=str(task_output_dir),
                    max_slowdown_ratio=request.max_slowdown_ratio,
                    quality_preset=request.quality_preset,
                    enable_frame_interpolation=request.enable_frame_interpolation,
                    include_gaps=request.include_gaps,
                    use_gpu=request.use_gpu,
                    gpu_id=request.gpu_id
                )
                analyzer = processor
            
            # 如果没有提供视频文件，只进行差异分析
            if not original_video_path:
                with task_lock:
                    video_sync_tasks[task_id]["stage"] = "仅分析模式"
                    video_sync_tasks[task_id]["progress"] = 50
                
                # 只分析时间轴差异
                timeline_diffs = analyzer.analyze_timeline_diff()
                
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
                video_sync_tasks[task_id]["stage"] = "处理视频"
                video_sync_tasks[task_id]["progress"] = 30
            
            # 根据模式执行处理
            if request.use_optimized_mode:
                # 优化模式：使用复杂滤镜链一次性处理
                print("🚀 执行优化处理流程...")
                
                # 打印文件路径信息用于调试
                print(f"📁 原始SRT路径: {original_srt_path}")
                print(f"📁 更新SRT路径: {updated_srt_path}")
                print(f"📁 原始SRT存在: {original_srt_path.exists() if original_srt_path else 'N/A'}")
                print(f"📁 更新SRT存在: {updated_srt_path.exists() if updated_srt_path else 'N/A'}")
                
                if original_srt_path and original_srt_path.exists():
                    print(f"📁 原始SRT大小: {original_srt_path.stat().st_size} 字节")
                if updated_srt_path and updated_srt_path.exists():
                    print(f"📁 更新SRT大小: {updated_srt_path.stat().st_size} 字节")
                
                # 1. 分析时间轴差异
                timeline_diffs = analyzer.analyze_timeline_diff()
                
                print(f"📊 时间轴差异数量: {len(timeline_diffs) if timeline_diffs else 0}")
                
                # 检查 timeline_diffs 是否为空
                if not timeline_diffs:
                    error_msg = "时间轴分析失败：原始字幕或更新后字幕可能为空或格式不正确"
                    # 添加更多调试信息
                    if original_srt_path and original_srt_path.exists():
                        error_msg += f"\n原始SRT文件大小: {original_srt_path.stat().st_size} 字节"
                    if updated_srt_path and updated_srt_path.exists():
                        error_msg += f"\n更新SRT文件大小: {updated_srt_path.stat().st_size} 字节"
                    
                    with task_lock:
                        video_sync_tasks[task_id]["status"] = "failed"
                        video_sync_tasks[task_id]["progress"] = 0
                        video_sync_tasks[task_id]["stage"] = "错误"
                        video_sync_tasks[task_id]["error"] = error_msg
                    return
                
                # 2. 获取视频时长和帧率
                video_duration = analyzer._get_video_duration()
                video_fps = processor._get_video_fps(str(original_video_path))
                
                # 3. 转换为VideoSegment格式（包含间隔片段，使用帧边界对齐）
                from video_timeline_sync_processor_optimized import create_segments_from_timeline_diffs
                segments = create_segments_from_timeline_diffs(
                    timeline_diffs,
                    original_video_duration=video_duration,
                    include_gaps=request.include_gaps,
                    video_fps=video_fps  # 传递帧率用于帧边界对齐
                )
                
                # 检查 segments 是否为空
                if not segments:
                    with task_lock:
                        video_sync_tasks[task_id]["status"] = "failed"
                        video_sync_tasks[task_id]["progress"] = 0
                        video_sync_tasks[task_id]["stage"] = "错误"
                        video_sync_tasks[task_id]["error"] = "无法生成视频片段：字幕文件可能为空或格式不正确"
                    return
                
                # 4. 估算处理时间
                estimate = processor.estimate_processing_time(
                    video_duration_sec=video_duration,
                    num_segments=len(segments),
                    slowdown_segments=sum(1 for s in segments if s.needs_slowdown)
                )
                
                print(f"⏱️  预计处理时间: {estimate['estimated_minutes']:.1f} 分钟")
                
                # 5. 执行优化处理
                output_path = task_output_dir / "synced_video.mp4"
                
                def progress_callback(progress: int, message: str):
                    with task_lock:
                        video_sync_tasks[task_id]["progress"] = progress
                        video_sync_tasks[task_id]["stage"] = message
                
                process_result = processor.process_video_optimized(
                    input_video_path=str(original_video_path),
                    input_audio_path=str(updated_audio_path),
                    segments=segments,
                    output_path=str(output_path),
                    progress_callback=progress_callback,
                    background_audio_path=str(background_audio_path) if background_audio_path else None,
                    background_volume=request.background_audio_volume if request.enable_background_audio else None
                )
                
                # 处理返回结果（可能是字典或字符串）
                if isinstance(process_result, dict):
                    result = {
                        'success': True,
                        'output_path': process_result.get('output_path', str(output_path)),
                        'segments_processed': len(segments),
                        'mode': 'optimized',
                        'background_audio_mixed': background_audio_path is not None,
                        'processing_time_seconds': process_result.get('processing_time_seconds', 0),
                        'processing_time_minutes': process_result.get('processing_time_minutes', 0)
                    }
                else:
                    result = {
                        'success': True,
                        'output_path': str(process_result) if process_result else str(output_path),
                        'segments_processed': len(segments),
                        'mode': 'optimized',
                        'background_audio_mixed': background_audio_path is not None
                    }
            else:
                # 标准模式：多次FFmpeg调用
                print("💻 执行标准处理流程...")
                result = processor.process()
                result['mode'] = 'standard'
            
            # 执行处理
            if result['success']:
                with task_lock:
                    video_sync_tasks[task_id]["status"] = "completed"
                    video_sync_tasks[task_id]["progress"] = 100
                    video_sync_tasks[task_id]["stage"] = "完成"
                    video_sync_tasks[task_id]["message"] = f"视频同步完成（{result.get('mode', 'unknown')}模式）"
                    video_sync_tasks[task_id]["output_path"] = result['output_path']
                    video_sync_tasks[task_id]["segments_processed"] = result.get('segments_processed', 0)
                    video_sync_tasks[task_id]["processing_mode"] = result.get('mode', 'unknown')
                    video_sync_tasks[task_id]["completed_at"] = datetime.now().isoformat()
                    # 添加处理时间信息
                    video_sync_tasks[task_id]["processing_time_seconds"] = result.get('processing_time_seconds', 0)
                    video_sync_tasks[task_id]["processing_time_minutes"] = result.get('processing_time_minutes', 0)
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
        
        # 读取上传的文件内容
        original_content = await original_srt.read()
        updated_content = await updated_srt.read()
        
        print(f"📁 原始SRT文件大小: {len(original_content)} 字节")
        print(f"📁 更新SRT文件大小: {len(updated_content)} 字节")
        
        # 检查文件内容是否为空
        if len(original_content) == 0:
            return {
                "success": False,
                "error": "原始SRT文件内容为空"
            }
        if len(updated_content) == 0:
            return {
                "success": False,
                "error": "更新后的SRT文件内容为空"
            }
        
        with open(original_srt_path, "wb") as f:
            f.write(original_content)
        
        with open(updated_srt_path, "wb") as f:
            f.write(updated_content)
        
        # 验证文件是否成功写入
        if not original_srt_path.exists():
            return {
                "success": False,
                "error": f"原始SRT文件写入失败: {original_srt_path}"
            }
        if not updated_srt_path.exists():
            return {
                "success": False,
                "error": f"更新SRT文件写入失败: {updated_srt_path}"
            }
        
        print(f"✅ 文件已保存: {original_srt_path} ({original_srt_path.stat().st_size} 字节)")
        print(f"✅ 文件已保存: {updated_srt_path} ({updated_srt_path.stat().st_size} 字节)")
        
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
