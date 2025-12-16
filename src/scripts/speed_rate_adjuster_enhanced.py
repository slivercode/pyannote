"""
增强版双重变速机制 - 完整移植 pyvideotrans 的 SpeedRate 算法
新增功能：
1. 视频慢速处理（视频片段切割和PTS调整）
2. 视频拼接（无损concat）
3. 物理时间轴模型（基于视频真实时长）
4. 多线程并行处理
5. 完整的边界情况处理
"""

import os
import subprocess
import threading
import time
import json
import shutil
from pathlib import Path
from pydub import AudioSegment
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import math


class SpeedRateAdjusterEnhanced:
    """
    增强版双重变速机制处理器
    完整实现 pyvideotrans 的 SpeedRate 算法
    """
    
    # 常量配置
    MIN_CLIP_DURATION_MS = 40
    AUDIO_SAMPLE_RATE = 44100
    AUDIO_CHANNELS = 2
    BEST_AUDIO_RATE = 1.3
    
    def __init__(
        self,
        subtitles: List[Dict],
        audio_files: List[str],
        output_dir: str,
        video_file: Optional[str] = None,
        enable_audio_speedup: bool = True,
        enable_video_slowdown: bool = False,
        max_audio_speed_rate: float = 100.0,
        max_video_pts_rate: float = 10.0,
        remove_silent_gaps: bool = False,
        align_subtitle_audio: bool = True,
        raw_total_time_ms: int = 0,
        video_fps: int = 30,
        crf: str = "20",
        preset: str = "fast"
    ):
