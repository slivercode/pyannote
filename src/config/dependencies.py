"""
依赖注入配置模块
提供全局配置和依赖项的访问接口
"""
import threading
from pathlib import Path
from typing import Dict, Any, Optional

# 全局配置存储
_config: Dict[str, Any] = {}


def init_config(
    current_dir: Path,
    input_dir: Path,
    output_dir: Path,
    scripts_dir: Path,
    tasks: Dict,
    task_lock: threading.Lock,
    video_merger: Optional[Any],
    video_merge_tasks: Dict,
    tts_dubbing_tasks: Dict
) -> None:
    """初始化全局配置"""
    global _config
    _config.update({
        "current_dir": current_dir,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "scripts_dir": scripts_dir,
        "tasks": tasks,
        "task_lock": task_lock,
        "video_merger": video_merger,
        "video_merge_tasks": video_merge_tasks,
        "tts_dubbing_tasks": tts_dubbing_tasks
    })


# 依赖注入函数
def get_current_dir() -> Path:
    """获取当前项目目录"""
    return _config["current_dir"]


def get_input_dir() -> Path:
    """获取输入目录"""
    return _config["input_dir"]


def get_output_dir() -> Path:
    """获取输出目录"""
    return _config["output_dir"]


def get_scripts_dir() -> Path:
    """获取脚本目录"""
    return _config["scripts_dir"]


def get_tasks() -> Dict:
    """获取任务字典"""
    return _config["tasks"]


def get_task_lock() -> threading.Lock:
    """获取任务锁"""
    return _config["task_lock"]


def get_video_merger() -> Optional[Any]:
    """获取视频合并器"""
    return _config["video_merger"]


def get_video_merge_tasks() -> Dict:
    """获取视频合并任务字典"""
    return _config["video_merge_tasks"]


def get_tts_dubbing_tasks() -> Dict:
    """获取TTS配音任务字典"""
    return _config["tts_dubbing_tasks"]