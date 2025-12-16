"""
快速集成示例 - 将 pyvideotrans 对齐算法应用到 pyannote-audio
这是一个最小化的集成示例，展示如何快速使用对齐算法
"""

import sys
from pathlib import Path

# 添加 pyvideotrans 到 Python 路径
pyvideotrans_path = Path(__file__).parent.parent.parent.parent.parent / 'pyvideotrans-main'
sys.path.insert(0, str(pyvideotrans_path))

# 导入 pyvideotrans 的 SpeedRate 类
from videotrans.task._rate import SpeedRate


class PyannoteSpeedRateAdapter:
    """
    适配器类 - 将 pyvideotrans 的 SpeedRate 适配到 pyannote 项目
    """
    
    def __init__(self, output_dir='./output'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def align_audio_with_subtitles(
        self,
        subtitles: list,
        audio_files: list,
        enable_audio_speedup: bool = True,
        enable_video_slowdown: bool = False,
        video_file: str = None,
        max_audio_speed_rate: float = 2.0,
        max_video_pts_rate: float = 10.0
    ):
        """
        使用 pyvideotrans 的对齐算法处理音频和字幕
        
        Args:
            subtitles: 字幕列表 [{'start_ms': int, 'end_ms': int, 'text': str}, ...]
            audio_files: 配音文件列表
            enable_audio_speedup: 是否启用音频加速
            enable_video_slowdown: 是否启用视频慢速
            video_file: 视频文件路径（如果需要视频慢速）
            max_audio_speed_rate: 最大音频加速倍率
            max_video_pts_rate: 最大视频慢速倍率
        
        Returns:
            (最终音频路径, 更新后的字幕列表)
        """
        
        # 转换字幕格式为 pyvideotrans 需要的格式
        queue_tts = self._convert_subtitles_format(subtitles, audio_files)
        
        # 计算原始视频总时长
        raw_total_time = queue_tts[-1]['end_time'] if queue_tts else 0
        
        # 输出音频路径
        target_audio = str(self.output_dir / 'final_audio.wav')
        
        # 创建 SpeedRate 实例
        rate_inst = SpeedRate(
            queue_tts=queue_tts,
            shoud_audiorate=enable_audio_speedup,
            shoud_videorate=enable_video_slowdown,
            uuid=None,
            novoice_mp4=video_file,
            raw_total_time=raw_total_time,
            target_audio=target_audio,
            cache_folder=str(self.output_dir / 'temp'),
            remove_silent_mid=False,
            align_sub_audio=True
        )
        
        # 手动设置最大倍率（覆盖配置文件）
        rate_inst.max_audio_speed_rate = max_audio_speed_rate
        rate_inst.max_video_pts_rate = max_video_pts_rate
        
        # 执行对齐处理
        updated_queue_tts = rate_inst.run()
        
        # 转换回 pyannote 格式
        updated_subtitles = self._convert_back_to_pyannote_format(updated_queue_tts)
        
        return target_audio, updated_subtitles
    
    def _convert_subtitles_format(self, subtitles, audio_files):
        """将 pyannote 格式转换为 pyvideotrans 格式"""
        queue_tts = []
        
        for i, subtitle in enumerate(subtitles):
            queue_tts.append({
                'line': i + 1,
                'start_time': subtitle['start_ms'],
                'end_time': subtitle['end_ms'],
                'text': subtitle.get('text', ''),
                'filename': audio_files[i] if i < len(audio_files) else None,
            })
        
        return queue_tts
    
    def _convert_back_to_pyannote_format(self, queue_tts):
        """将 pyvideotrans 格式转换回 pyannote 格式"""
        subtitles = []
        
        for item in queue_tts:
            subtitles.append({
                'start_ms': item['start_time'],
                'end_ms': item['end_time'],
                'text': item['text'],
                'audio_file': item.get('filename'),
            })
        
        return subtitles


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    # 示例1: 仅音频加速
    print("=" * 60)
    print("示例1: 仅音频加速")
    print("=" * 60)
    
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
        {'start_ms': 6000, 'end_ms': 8000, 'text': '第三句话'},
    ]
    
    audio_files = [
        'path/to/audio_001.wav',
        'path/to/audio_002.wav',
        'path/to/audio_003.wav',
    ]
    
    adapter = PyannoteSpeedRateAdapter(output_dir='./output_example1')
    
    try:
        final_audio, updated_subtitles = adapter.align_audio_with_subtitles(
            subtitles=subtitles,
            audio_files=audio_files,
            enable_audio_speedup=True,
            enable_video_slowdown=False,
            max_audio_speed_rate=2.0,
        )
        
        print(f"\n✅ 处理完成！")
        print(f"最终音频: {final_audio}")
        print(f"更新后的字幕:")
        for i, sub in enumerate(updated_subtitles):
            print(f"  {i+1}. {sub['start_ms']}ms - {sub['end_ms']}ms: {sub['text']}")
    
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
    
    
    # 示例2: 音频加速 + 视频慢速
    print("\n" + "=" * 60)
    print("示例2: 音频加速 + 视频慢速")
    print("=" * 60)
    
    adapter2 = PyannoteSpeedRateAdapter(output_dir='./output_example2')
    
    try:
        final_audio, updated_subtitles = adapter2.align_audio_with_subtitles(
            subtitles=subtitles,
            audio_files=audio_files,
            enable_audio_speedup=True,
            enable_video_slowdown=True,
            video_file='path/to/video.mp4',  # 提供视频文件
            max_audio_speed_rate=1.5,
            max_video_pts_rate=2.0,
        )
        
        print(f"\n✅ 处理完成！")
        print(f"最终音频: {final_audio}")
        print(f"处理后的视频: {adapter2.output_dir / 'temp' / 'novoice.mp4'}")
    
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
