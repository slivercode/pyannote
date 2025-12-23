"""
响应模型定义
包含API返回给前端的数据结构
"""
from typing import Optional
from pydantic import BaseModel


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