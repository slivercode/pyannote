"""
简单时间轴构建器
根据实际配音时长，从指定偏移开始顺序构建时间轴
"""

import os
from typing import List, Dict
from pydub import AudioSegment
from pathlib import Path


class SimpleTimelineBuilder:
    """
    简单时间轴构建器
    
    核心逻辑：
    1. 从指定偏移开始（如 00:00:07,000）
    2. 每句结束 = 上一句结束 + 本句实际配音时长
    3. 如果超出原视频总时长，自动加速音频
    4. 导出调整后的SRT文件
    """
    
    def __init__(self, 
                 subtitles: List[Dict],
                 audio_files: List[str],
                 start_offset_ms: int = 0,
                 max_total_time_ms: int = 0,
                 max_speedup_rate: float = 2.0):
        """
        初始化时间轴构建器
        
        Args:
            subtitles: 原始字幕列表 [{'text': str}, ...]
            audio_files: 配音文件列表（与字幕对应）
            start_offset_ms: 起始偏移（毫秒），如 7000 表示从 00:00:07,000 开始
            max_total_time_ms: 最大总时长（毫秒），如果为0则不限制
            max_speedup_rate: 最大加速倍率（当超出总时长时使用）
        """
        self.subtitles = subtitles
        self.audio_files = audio_files
        self.start_offset_ms = start_offset_ms
        self.max_total_time_ms = max_total_time_ms
        self.max_speedup_rate = max_speedup_rate
        
        print(f"\n{'='*60}")
        print(f"📐 简单时间轴构建器初始化")
        print(f"{'='*60}")
        print(f"起始偏移: {self._ms_to_srt_time(start_offset_ms)}")
        print(f"最大总时长: {self._ms_to_srt_time(max_total_time_ms) if max_total_time_ms > 0 else '不限制'}")
        print(f"最大加速倍率: {max_speedup_rate}x")
        print(f"字幕数量: {len(subtitles)}")
        print(f"配音文件数量: {len(audio_files)}")
    
    def _get_audio_duration(self, audio_file: str) -> int:
        """获取音频文件时长（毫秒）"""
        if not audio_file or not os.path.exists(audio_file):
            return 0
        try:
            audio = AudioSegment.from_file(audio_file)
            return len(audio)
        except Exception as e:
            print(f"  ⚠️ 获取音频时长失败 {audio_file}: {e}")
            return 0
    
    def _ms_to_srt_time(self, ms: int) -> str:
        """将毫秒转换为SRT时间格式"""
        hours = int(ms // 3600000)
        minutes = int((ms % 3600000) // 60000)
        seconds = int((ms % 60000) // 1000)
        milliseconds = int(ms % 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def build_timeline(self) -> List[Dict]:
        """
        构建新的时间轴
        
        Returns:
            更新后的字幕列表 [{'start_ms': int, 'end_ms': int, 'text': str, 'audio_file': str}, ...]
        """
        print(f"\n{'='*60}")
        print(f"⏱️  开始构建时间轴")
        print(f"{'='*60}")
        
        # 第一步：获取每段配音的实际时长
        actual_durations = []
        for i, (subtitle, audio_file) in enumerate(zip(self.subtitles, self.audio_files)):
            duration = self._get_audio_duration(audio_file)
            if duration == 0:
                # 如果获取失败，使用默认时长（2秒）
                duration = 2000
                print(f"  ⚠️ 字幕 {i+1}: 无法获取配音时长，使用默认 2000ms")
            else:
                print(f"  ✅ 字幕 {i+1}: 配音时长 = {duration}ms")
            
            actual_durations.append(duration)
        
        # 第二步：计算总时长
        total_duration = sum(actual_durations)
        available_time = self.max_total_time_ms - self.start_offset_ms if self.max_total_time_ms > 0 else total_duration
        
        print(f"\n📊 时长统计:")
        print(f"   配音总时长: {total_duration}ms ({total_duration/1000:.1f}秒)")
        print(f"   起始偏移: {self.start_offset_ms}ms")
        print(f"   可用时长: {available_time}ms ({available_time/1000:.1f}秒)")
        
        # 第三步：判断是否需要加速
        need_speedup = False
        speedup_ratio = 1.0
        
        if self.max_total_time_ms > 0 and total_duration > available_time:
            speedup_ratio = total_duration / available_time
            if speedup_ratio > self.max_speedup_rate:
                speedup_ratio = self.max_speedup_rate
                print(f"   ⚠️ 需要加速 {speedup_ratio:.2f}x（已限制到最大倍率）")
            else:
                print(f"   ⚠️ 需要加速 {speedup_ratio:.2f}x")
            need_speedup = True
        else:
            print(f"   ✅ 无需加速")
        
        # 第四步：构建时间轴
        updated_subtitles = []
        current_time = self.start_offset_ms
        
        print(f"\n📝 构建时间轴:")
        
        for i, (subtitle, duration) in enumerate(zip(self.subtitles, actual_durations)):
            # 如果需要加速，调整时长
            if need_speedup:
                adjusted_duration = int(duration / speedup_ratio)
            else:
                adjusted_duration = duration
            
            # 构建新的字幕条目
            updated_subtitle = {
                'start_ms': current_time,
                'end_ms': current_time + adjusted_duration,
                'text': subtitle.get('text', ''),
                'audio_file': self.audio_files[i],
                'original_duration_ms': duration,
                'adjusted_duration_ms': adjusted_duration,
                'speaker': subtitle.get('speaker', None)
            }
            
            updated_subtitles.append(updated_subtitle)
            
            print(f"  字幕 {i+1}: {self._ms_to_srt_time(current_time)} --> {self._ms_to_srt_time(current_time + adjusted_duration)}")
            if need_speedup:
                print(f"          (原时长: {duration}ms, 加速后: {adjusted_duration}ms)")
            
            current_time += adjusted_duration
        
        # 第五步：验证总时长
        final_time = current_time
        print(f"\n📊 最终统计:")
        print(f"   最终总时长: {final_time}ms ({final_time/1000:.1f}秒)")
        print(f"   最后一句结束: {self._ms_to_srt_time(final_time)}")
        
        if self.max_total_time_ms > 0:
            if final_time <= self.max_total_time_ms:
                print(f"   ✅ 未超出限制 ({self.max_total_time_ms}ms)")
            else:
                print(f"   ⚠️ 超出限制 {final_time - self.max_total_time_ms}ms")
        
        return updated_subtitles
    
    def save_srt(self, updated_subtitles: List[Dict], output_path: str):
        """
        保存调整后的SRT文件
        
        Args:
            updated_subtitles: 更新后的字幕列表
            output_path: 输出文件路径
        """
        print(f"\n💾 保存调整后的SRT文件: {output_path}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, subtitle in enumerate(updated_subtitles):
                f.write(f"{i+1}\n")
                
                start_time = self._ms_to_srt_time(subtitle['start_ms'])
                end_time = self._ms_to_srt_time(subtitle['end_ms'])
                
                f.write(f"{start_time} --> {end_time}\n")
                
                # 如果有说话人信息，添加到文本前
                text = subtitle['text']
                if subtitle.get('speaker'):
                    text = f"[{subtitle['speaker']}] {text}"
                
                f.write(f"{text}\n\n")
        
        print(f"✅ SRT文件保存成功")


# 使用示例
if __name__ == "__main__":
    # 测试数据
    subtitles = [
        {'text': '第一句话'},
        {'text': '第二句话'},
        {'text': '第三句话'},
    ]
    
    audio_files = ['audio_001.wav', 'audio_002.wav', 'audio_003.wav']
    
    # 创建构建器
    builder = SimpleTimelineBuilder(
        subtitles=subtitles,
        audio_files=audio_files,
        start_offset_ms=7000,  # 从 00:00:07,000 开始
        max_total_time_ms=120000,  # 最大2分钟
        max_speedup_rate=2.0
    )
    
    # 构建时间轴
    updated_subtitles = builder.build_timeline()
    
    # 保存SRT
    builder.save_srt(updated_subtitles, 'output_adjusted.srt')
    
    print("\n更新后的字幕:")
    for i, sub in enumerate(updated_subtitles):
        print(f"  {i+1}. {sub['start_ms']}ms - {sub['end_ms']}ms: {sub['text']}")
