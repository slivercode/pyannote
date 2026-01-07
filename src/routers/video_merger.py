"""
视频字幕烧录路由模块
处理视频和字幕的烧录合并操作
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

router = APIRouter(prefix="/api/video-merger", tags=["视频字幕烧录"])


@router.post("/burn-subtitle", summary="烧录字幕到视频")
async def burn_subtitle_to_video(
    video: UploadFile = File(..., description="MP4视频文件"),
    subtitle: UploadFile = File(..., description="SRT字幕文件"),
    subtitle_font_size: int = Form(24, description="字幕字体大小"),
    subtitle_font_name: str = Form("Arial", description="字幕字体名称"),
    subtitle_color: str = Form("white", description="字幕颜色"),
    subtitle_outline_color: str = Form("black", description="字幕描边颜色"),
    subtitle_outline_width: int = Form(2, description="字幕描边宽度"),
    subtitle_position: str = Form("bottom", description="字幕位置"),
    subtitle_bold_weight: int = Form(0, description="字体粗细(0-900)"),
    subtitle_margin_v: int = Form(20, description="垂直边距(像素)")
):
    """
    视频字幕烧录API
    将SRT字幕烧录到视频画面中，生成带硬字幕的MP4文件
    """
    try:
        video_merger = get_video_merger()
        if not video_merger:
            raise HTTPException(status_code=500, detail="视频合并器未初始化，请检查FFmpeg安装")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 创建临时目录
        temp_dir = pathlib.Path(get_current_dir()) / "temp" / f"subtitle_burn_{task_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存上传的文件
        video_path = temp_dir / f"{timestamp}_video{pathlib.Path(video.filename).suffix}"
        with open(video_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        subtitle_path = temp_dir / f"{timestamp}_subtitle{pathlib.Path(subtitle.filename).suffix}"
        with open(subtitle_path, "wb") as f:
            content = await subtitle.read()
            f.write(content)
        
        # 生成输出文件路径
        output_filename = f"{timestamp}_with_subtitles.mp4"
        output_path = pathlib.Path(get_output_dir()) / output_filename
        
        # 初始化任务状态
        video_merge_tasks = get_video_merge_tasks()
        video_merge_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "output_path": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
            "font_settings": {
                "font_size": subtitle_font_size,
                "font_name": subtitle_font_name,
                "color": subtitle_color,
                "outline_color": subtitle_outline_color,
                "outline_width": subtitle_outline_width,
                "position": subtitle_position,
                "bold_weight": subtitle_bold_weight,
                "margin_v": subtitle_margin_v
            }
        }
        
        # 在后台线程中执行烧录
        def run_burn_task():
            try:
                start_time = time.time()
                print(f"🎬 开始字幕烧录任务: {task_id}")
                
                # 更新进度
                video_merge_tasks[task_id]["progress"] = 30
                
                # 执行字幕烧录
                result_path = video_merger.burn_subtitle_to_video(
                    video_path=str(video_path),
                    subtitle_path=str(subtitle_path),
                    output_path=str(output_path),
                    subtitle_font_size=subtitle_font_size,
                    subtitle_font_name=subtitle_font_name,
                    subtitle_color=subtitle_color,
                    subtitle_outline_color=subtitle_outline_color,
                    subtitle_outline_width=subtitle_outline_width,
                    subtitle_position=subtitle_position,
                    subtitle_bold_weight=subtitle_bold_weight,
                    subtitle_margin_v=subtitle_margin_v
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
                print(f"❌ 字幕烧录任务失败: {e}")
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
        thread = threading.Thread(target=run_burn_task, daemon=True)
        thread.start()
        
        return {"task_id": task_id, "message": "字幕烧录任务已启动"}
        
    except Exception as e:
        print(f"❌ 启动字幕烧录任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动字幕烧录任务失败: {str(e)}")


@router.post("/burn-subtitle-clean", summary="烧录字幕到视频（自动清理说话人标识）")
async def burn_subtitle_to_video_with_cleaning(
    video: UploadFile = File(..., description="MP4视频文件"),
    subtitle: UploadFile = File(..., description="SRT字幕文件"),
    subtitle_font_size: int = Form(24, description="字幕字体大小"),
    subtitle_font_name: str = Form("Arial", description="字幕字体名称"),
    subtitle_color: str = Form("white", description="字幕颜色"),
    subtitle_outline_color: str = Form("black", description="字幕描边颜色"),
    subtitle_outline_width: int = Form(2, description="字幕描边宽度"),
    subtitle_position: str = Form("bottom", description="字幕位置"),
    subtitle_bold_weight: int = Form(0, description="字体粗细(0-900)"),
    subtitle_margin_v: int = Form(20, description="垂直边距(像素)"),
    clean_speakers: bool = Form(True, description="是否清理说话人标识")
):
    """
    视频字幕烧录API（支持自动清理说话人标识）
    将SRT字幕烧录到视频画面中，自动去除[spk01]:等说话人标识
    """
    try:
        video_merger = get_video_merger()
        if not video_merger:
            raise HTTPException(status_code=500, detail="视频合并器未初始化，请检查FFmpeg安装")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 创建临时目录
        temp_dir = pathlib.Path(get_current_dir()) / "temp" / f"subtitle_burn_clean_{task_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存上传的文件
        video_path = temp_dir / f"{timestamp}_video{pathlib.Path(video.filename).suffix}"
        with open(video_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        subtitle_path = temp_dir / f"{timestamp}_subtitle{pathlib.Path(subtitle.filename).suffix}"
        with open(subtitle_path, "wb") as f:
            content = await subtitle.read()
            f.write(content)
        
        # 调试：检查上传后的字幕文件内容
        print(f"🔍 [路由层] 检查上传后的字幕文件")
        print(f"   文件路径: {subtitle_path}")
        print(f"   文件大小: {subtitle_path.stat().st_size} 字节")
        try:
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                debug_content = f.read()
            import re
            # 更新正则表达式以匹配有空格和没有空格的情况
            debug_count = len(re.findall(r'\[spk\d+\]\s*:', debug_content))
            print(f"   说话人标识数量（路由层检测）: {debug_count}")
            if debug_count > 0:
                debug_samples = re.findall(r'\[spk\d+\]:[^\n]*', debug_content)[:2]
                print(f"   示例:")
                for sample in debug_samples:
                    print(f"      {sample}")
            else:
                # 显示前几行内容
                lines = debug_content.split('\n')[:10]
                print(f"   前10行内容:")
                for i, line in enumerate(lines, 1):
                    if line.strip():
                        print(f"      {i}: {line[:80]}")
        except Exception as e:
            print(f"   ⚠️ 读取文件失败: {e}")
        
        # 生成输出文件路径
        output_filename = f"{timestamp}_with_clean_subtitles.mp4"
        output_path = pathlib.Path(get_output_dir()) / output_filename
        
        # 初始化任务状态
        video_merge_tasks = get_video_merge_tasks()
        video_merge_tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0,
            "output_path": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
            "font_settings": {
                "font_size": subtitle_font_size,
                "font_name": subtitle_font_name,
                "color": subtitle_color,
                "outline_color": subtitle_outline_color,
                "outline_width": subtitle_outline_width,
                "position": subtitle_position,
                "bold_weight": subtitle_bold_weight,
                "margin_v": subtitle_margin_v
            },
            "clean_speakers": clean_speakers
        }
        
        # 在后台线程中执行烧录
        def run_burn_clean_task():
            try:
                start_time = time.time()
                print(f"🎬 开始字幕烧录任务（清理说话人标识）: {task_id}")
                print(f"🧹 清理说话人标识设置: {clean_speakers}")
                
                # 更新进度
                video_merge_tasks[task_id]["progress"] = 30
                
                # 执行字幕烧录（带清理功能）
                result_path = video_merger.burn_subtitle_to_video_with_cleaning(
                    video_path=str(video_path),
                    subtitle_path=str(subtitle_path),
                    output_path=str(output_path),
                    subtitle_font_size=subtitle_font_size,
                    subtitle_font_name=subtitle_font_name,
                    subtitle_color=subtitle_color,
                    subtitle_outline_color=subtitle_outline_color,
                    subtitle_outline_width=subtitle_outline_width,
                    subtitle_position=subtitle_position,
                    subtitle_bold_weight=subtitle_bold_weight,
                    subtitle_margin_v=subtitle_margin_v,
                    clean_speakers=clean_speakers
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
                print(f"❌ 字幕烧录任务失败: {e}")
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
        thread = threading.Thread(target=run_burn_clean_task, daemon=True)
        thread.start()
        
        return {"task_id": task_id, "message": "字幕烧录任务已启动（支持说话人标识清理）"}
        
    except Exception as e:
        print(f"❌ 启动字幕烧录任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动字幕烧录任务失败: {str(e)}")


@router.get("/status/{task_id}", summary="获取字幕烧录任务状态")
async def get_burn_status(task_id: str):
    """获取字幕烧录任务的当前状态"""
    video_merge_tasks = get_video_merge_tasks()
    if task_id not in video_merge_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return video_merge_tasks[task_id]


@router.get("/download/{filename}", summary="下载烧录后的视频")
async def download_video_with_subtitles(filename: str):
    """下载烧录字幕后的视频文件"""
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


@router.get("/fonts", summary="获取可用字体列表")
async def get_available_fonts():
    """获取系统可用的字体列表"""
    # 常用字体列表
    common_fonts = [
        "Arial",
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Times New Roman",
        "Helvetica",
        "Verdana",
        "Tahoma",
        "Georgia",
        "Courier New"
    ]
    
    return {
        "fonts": common_fonts,
        "default": "Arial"
    }


@router.get("/colors", summary="获取可用颜色列表")
async def get_available_colors():
    """获取可用的字幕颜色列表"""
    colors = {
        "white": "白色",
        "black": "黑色", 
        "red": "红色",
        "green": "绿色",
        "blue": "蓝色",
        "yellow": "黄色",
        "cyan": "青色",
        "magenta": "洋红色",
        "gray": "灰色"
    }
    
    return {
        "colors": colors,
        "default": "white"
    }