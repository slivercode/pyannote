"""
文件管理路由模块
处理文件上传、下载和文件夹操作
"""
import os
import sys
import pathlib
import platform
import subprocess
from datetime import datetime
from typing import List
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from models.responses import AudioUploadResponse
from config.dependencies import get_current_dir, get_input_dir, get_output_dir

# 添加utils目录到路径
utils_dir = pathlib.Path(__file__).parent.parent / "utils"
if str(utils_dir) not in sys.path:
    sys.path.insert(0, str(utils_dir))

from path_utils import ensure_directory_exists, safe_file_write, is_path_writable

router = APIRouter(prefix="/api", tags=["文件管理"])
logger = logging.getLogger(__name__)


class OpenFolderRequest(BaseModel):
    folder_path: str


@router.post(
    "/upload-audio",
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
    4. 跨平台兼容（Windows/Linux/Mac）
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
    file_ext = pathlib.Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件后缀：{file_ext}，仅允许 .mp3/.wav/.flac/.mp4",
        )

    # 2. 处理文件名：添加时间戳（避免重名）+ 清理恶意路径
    safe_filename = os.path.basename(file.filename)
    # 防止路径遍历攻击（如"../etc/passwd"）
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")  # 时间戳：20240520123456
    saved_filename = (
        f"{timestamp}_{safe_filename}"  # 最终保存的文件名：20240520123456_test.mp3
    )

    # 3. 获取input目录并确保其存在且可写（跨平台）
    input_dir = pathlib.Path(get_input_dir())
    
    # 确保目录存在且可写
    if not ensure_directory_exists(input_dir):
        raise HTTPException(
            status_code=500, 
            detail=f"无法创建或访问input目录: {input_dir}，请检查权限"
        )
    
    if not is_path_writable(input_dir):
        raise HTTPException(
            status_code=500,
            detail=f"input目录不可写: {input_dir}，请检查权限"
        )
    
    # 4. 保存文件到 input 目录
    save_path = input_dir / saved_filename
    save_path_str = str(save_path)  # 本地完整路径（给前端/脚本参考）

    try:
        file_size = 0
        # 分块读取保存（避免大文件占用过多内存）
        with open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 每次读取1MB
                f.write(chunk)
                file_size += len(chunk)
        await file.close()  # 关闭文件流
        
        # 在Linux/Mac上设置文件权限
        if os.name != 'nt':
            try:
                os.chmod(save_path, 0o644)
            except Exception as e:
                logger.warning(f"设置文件权限失败: {e}")
        
        logger.info(f"文件上传成功: {save_path} ({file_size} bytes)")
        
    except Exception as e:
        logger.error(f"文件保存失败: {save_path}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")

    # 5. 构建HTTP访问URL（前端可直接拼接服务地址使用）
    access_url = f"/input/{saved_filename}"

    # 6. 返回上传结果
    return AudioUploadResponse(
        success=True,
        filename=saved_filename,
        save_path=save_path_str,
        access_url=access_url,
        file_size=file_size,
        message="音频文件上传成功",
    )


@router.post(
    "/upload-video",
    summary="上传音视频文件到input目录",
    response_model=AudioUploadResponse,
)
async def upload_video(
    file: UploadFile = File(..., description="音视频文件（支持mp4、avi、mov、mkv、wav、mp3、flac、aac、m4a、ogg格式）")
):
    """
    音视频上传规则：
    1. 支持视频格式：mp4/avi/mov/mkv
    2. 支持音频格式：wav/mp3/flac/aac/m4a/ogg
    3. 文件名自动添加时间戳（避免重名）
    4. 上传后自动保存到项目根目录的 input 文件夹
    5. 跨平台兼容（Windows/Linux/Mac）
    """
    # 1. 验证文件类型
    allowed_content_types = [
        # 视频格式
        "video/mp4",
        "video/x-msvideo",  # avi
        "video/quicktime",  # mov
        "video/x-matroska",  # mkv
        # 音频格式
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",  # mp3
        "audio/mp3",
        "audio/flac",
        "audio/x-flac",
        "audio/aac",
        "audio/x-m4a",
        "audio/mp4",  # m4a
        "audio/ogg",
        "audio/x-ogg",
    ]
    allowed_extensions = [
        # 视频格式
        ".mp4", ".avi", ".mov", ".mkv",
        # 音频格式
        ".wav", ".mp3", ".flac", ".aac", ".m4a", ".ogg"
    ]

    # 验证MIME类型（音视频类型可能不准确，主要依赖后缀）
    file_ext = pathlib.Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件后缀：{file_ext}，仅允许视频格式(.mp4/.avi/.mov/.mkv)或音频格式(.wav/.mp3/.flac/.aac/.m4a/.ogg)",
        )

    # 2. 处理文件名
    safe_filename = os.path.basename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    saved_filename = f"{timestamp}_{safe_filename}"

    # 3. 获取input目录并确保其存在且可写（跨平台）
    input_dir = pathlib.Path(get_input_dir())
    
    if not ensure_directory_exists(input_dir):
        raise HTTPException(
            status_code=500, 
            detail=f"无法创建或访问input目录: {input_dir}，请检查权限"
        )
    
    if not is_path_writable(input_dir):
        raise HTTPException(
            status_code=500,
            detail=f"input目录不可写: {input_dir}，请检查权限"
        )

    # 4. 保存文件
    save_path = input_dir / saved_filename
    save_path_str = str(save_path)

    try:
        file_size = 0
        with open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
                file_size += len(chunk)
        await file.close()
        
        # 在Linux/Mac上设置文件权限
        if os.name != 'nt':
            try:
                os.chmod(save_path, 0o644)
            except Exception as e:
                logger.warning(f"设置文件权限失败: {e}")
        
        logger.info(f"文件上传成功: {save_path} ({file_size} bytes)")
        
    except Exception as e:
        logger.error(f"文件保存失败: {save_path}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")

    access_url = f"/input/{saved_filename}"

    # 判断文件类型
    video_extensions = [".mp4", ".avi", ".mov", ".mkv"]
    audio_extensions = [".wav", ".mp3", ".flac", ".aac", ".m4a", ".ogg"]
    
    if file_ext in video_extensions:
        file_type = "视频"
    elif file_ext in audio_extensions:
        file_type = "音频"
    else:
        file_type = "媒体"
    
    return AudioUploadResponse(
        success=True,
        filename=saved_filename,
        save_path=save_path_str,
        access_url=access_url,
        file_size=file_size,
        message=f"{file_type}文件上传成功",
    )


@router.post(
    "/upload-srt",
    summary="上传SRT字幕文件到input目录",
    response_model=AudioUploadResponse,
)
async def upload_srt(
    file: UploadFile = File(..., description="SRT字幕文件")
):
    """
    SRT字幕上传规则：
    1. 仅支持 .srt 格式
    2. 文件名自动添加时间戳（避免重名）
    3. 上传后自动保存到项目根目录的 input 文件夹
    4. 跨平台兼容（Windows/Linux/Mac）
    """
    # 1. 验证文件类型
    file_ext = pathlib.Path(file.filename).suffix.lower()
    if file_ext != ".srt":
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件后缀：{file_ext}，仅允许 .srt",
        )

    # 2. 处理文件名
    safe_filename = os.path.basename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    saved_filename = f"{timestamp}_{safe_filename}"

    # 3. 获取input目录并确保其存在且可写（跨平台）
    input_dir = pathlib.Path(get_input_dir())
    
    if not ensure_directory_exists(input_dir):
        raise HTTPException(
            status_code=500, 
            detail=f"无法创建或访问input目录: {input_dir}，请检查权限"
        )
    
    if not is_path_writable(input_dir):
        raise HTTPException(
            status_code=500,
            detail=f"input目录不可写: {input_dir}，请检查权限"
        )

    # 4. 保存文件
    save_path = input_dir / saved_filename
    save_path_str = str(save_path)

    try:
        file_size = 0
        with open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
                file_size += len(chunk)
        await file.close()
        
        # 在Linux/Mac上设置文件权限
        if os.name != 'nt':
            try:
                os.chmod(save_path, 0o644)
            except Exception as e:
                logger.warning(f"设置文件权限失败: {e}")
        
        logger.info(f"文件上传成功: {save_path} ({file_size} bytes)")
        
    except Exception as e:
        logger.error(f"文件保存失败: {save_path}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")

    access_url = f"/input/{saved_filename}"

    return AudioUploadResponse(
        success=True,
        filename=saved_filename,
        save_path=save_path_str,
        access_url=access_url,
        file_size=file_size,
        message="SRT字幕文件上传成功",
    )


@router.post("/open-folder")
async def open_folder(req: OpenFolderRequest):
    """打开指定文件夹"""
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