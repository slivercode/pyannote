"""
时间轴动态调整器
根据实际生成的音频长度，动态调整字幕时间轴，同时保证总时长不变
"""

from typing import List, Dict
from pydub import AudioSegment
import os


class TimelineAdjuster:
    """
    时间轴动态调整器
    
    核心策略：
    1. 根据每段配音的实际长度调整字幕时间
    2. 保证 SRT 总时长不变（等于原始 SRT 总时长）
    3. 通过压缩/拉伸静音间隙来吸收时长差异
    """
    
    def __init__(self, subtitles: List[Dict], audio_files: List[str], preserve_total_time: bool = True):
        """
        初始化时间轴调整器
        
        Args:
            subtitles: 字幕列表 [{'start_ms': int, 'end_ms': int, 'text': str}, ...]
            audio_files: 配音文件列表
            preserve_total_time: 是否保持总时长不变
        """
        self.subtitles = subtitles
        self.audio_files = audio_files
        self.preserve_total_time = preserve_total_time
        
        # 计算原始总时长
        if subtitles:
            self.original_total_time = subtitles[-1]['end_ms']
        else:
            self.original_total_time = 0
    
    def adjust_timeline(self) -> List[Dict]:
        """
        动态调整时间轴
        
        策略：
        1. 第一遍：计算每段配音的实际时长
        2. 第二遍：计算总时长差异
        3. 第三遍：按比例分配时长差异到各个间隙
        
        Returns:
            更新后的字幕列表
        """
        print("\n" + "="*60)
        print("⏱️  开始动态调整时间轴")
        print("="*60)
        print(f"原始总时长: {self.original_total_time}ms")
        
        # 第一步：获取每段配音的实际时长
        actual_durations = []
        for i, (subtitle, audio_file) in enumerate(zip(self.subtitles, self.audio_files)):
            original_duration = subtitle['end_ms'] - subtitle['start_ms']
            actual_duration = self._get_audio_duration(audio_file)
            
            if actual_duration == 0:
                actual_duration = original_duration
            
            actual_durations.append(actual_duration)
            print(f"  字幕 {i+1}: 原时长={original_duration}ms, 实际配音={actual_duration}ms, "
                  f"差异={actual_duration - original_duration:+d}ms")
        
        # 第二步：计算总时长差异
        total_actual_duration = sum(actual_durations)
        time_diff = total_actual_duration - self.original_total_time
        
        print(f"\n总配音时长: {total_actual_duration}ms")
        print(f"时长差异: {time_diff:+d}ms")
        
        if not self.preserve_total_time:
            # 不需要保持总时长，直接按实际时长排列
            print("⚠️ 未启用保持总时长，直接按实际时长排列")
            return self._simple_timeline_adjustment(actual_durations)
        
        if abs(time_diff) < 100:
            # 差异很小（< 100ms = 0.1秒），直接按实际时长排列
            print(f"✅ 差异很小({time_diff:+d}ms < 100ms)，直接按实际时长排列")
            return self._simple_timeline_adjustment(actual_durations)
        
        # 第三步：需要调整时间轴以保持总时长
        if time_diff > 0:
            # 配音总时长超出原始时长，需要压缩间隙
            print(f"⚠️ 配音超出 {time_diff}ms，需要压缩静音间隙")
            return self._compress_timeline(actual_durations, time_diff)
        else:
            # 配音总时长小于原始时长，需要扩展间隙
            print(f"✅ 配音短于原始 {abs(time_diff)}ms，需要扩展静音间隙")
            return self._expand_timeline(actual_durations, abs(time_diff))
    
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
    
    def _simple_timeline_adjustment(self, actual_durations: List[int]) -> List[Dict]:
        """
        简单时间轴调整：直接按实际配音时长排列
        """
        current_time = 0
        updated_subtitles = []
        
        for i, (subtitle, duration) in enumerate(zip(self.subtitles, actual_durations)):
            # 保留原始字幕间隙
            if i == 0:
                gap_before = subtitle['start_ms']
            else:
                gap_before = subtitle['start_ms'] - self.subtitles[i-1]['end_ms']
            
            current_time += gap_before
            
            updated_subtitle = subtitle.copy()
            updated_subtitle['start_ms'] = current_time
            updated_subtitle['end_ms'] = current_time + duration
            updated_subtitles.append(updated_subtitle)
            
            current_time += duration
            
            print(f"  字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms")
        
        return updated_subtitles
    
    def _compress_timeline(self, actual_durations: List[int], excess_time: int) -> List[Dict]:
        """
        压缩时间轴：配音超出原始时长，需要压缩静音间隙
        
        策略：
        1. 首先尝试压缩静音间隙
        2. 如果间隙不足，则加速每段配音
        3. 确保最终总时长 = 原始总时长
        """
        # 计算原始间隙
        gaps = []
        for i in range(len(self.subtitles)):
            if i == 0:
                gap = self.subtitles[i]['start_ms']
            else:
                gap = self.subtitles[i]['start_ms'] - self.subtitles[i-1]['end_ms']
            gaps.append(max(0, gap))
        
        total_gap = sum(gaps)
        print(f"  原始间隙总时长: {total_gap}ms")
        print(f"  需要压缩: {excess_time}ms")
        
        if total_gap >= excess_time:
            # 间隙足够，按比例压缩
            print(f"  ✅ 间隙足够，按比例压缩")
            compression_ratio = (total_gap - excess_time) / total_gap if total_gap > 0 else 0
            compressed_gaps = [int(gap * compression_ratio) for gap in gaps]
            adjusted_durations = actual_durations  # 不需要加速配音
        else:
            # 间隙不足，需要加速配音
            remaining_excess = excess_time - total_gap
            print(f"  ⚠️ 间隙不足，移除所有间隙后仍超出 {remaining_excess}ms")
            print(f"  🚀 需要加速配音以压缩 {remaining_excess}ms")
            
            compressed_gaps = [0] * len(gaps)  # 移除所有间隙
            
            # 计算需要的加速倍率
            total_audio_duration = sum(actual_durations)
            target_audio_duration = total_audio_duration - remaining_excess
            speedup_ratio = total_audio_duration / target_audio_duration
            
            print(f"  📊 配音总时长: {total_audio_duration}ms")
            print(f"  📊 目标时长: {target_audio_duration}ms")
            print(f"  📊 加速倍率: {speedup_ratio:.2f}x")
            
            # 按比例加速每段配音
            adjusted_durations = [int(duration / speedup_ratio) for duration in actual_durations]
        
        # 重新计算时间轴
        current_time = 0
        updated_subtitles = []
        
        for i, (subtitle, duration, gap) in enumerate(zip(self.subtitles, adjusted_durations, compressed_gaps)):
            current_time += gap
            
            updated_subtitle = subtitle.copy()
            updated_subtitle['start_ms'] = current_time
            updated_subtitle['end_ms'] = current_time + duration
            updated_subtitle['original_duration_ms'] = actual_durations[i]  # 保存原始时长
            updated_subtitle['adjusted_duration_ms'] = duration  # 保存调整后时长
            updated_subtitles.append(updated_subtitle)
            
            current_time += duration
            
            if actual_durations[i] != duration:
                print(f"  字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                      f"(原时长: {actual_durations[i]}ms, 加速后: {duration}ms)")
            else:
                print(f"  字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                      f"(间隙: {gap}ms)")
        
        final_time = current_time
        print(f"\n  最终总时长: {final_time}ms (目标: {self.original_total_time}ms)")
        print(f"  误差: {final_time - self.original_total_time:+d}ms")
        
        return updated_subtitles
    
    def _expand_timeline(self, actual_durations: List[int], shortage_time: int) -> List[Dict]:
        """
        扩展时间轴：配音短于原始时长，需要扩展静音间隙
        
        策略：
        1. 计算所有静音间隙的总时长
        2. 按比例扩展每个间隙
        3. 确保最终总时长等于原始总时长
        """
        # 计算原始间隙
        gaps = []
        for i in range(len(self.subtitles)):
            if i == 0:
                gap = self.subtitles[i]['start_ms']
            else:
                gap = self.subtitles[i]['start_ms'] - self.subtitles[i-1]['end_ms']
            gaps.append(max(0, gap))
        
        total_gap = sum(gaps)
        print(f"  原始间隙总时长: {total_gap}ms")
        
        # 按比例扩展间隙
        if total_gap > 0:
            expansion_ratio = (total_gap + shortage_time) / total_gap
            expanded_gaps = [int(gap * expansion_ratio) for gap in gaps]
        else:
            # 没有间隙，平均分配到每个字幕后
            avg_gap = shortage_time // len(self.subtitles)
            expanded_gaps = [avg_gap] * len(self.subtitles)
        
        print(f"  ✅ 扩展间隙，增加 {shortage_time}ms")
        
        # 重新计算时间轴
        current_time = 0
        updated_subtitles = []
        
        for i, (subtitle, duration, gap) in enumerate(zip(self.subtitles, actual_durations, expanded_gaps)):
            current_time += gap
            
            updated_subtitle = subtitle.copy()
            updated_subtitle['start_ms'] = current_time
            updated_subtitle['end_ms'] = current_time + duration
            updated_subtitles.append(updated_subtitle)
            
            current_time += duration
            
            print(f"  字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                  f"(间隙: {gap}ms)")
        
        final_time = current_time
        print(f"\n  最终总时长: {final_time}ms (目标: {self.original_total_time}ms)")
        
        return updated_subtitles


# 使用示例
if __name__ == "__main__":
    # 测试数据
    subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
        {'start_ms': 6000, 'end_ms': 8000, 'text': '第三句话'},
    ]
    
    audio_files = ['audio_001.wav', 'audio_002.wav', 'audio_003.wav']
    
    adjuster = TimelineAdjuster(subtitles, audio_files, preserve_total_time=True)
    updated_subtitles = adjuster.adjust_timeline()
    
    print("\n更新后的字幕:")
    for i, sub in enumerate(updated_subtitles):
        print(f"  {i+1}. {sub['start_ms']}ms - {sub['end_ms']}ms: {sub['text']}")
