"""
OCR 字幕提取相关的数据模型
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class SubtitleRegion(BaseModel):
    """字幕区域坐标"""
    x: int
    y: int
    width: int
    height: int
    name: str = "自定义区域"  # 区域名称


class OCRConfig(BaseModel):
    """OCR 配置参数"""
    language: str = "ch"  # 识别语言
    mode: str = "auto"  # 识别模式: fast, auto, precise
    use_gpu: bool = True  # 是否使用GPU加速
    confidence_threshold: float = 0.3  # 置信度阈值（降低以提高召回率）
    remove_duplicates: bool = True  # 是否去除重复字幕
    filter_watermark: bool = False  # 是否过滤水印（默认关闭，避免误判）
    # frame_interval 已移除 - 现在基于视频FPS动态提取帧，而不是固定间隔


class SubtitleItem(BaseModel):
    """单条字幕项"""
    start_time: float  # 开始时间（秒）
    end_time: float  # 结束时间（秒）
    text: str  # 字幕文本
    confidence: float  # 识别置信度
    is_watermark: bool = False  # 是否为水印
    frame_index: int  # 对应的帧索引


class OCRProgress(BaseModel):
    """OCR 处理进度"""
    stage: str  # 当前阶段: extracting, recognizing, processing
    progress: float  # 进度百分比 0-100
    current_frame: int  # 当前处理帧
    total_frames: int  # 总帧数
    message: str  # 状态消息
    estimated_time: Optional[float] = None  # 预估剩余时间


class OCRResult(BaseModel):
    """OCR 提取结果"""
    video_file: str  # 视频文件名
    subtitles: List[SubtitleItem]  # 提取的字幕列表
    total_duration: float  # 视频总时长
    processing_time: float  # 处理耗时
    accuracy_score: Optional[float] = None  # 识别准确率评估


class VideoInfo(BaseModel):
    """视频文件信息"""
    filename: str
    duration: float  # 时长（秒）
    width: int  # 宽度
    height: int  # 高度
    fps: float  # 帧率
    size: int  # 文件大小（字节）
    format: str  # 视频格式


class OCRTaskRequest(BaseModel):
    """OCR 任务请求"""
    video_file: str  # 视频文件路径
    config: OCRConfig  # OCR 配置
    subtitle_region: Optional[SubtitleRegion] = None  # 字幕区域


class OCRTaskResponse(BaseModel):
    """OCR 任务响应"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: OCRProgress
    result: Optional[OCRResult] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class BatchOCRRequest(BaseModel):
    """批量OCR处理请求"""
    video_files: List[str]
    config: OCRConfig
    subtitle_region: Optional[SubtitleRegion] = None


class SystemResourceInfo(BaseModel):
    """系统资源信息"""
    cpu_usage: float  # CPU使用率
    memory_usage: float  # 内存使用率
    gpu_available: bool  # GPU是否可用
    gpu_memory_usage: Optional[float] = None  # GPU内存使用率
    disk_space: float  # 可用磁盘空间（GB）