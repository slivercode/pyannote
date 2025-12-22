"""
视频合并路由模块
处理视频、音频和字幕的合并操作
"""
import pathlib
import threading
import time
import uuid
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from config.dependencies import get_video_merger, get_video_merge_tasks, get_current_dir, get_output_dir

router = APIRouter(prefix="/api/video-merger", tags=["视频合并"])


@router.post("/merge", summary="合并视频、音频和字幕")
async def merge_video_audio_subtitle(
    video: UploadFile = File(..., description="MP4视频文件"),
    audio: UploadFile = File(None, description="WAV/MP3音频文件"),
    subtitle: UploadFile = File(None, description="SRT字幕文件"),
    mode: str = Form("replace_audio", description="合并模式"),
    remove_original_audio: bool = Form(True, description="是否去除原始音轨")
):
    """
    视频合并API
    支持6种合并模式：
    - replace_audio: 替换音轨
    - mix_audio: 混合音轨
    - embed_subtitle: 嵌入字幕
    - burn_subtitle: 烧录字幕
    - remove_audio: 去除音轨
    - video_only: 仅视频
    """
    try:
        video_merger = get_video_merger()
        if not video_merger:
            raise HTTPException(status_code=500, detail="视频合并器未初始化，请检查FFmpeg安装")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 创建临时目录
        temp_dir = pathlib.Path(get_current_dir()) / "temp" / f"video_merge_{task_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存上传的文件
        video_path = temp_dir / f"{timestamp}_video{pathlib.Path(video.filename).suffix}"
        with open(video_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        audio_path = None
        if audio and audio.filename:
            audio_path = temp_dir / f"{timestamp}_audio{pathlib.Path(audio.filename).suffix}"
            with open(audio_path, "wb") as f:
                content = await audio.read()
                f.write(content)
        
        subtitle_path = None
        if subtitle and subtitle.filename:
            subtitle_path = temp_dir / f"{timestamp}_subtitle{pathlib.Path(subtitle.filename).suffix}"
            with open(subtitle_path, "wb") as f:
                content = await subtitle.read()
                f.write(content)
        
        # 生成输出文件路径
        output_filename = f"{timestamp}_merged.mp4"
        output_path = pathlib.Path(get_output_dir()) / output_filename
        
        # 初始化任务状态
        video_merge_tasks = get_video_merge_tasks()
        video_merge_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "output_path": None,
            "error": None,
            "created_at": datetime.now().isoformat()
        }
        
        # 在后台线程中执行合并
        def run_merge_task():
            try:
                start_time = time.time()
                print(f"🎬 开始视频合并任务: {task_id}")
                
                # 更新进度
                video_merge_tasks[task_id]["progress"] = 30
                
                # 执行合并
                result_path = video_merger.merge_video_audio_subtitle(
                    video_path=str(video_path),
                    audio_path=str(audio_path) if audio_path else None,
                    subtitle_path=str(subtitle_path) if subtitle_path else None,
                    output_path=str(output_path),
                    mode=mode,
                    remove_original_audio=remove_original_audio
                )
                
                # 计算处理时间
                processing_time = time.time() - start_time
                
                # 更新任务状态
                video_merge_tasks[task_id]["status"] = "completed"
                video_merge_tasks[task_id]["progress"] = 100
                video_merge_tasks[task_id]["output_path"] = str(result_path)
                video_merge_tasks[task_id]["processing_time"] = f"{processing_time:.2f}秒"
                video_merge_tasks[task_id]["filename"] = output_filename
                
            except Exception as e:
                print(f"❌ 视频合并任务失败: {e}")
                video_merge_tasks[task_id]["status"] = "failed"
                video_merge_tasks[task_id]["error"] = str(e)
            
            finally:
                # 清理临时文件
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except:
                    pass
        
        # 启动后台线程
        thread = threading.Thread(target=run_merge_task, daemon=True)
        thread.start()
        
        return {"task_id": task_id, "message": "视频合并任务已启动"}
        
    except Exception as e:
        print(f"❌ 启动视频合并任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动视频合并任务失败: {str(e)}")


@router.post("/merge-simple", summary="简单视频音频合并")
async def merge_video_audio_only(
    video: UploadFile = File(..., description="MP4视频文件"),
    audio: UploadFile = File(..., description="WAV/MP3音频文件"),
    mode: str = Form("replace", description="合并模式: replace/mix/remove"),
    enable_slowdown: bool = Form(True, description="音频比视频长时是否自动慢放视频")
):
    """
    只合并视频和音频（不涉及字幕）
    """
    try:
        video_merger = get_video_merger()
        if not video_merger:
            raise HTTPException(status_code=500, detail="视频合并器未初始化，请检查FFmpeg安装")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 创建临时目录
        temp_dir = pathlib.Path(get_current_dir()) / "temp" / f"video_merge_simple_{task_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存上传的文件
        video_path = temp_dir / f"{timestamp}_video{pathlib.Path(video.filename).suffix}"
        with open(video_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        audio_path = temp_dir / f"{timestamp}_audio{pathlib.Path(audio.filename).suffix}"
        with open(audio_path, "wb") as f:
            content = await audio.read()
            f.write(content)
        
        # 生成输出文件路径
        output_filename = f"{timestamp}_merged_simple.mp4"
        output_path = pathlib.Path(get_output_dir()) / output_filename
        
        # 初始化任务状态
        video_merge_tasks = get_video_merge_tasks()
        video_merge_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "output_path": None,
            "error": None,
            "created_at": datetime.now().isoformat()
        }
        
        # 在后台线程中执行合并
        def run_merge_simple_task():
            try:
                start_time = time.time()
                
                # 执行合并
                result_path = video_merger.merge_video_audio_only(
                    video_path=str(video_path),
                    audio_path=str(audio_path),
                    output_path=str(output_path),
                    mode=mode,
                    enable_slowdown=enable_slowdown
                )
                
                # 更新任务状态
                video_merge_tasks[task_id]["status"] = "completed"
                video_merge_tasks[task_id]["progress"] = 100
                video_merge_tasks[task_id]["output_path"] = output_filename
                video_merge_tasks[task_id]["duration"] = time.time() - start_time
                
            except Exception as e:
                video_merge_tasks[task_id]["status"] = "failed"
                video_merge_tasks[task_id]["error"] = str(e)
        
        # 启动后台线程
        thread = threading.Thread(target=run_merge_simple_task, daemon=True)
        thread.start()
        
        return {
            "task_id": task_id,
            "message": "视频合并任务已启动",
            "status_url": f"/api/video-merger/status/{task_id}"
        }
        
    except Exception as e:
        print(f"❌ 启动视频合并任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动视频合并任务失败: {str(e)}")


@router.get("/status/{task_id}", summary="获取视频合并任务状态")
async def get_video_merge_status(task_id: str):
    """获取视频合并任务的当前状态"""
    video_merge_tasks = get_video_merge_tasks()
    if task_id not in video_merge_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return video_merge_tasks[task_id]


@router.get("/download/{filename}", summary="下载合并后的视频")
async def download_merged_video(filename: str):
    """下载合并后的视频文件"""
    file_path = pathlib.Path(get_output_dir()) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        filename=filename
    )


@router.post("/info", summary="获取视频信息")
async def get_video_info(
    video: UploadFile = File(..., description="视频文件")
):
    """获取视频文件的基本信息"""
    try:
        video_merger = get_video_merger()
        if not video_merger:
            raise HTTPException(status_code=500, detail="视频合并器未初始化")
        
        # 保存临时文件
        temp_dir = pathlib.Path(get_current_dir()) / "temp" / "video_info"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        temp_file = temp_dir / f"temp_{uuid.uuid4()}{pathlib.Path(video.filename).suffix}"
        with open(temp_file, "wb") as f:
            content = await video.read()
            f.write(content)
        
        try:
            # 获取视频信息
            info = video_merger.get_video_info(str(temp_file))
            return {"success": True, "info": info}
        
        finally:
            # 清理临时文件
            try:
                temp_file.unlink()
            except:
                pass
    
    except Exception as e:
        print(f"❌ 获取视频信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频信息失败: {str(e)}")