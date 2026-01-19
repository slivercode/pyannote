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
    4. 限制语速不超过最大值，必要时调整时间轴
    """
    
    def __init__(self, subtitles: List[Dict], audio_files: List[str], preserve_total_time: bool = True, 
                 target_speed_factor: float = 1.0, max_speed_limit: float = 2.0):
        """
        初始化时间轴调整器
        
        Args:
            subtitles: 字幕列表 [{'start_ms': int, 'end_ms': int, 'text': str}, ...]
            audio_files: 配音文件列表
            preserve_total_time: 是否保持总时长不变
            target_speed_factor: 目标语速系数（用户设定的语速）
            max_speed_limit: 最大语速限制（默认2.0x）
        """
        self.subtitles = subtitles
        self.audio_files = audio_files
        self.preserve_total_time = preserve_total_time
        self.target_speed_factor = target_speed_factor
        self.max_speed_limit = max_speed_limit
        
        # 计算原始总时长
        if subtitles:
            self.original_total_time = subtitles[-1]['end_ms']
        else:
            self.original_total_time = 0
    
    def adjust_timeline(self) -> List[Dict]:
        """
        动态调整时间轴（修复版）
        
        核心修复：
        1. 正确计算时长差异（音频总时长 vs 原始字幕总时长，不含间隙）
        2. 只有当 (音频+原始间隙) > 原始SRT总时长 时才压缩间隙
        3. 音频时长准确时，保持原始间隙不变
        
        Returns:
            更新后的字幕列表
        """
        print("\n" + "="*60)
        print("⏱️  开始动态调整时间轴（修复版）")
        print("="*60)
        print(f"原始SRT总时长: {self.original_total_time}ms ({self.original_total_time/1000:.1f}秒)")
        print(f"TTS生成语速: {self.target_speed_factor}x")
        
        # 第一步：获取每段配音的实际时长
        actual_durations = []
        
        for i, (subtitle, audio_file) in enumerate(zip(self.subtitles, self.audio_files)):
            original_duration = subtitle['end_ms'] - subtitle['start_ms']
            actual_duration = self._get_audio_duration(audio_file)
            
            if actual_duration == 0:
                actual_duration = original_duration
            
            actual_durations.append(actual_duration)
            
            if i < 5:  # 只显示前5条
                print(f"  字幕 {i+1}: 原时长={original_duration}ms, TTS配音={actual_duration}ms, "
                      f"差异={actual_duration - original_duration:+d}ms")
        
        if len(actual_durations) > 5:
            print(f"  ... (省略 {len(actual_durations) - 5} 条)")
        
        # 第二步：计算总时长（关键修复：分别计算音频总时长和原始字幕总时长）
        total_audio_duration = sum(actual_durations)
        
        # 计算原始字幕总时长（不包含间隙）
        original_subtitle_duration = sum(s['end_ms'] - s['start_ms'] for s in self.subtitles)
        
        # 关键：时长差异应该是音频总时长 vs 原始字幕总时长（都不含间隙）
        audio_time_diff = total_audio_duration - original_subtitle_duration
        
        print(f"\n📊 时长分析:")
        print(f"  原始字幕总时长（不含间隙）: {original_subtitle_duration}ms ({original_subtitle_duration/1000:.1f}秒)")
        print(f"  TTS音频总时长: {total_audio_duration}ms ({total_audio_duration/1000:.1f}秒)")
        print(f"  音频时长差异: {audio_time_diff:+d}ms ({audio_time_diff/1000:+.1f}秒)")
        print(f"  原始SRT总时长（含间隙）: {self.original_total_time}ms ({self.original_total_time/1000:.1f}秒)")
        
        # 计算原始间隙
        gaps = []
        for i in range(len(self.subtitles)):
            if i == 0:
                gap = self.subtitles[i]['start_ms']
            else:
                gap = self.subtitles[i]['start_ms'] - self.subtitles[i-1]['end_ms']
            gaps.append(max(0, gap))
        
        total_gap = sum(gaps)
        print(f"  原始间隙总时长: {total_gap}ms ({total_gap/1000:.1f}秒)")
        
        # 第三步：判断处理策略
        if not self.preserve_total_time:
            # 不需要保持总时长，直接按配音时长排列，保留原始间隙
            print("\n✅ 未启用保持总时长，直接按配音时长排列（保留原始间隙）")
            return self._simple_timeline_adjustment_no_gaps(actual_durations)
        
        # 关键修复：判断是否需要压缩间隙
        # 只有当音频总时长 + 原始间隙 > 原始SRT总时长时，才需要压缩
        projected_total_time = total_audio_duration + total_gap
        total_time_diff = projected_total_time - self.original_total_time
        
        print(f"  预计总时长（音频+原始间隙）: {projected_total_time}ms ({projected_total_time/1000:.1f}秒)")
        print(f"  与原始SRT差异: {total_time_diff:+d}ms ({total_time_diff/1000:+.1f}秒)")
        
        if abs(total_time_diff) < 100:
            # 差异很小（< 100ms），直接保留原始间隙
            print(f"\n✅ 差异很小({total_time_diff:+d}ms < 100ms)，保留原始间隙")
            return self._simple_timeline_adjustment_no_gaps(actual_durations)
        
        if total_time_diff < 0:
            # 音频总时长 + 原始间隙 < 原始SRT总时长
            # 说明音频变短了，可以保留原始间隙，总时长自然缩短
            print(f"\n✅ 音频总时长缩短，保留原始间隙，总时长自然缩短")
            return self._simple_timeline_adjustment_no_gaps(actual_durations)
        
        # 只有这种情况才需要压缩间隙：
        # 音频总时长 + 原始间隙 > 原始SRT总时长
        print(f"\n⚠️ 音频总时长+原始间隙超出原始SRT {total_time_diff}ms ({total_time_diff/1000:.1f}秒)")
        print(f"   策略：优先压缩间隙 → 必要时轻微加速（保持清晰）")
        
        # 检查间隙是否足够压缩
        if total_gap >= total_time_diff:
            # 间隙足够，只压缩间隙
            print(f"   ✅ 间隙足够（{total_gap}ms >= {total_time_diff}ms），只压缩间隙")
            return self._compress_gaps_only(actual_durations, gaps, total_time_diff)
        else:
            # 间隙不足，需要同时压缩间隙和加速音频
            print(f"   ⚠️ 间隙不足（{total_gap}ms < {total_time_diff}ms），需要同时压缩间隙和加速音频")
            return self._compress_gaps_and_speedup(actual_durations, gaps, total_time_diff)
    
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
    
    def _simple_timeline_adjustment_no_gaps(self, durations: List[int]) -> List[Dict]:
        """
        简单时间轴调整：使用累积时间，保持原始间隔不变
        
        策略：
        1. 计算每条字幕前的原始间隔
        2. 使用累积时间 + 原始间隔计算新的开始时间
        3. 根据实际配音时长设置结束时间
        4. 确保间隔保持不变，总时长自然变化
        """
        updated_subtitles = []
        current_time = 0  # 使用累积时间
        
        print(f"\n  🔗 使用累积时间，保持原始间隔不变:")
        
        for i, (subtitle, duration) in enumerate(zip(self.subtitles, durations)):
            # 计算原始间隔
            if i == 0:
                original_gap = subtitle['start_ms']  # 第一条字幕前的空白
            else:
                original_gap = subtitle['start_ms'] - self.subtitles[i-1]['end_ms']
            
            # 添加原始间隔
            current_time += original_gap
            
            # 设置新的时间轴
            updated_subtitle = subtitle.copy()
            updated_subtitle['start_ms'] = current_time  # 使用累积时间
            updated_subtitle['end_ms'] = current_time + duration  # 使用实际配音时长
            
            original_duration = subtitle['end_ms'] - subtitle['start_ms']
            
            # 输出日志
            if i > 0:
                print(f"    字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                      f"(间隔: {original_gap}ms, 配音: {duration}ms)")
            else:
                print(f"    字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                      f"(配音: {duration}ms)")
            
            updated_subtitles.append(updated_subtitle)
            
            # 移动到下一个位置
            current_time += duration
        
        # 计算最终总时长
        final_time = updated_subtitles[-1]['end_ms'] if updated_subtitles else 0
        time_diff = final_time - self.original_total_time
        
        print(f"\n  📊 时间轴调整完成:")
        print(f"    原始总时长: {self.original_total_time}ms ({self.original_total_time/1000:.1f}秒)")
        print(f"    实际总时长: {final_time}ms ({final_time/1000:.1f}秒)")
        print(f"    时长差异: {time_diff:+d}ms ({time_diff/1000:+.1f}秒)")
        
        if abs(time_diff) <= 100:
            print(f"    ✅ 总时长基本一致（误差 ≤ 0.1秒）")
        elif time_diff < 0:
            print(f"    ✅ 总时长缩短 {abs(time_diff)}ms（配音加速所致）")
        else:
            print(f"    ⚠️ 总时长延长 {time_diff}ms（配音减速或超时所致）")
        
        return updated_subtitles
    
    def _compress_timeline(self, actual_durations: List[int], excess_time: int) -> List[Dict]:
        """
        压缩时间轴：配音超出原始时长，需要压缩静音间隙
        
        策略：
        1. 首先尝试压缩静音间隙
        2. 如果间隙不足，则加速每段配音（限制最大语速）
        3. 如果加速仍不足，则适当延长总时长
        4. 确保语速不超过最大限制
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
        print(f"  最大语速限制: {self.max_speed_limit}x")
        
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
            required_speedup_ratio = total_audio_duration / target_audio_duration
            
            print(f"  📊 配音总时长: {total_audio_duration}ms")
            print(f"  📊 目标时长: {target_audio_duration}ms")
            print(f"  📊 需要加速倍率: {required_speedup_ratio:.2f}x")
            
            # 检查是否超过最大语速限制
            if required_speedup_ratio > self.max_speed_limit:
                print(f"  ⚠️ 需要的加速倍率({required_speedup_ratio:.2f}x)超过限制({self.max_speed_limit}x)")
                
                # 使用最大允许的语速
                actual_speedup_ratio = self.max_speed_limit
                adjusted_durations = [int(duration / actual_speedup_ratio) for duration in actual_durations]
                
                # 计算使用最大语速后的实际压缩量
                actual_compressed_time = total_audio_duration - sum(adjusted_durations)
                still_excess = remaining_excess - actual_compressed_time
                
                print(f"  🔧 使用最大语速({actual_speedup_ratio}x)，实际压缩: {actual_compressed_time}ms")
                print(f"  📊 仍然超出: {still_excess}ms")
                
                if still_excess > 0:
                    if self.preserve_total_time:
                        print(f"  ⚠️ 即使使用最大语速仍无法完全压缩，将适当延长总时长")
                        # 记录需要延长的时间，用于后续处理
                        self._timeline_extension_needed = still_excess
                    else:
                        print(f"  ✅ 非保持总时长模式，允许延长 {still_excess}ms")
                else:
                    print(f"  ✅ 使用最大语速成功压缩到目标时长")
            else:
                # 在限制范围内，正常加速
                print(f"  ✅ 加速倍率在限制范围内，使用 {required_speedup_ratio:.2f}x")
                adjusted_durations = [int(duration / required_speedup_ratio) for duration in actual_durations]
        
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
    
    def _compress_gaps_only(self, actual_durations: List[int], gaps: List[int], excess_time: int) -> List[Dict]:
        """
        只压缩间隙（不加速音频）
        
        Args:
            actual_durations: 实际音频时长列表
            gaps: 原始间隙列表
            excess_time: 需要压缩的时长
        """
        print(f"\n  🔧 只压缩间隙，不加速音频")
        
        total_gap = sum(gaps)
        remaining_gap = total_gap - excess_time
        
        # 按比例压缩间隙
        if total_gap > 0:
            compression_ratio = remaining_gap / total_gap
            compressed_gaps = [int(gap * compression_ratio) for gap in gaps]
        else:
            compressed_gaps = [0] * len(gaps)
        
        # 显示压缩结果
        print(f"    原始间隙总时长: {total_gap}ms")
        print(f"    压缩后间隙总时长: {sum(compressed_gaps)}ms")
        print(f"    压缩比例: {compression_ratio:.2%}")
        
        # 显示前几个间隙的变化
        for i in range(min(5, len(gaps))):
            if gaps[i] > 0:
                print(f"    间隙 {i+1}: {gaps[i]}ms -> {compressed_gaps[i]}ms ({compressed_gaps[i] - gaps[i]:+d}ms)")
        
        # 重建时间轴
        return self._rebuild_timeline_with_gaps(actual_durations, compressed_gaps, actual_durations)
    
    def _compress_gaps_and_speedup(self, actual_durations: List[int], gaps: List[int], excess_time: int) -> List[Dict]:
        """
        同时压缩间隙和加速音频
        
        Args:
            actual_durations: 实际音频时长列表
            gaps: 原始间隙列表
            excess_time: 需要压缩的时长
        """
        print(f"\n  🔧 同时压缩间隙和加速音频")
        
        total_gap = sum(gaps)
        remaining_excess = excess_time - total_gap
        
        print(f"    移除所有间隙后仍超出: {remaining_excess}ms")
        
        # 移除所有间隙
        compressed_gaps = [0] * len(gaps)
        
        # 计算需要的加速倍率
        total_audio_duration = sum(actual_durations)
        target_audio_duration = total_audio_duration - remaining_excess
        required_speedup = total_audio_duration / target_audio_duration
        
        print(f"    需要加速倍率: {required_speedup:.2f}x")
        
        # 检查是否超过最大语速限制
        if required_speedup > self.max_speed_limit:
            print(f"    ⚠️ 超过最大语速限制 {self.max_speed_limit}x")
            actual_speedup = self.max_speed_limit
            adjusted_durations = [int(d / actual_speedup) for d in actual_durations]
            
            # 计算延长的时长
            compressed_duration = sum(adjusted_durations)
            extension = compressed_duration - self.original_total_time
            
            print(f"    使用最大语速 {actual_speedup}x，总时长将延长 {extension}ms")
        else:
            print(f"    ✅ 使用 {required_speedup:.2f}x 加速")
            adjusted_durations = [int(d / required_speedup) for d in actual_durations]
        
        # 重建时间轴
        return self._rebuild_timeline_with_gaps(adjusted_durations, compressed_gaps, actual_durations)
    
    def _rebuild_timeline_with_gaps(self, adjusted_durations: List[int], gaps: List[int], 
                                     original_durations: List[int]) -> List[Dict]:
        """
        使用指定的间隙重建时间轴
        
        Args:
            adjusted_durations: 调整后的音频时长列表
            gaps: 间隙列表
            original_durations: 原始音频时长列表（用于记录）
        """
        updated_subtitles = []
        current_time = 0
        
        print(f"\n  🔨 重建时间轴:")
        
        for i, (subtitle, duration, gap, original_duration) in enumerate(
            zip(self.subtitles, adjusted_durations, gaps, original_durations)
        ):
            # 添加间隙
            current_time += gap
            
            # 设置新的时间轴
            updated_subtitle = subtitle.copy()
            updated_subtitle['start_ms'] = current_time
            updated_subtitle['end_ms'] = current_time + duration
            
            # 保存调整信息
            if abs(original_duration - duration) > 10:
                updated_subtitle['original_duration_ms'] = original_duration
                updated_subtitle['adjusted_duration_ms'] = duration
                speed_ratio = original_duration / duration if duration > 0 else 1.0
                
                if i < 5:
                    print(f"    字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                          f"(间隙: {gap}ms, 配音: {duration}ms, 语速: {speed_ratio:.2f}x)")
            else:
                if i < 5:
                    print(f"    字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                          f"(间隙: {gap}ms, 配音: {duration}ms)")
            
            updated_subtitles.append(updated_subtitle)
            
            # 移动到下一个位置
            current_time += duration
        
        if len(updated_subtitles) > 5:
            print(f"    ... (省略 {len(updated_subtitles) - 5} 条)")
        
        final_time = updated_subtitles[-1]['end_ms'] if updated_subtitles else 0
        time_diff = final_time - self.original_total_time
        
        print(f"\n  📊 时间轴重建完成:")
        print(f"    原始总时长: {self.original_total_time}ms ({self.original_total_time/1000:.1f}秒)")
        print(f"    实际总时长: {final_time}ms ({final_time/1000:.1f}秒)")
        print(f"    时长差异: {time_diff:+d}ms ({time_diff/1000:+.1f}秒)")
        
        if abs(time_diff) <= 100:
            print(f"    ✅ 总时长基本一致（误差 ≤ 0.1秒）")
        elif time_diff < 0:
            print(f"    ✅ 总时长缩短 {abs(time_diff)}ms")
        else:
            print(f"    ⚠️ 总时长延长 {time_diff}ms")
        
        return updated_subtitles
    
    def _compress_gaps_first(self, actual_durations: List[int], excess_time: int) -> List[Dict]:
        """
        优先压缩间隙策略：最大化压缩字幕间的空隙，最小化配音加速
        
        策略：
        1. 计算所有字幕间的间隙
        2. 尽可能压缩/移除这些间隙
        3. 如果间隙压缩后仍超出，才考虑轻微加速
        4. 严格限制加速倍率，保持发音清晰
        """
        print(f"\n🎯 开始优先压缩间隙（语速限制: {self.max_speed_limit}x）")
        
        # 计算原始间隙
        gaps = []
        for i in range(len(self.subtitles)):
            if i == 0:
                gap = self.subtitles[i]['start_ms']
            else:
                gap = self.subtitles[i]['start_ms'] - self.subtitles[i-1]['end_ms']
            gaps.append(max(0, gap))
        
        total_gap = sum(gaps)
        total_audio_duration = sum(actual_durations)
        
        print(f"  📊 原始字幕间隙总时长: {total_gap}ms ({total_gap/1000:.1f}秒)")
        print(f"  📊 配音总时长: {total_audio_duration}ms ({total_audio_duration/1000:.1f}秒)")
        print(f"  📊 需要压缩: {excess_time}ms ({excess_time/1000:.1f}秒)")
        
        # 策略1：尽可能移除间隙
        if total_gap >= excess_time:
            # 间隙足够，完全通过压缩间隙解决
            print(f"  ✅ 间隙足够！完全通过压缩间隙解决，无需加速配音")
            remaining_gap = total_gap - excess_time
            
            # 按比例保留一些间隙（保持自然停顿）
            if remaining_gap > 0:
                compression_ratio = remaining_gap / total_gap
                compressed_gaps = [int(gap * compression_ratio) for gap in gaps]
                print(f"  📊 保留 {remaining_gap}ms ({remaining_gap/1000:.1f}秒) 间隙作为自然停顿")
            else:
                compressed_gaps = [0] * len(gaps)
                print(f"  📊 移除所有间隙")
            
            return self._rebuild_timeline(actual_durations, compressed_gaps, actual_durations)
        
        # 策略2：移除所有间隙后仍不够，需要轻微加速
        remaining_excess = excess_time - total_gap
        print(f"  ⚠️ 移除所有间隙后仍超出 {remaining_excess}ms ({remaining_excess/1000:.1f}秒)")
        print(f"  🔧 需要轻微加速配音")
        
        compressed_gaps = [0] * len(gaps)  # 移除所有间隙
        
        # 计算需要的加速倍率
        required_speedup = total_audio_duration / (total_audio_duration - remaining_excess)
        
        print(f"  📊 需要加速倍率: {required_speedup:.2f}x")
        
        # 检查是否超过限制
        if required_speedup > self.max_speed_limit:
            print(f"  ⚠️ 超过最大语速限制 {self.max_speed_limit}x")
            print(f"  🔧 使用最大允许语速 {self.max_speed_limit}x，并适当延长总时长")
            
            actual_speedup = self.max_speed_limit
            adjusted_durations = [int(d / actual_speedup) for d in actual_durations]
            
            # 计算延长的时长
            compressed_duration = sum(adjusted_durations)
            extension = compressed_duration - self.original_total_time
            
            print(f"  📊 使用 {actual_speedup}x 加速后配音时长: {compressed_duration}ms")
            print(f"  📊 需要延长总时长: {extension}ms ({extension/1000:.1f}秒)")
            
            self._final_extension = extension
        else:
            print(f"  ✅ 加速倍率在限制范围内，使用 {required_speedup:.2f}x")
            adjusted_durations = [int(d / required_speedup) for d in actual_durations]
        
        return self._rebuild_timeline(adjusted_durations, compressed_gaps, actual_durations)
    
    def _compress_timeline_with_speed_limit(self, actual_durations: List[int], excess_time: int) -> List[Dict]:
        """
        智能压缩时间轴：在语速限制下平衡压缩间隙和调整时间轴
        
        策略：
        1. 首先尝试压缩静音间隙
        2. 如果间隙不足，在语速限制内加速配音
        3. 如果仍不足，智能调整时间轴（适当延长或重新分配）
        4. 确保语速不超过最大限制
        """
        print(f"\n🎯 开始智能时间轴压缩（语速限制: {self.max_speed_limit}x）")
        
        # 计算原始间隙
        gaps = []
        for i in range(len(self.subtitles)):
            if i == 0:
                gap = self.subtitles[i]['start_ms']
            else:
                gap = self.subtitles[i]['start_ms'] - self.subtitles[i-1]['end_ms']
            gaps.append(max(0, gap))
        
        total_gap = sum(gaps)
        total_audio_duration = sum(actual_durations)
        
        print(f"  📊 原始间隙总时长: {total_gap}ms")
        print(f"  📊 配音总时长: {total_audio_duration}ms")
        print(f"  📊 需要压缩: {excess_time}ms")
        
        # 第一阶段：压缩间隙
        gap_compression = min(total_gap, excess_time)
        remaining_excess = excess_time - gap_compression
        
        if gap_compression > 0:
            compression_ratio = (total_gap - gap_compression) / total_gap if total_gap > 0 else 0
            compressed_gaps = [int(gap * compression_ratio) for gap in gaps]
            print(f"  ✅ 压缩间隙: {gap_compression}ms")
        else:
            compressed_gaps = gaps
            print(f"  ⚠️ 无间隙可压缩")
        
        # 第二阶段：在语速限制内加速配音
        if remaining_excess > 0:
            print(f"  📊 剩余需压缩: {remaining_excess}ms")
            
            # 计算最大允许的压缩量（基于语速限制）
            max_compression_by_speed = total_audio_duration - (total_audio_duration / self.max_speed_limit)
            actual_compression = min(remaining_excess, max_compression_by_speed)
            
            if actual_compression > 0:
                speedup_ratio = total_audio_duration / (total_audio_duration - actual_compression)
                adjusted_durations = [int(duration / speedup_ratio) for duration in actual_durations]
                print(f"  🚀 加速配音: {speedup_ratio:.2f}x，压缩 {actual_compression}ms")
                remaining_excess -= actual_compression
            else:
                adjusted_durations = actual_durations
                print(f"  ⚠️ 已达语速限制，无法进一步加速")
        else:
            adjusted_durations = actual_durations
            print(f"  ✅ 仅压缩间隙即可满足要求")
        
        # 第三阶段：处理剩余超出时间
        if remaining_excess > 0:
            print(f"  ⚠️ 仍有 {remaining_excess}ms 无法压缩")
            
            if self.preserve_total_time:
                # 保持总时长模式：智能调整策略
                print(f"  🔧 保持总时长模式：采用智能调整策略")
                return self._intelligent_timeline_adjustment(adjusted_durations, compressed_gaps, remaining_excess)
            else:
                # 非保持总时长模式：允许延长
                print(f"  ✅ 非保持总时长模式：允许延长 {remaining_excess}ms")
        
        # 重新计算时间轴
        return self._rebuild_timeline(adjusted_durations, compressed_gaps, actual_durations)
    
    def _intelligent_timeline_adjustment(self, adjusted_durations: List[int], compressed_gaps: List[int], excess_time: int) -> List[Dict]:
        """
        智能时间轴调整：在无法完全压缩的情况下，智能重新分配时间
        
        策略：
        1. 分析每段配音的压缩潜力
        2. 优先压缩较长的配音段
        3. 适当调整间隙分配
        4. 在保持合理语速的前提下微调时间轴
        """
        print(f"  🧠 启用智能时间轴调整，处理剩余 {excess_time}ms")
        
        # 分析每段配音的时长和压缩潜力
        compression_potential = []
        for i, (original_duration, adjusted_duration) in enumerate(zip([self._get_audio_duration(f) for f in self.audio_files], adjusted_durations)):
            current_speed = original_duration / adjusted_duration if adjusted_duration > 0 else 1.0
            max_additional_compression = 0
            
            if current_speed < self.max_speed_limit:
                # 还有加速空间
                max_speed_duration = original_duration / self.max_speed_limit
                max_additional_compression = adjusted_duration - max_speed_duration
            
            compression_potential.append({
                'index': i,
                'original_duration': original_duration,
                'current_duration': adjusted_duration,
                'current_speed': current_speed,
                'max_additional_compression': max(0, max_additional_compression),
                'priority': original_duration  # 优先压缩较长的段落
            })
        
        # 按优先级排序（较长的段落优先）
        compression_potential.sort(key=lambda x: x['priority'], reverse=True)
        
        # 逐步分配剩余的压缩需求
        remaining_to_compress = excess_time
        final_durations = adjusted_durations.copy()
        
        print(f"    📋 配音段压缩分析:")
        for item in compression_potential:
            if remaining_to_compress <= 0:
                break
                
            available_compression = item['max_additional_compression']
            if available_compression > 0:
                # 分配压缩量（不超过可用量和剩余需求）
                allocated_compression = min(available_compression, remaining_to_compress)
                
                if allocated_compression > 0:
                    final_durations[item['index']] -= int(allocated_compression)
                    remaining_to_compress -= allocated_compression
                    
                    new_speed = item['original_duration'] / final_durations[item['index']]
                    print(f"      段落 {item['index']+1}: 额外压缩 {allocated_compression:.0f}ms, 语速 {item['current_speed']:.2f}x -> {new_speed:.2f}x")
        
        # 如果仍有无法压缩的时间，采用微调策略
        if remaining_to_compress > 0:
            print(f"    ⚠️ 仍有 {remaining_to_compress}ms 无法压缩")
            
            # 策略1：微调间隙（允许负间隙，即重叠）
            if remaining_to_compress <= len(compressed_gaps) * 50:  # 每个间隙最多减少50ms
                gap_reduction_per_gap = remaining_to_compress / len(compressed_gaps)
                compressed_gaps = [max(0, gap - gap_reduction_per_gap) for gap in compressed_gaps]
                print(f"    🔧 微调间隙，平均每个间隙减少 {gap_reduction_per_gap:.1f}ms")
                remaining_to_compress = 0
            else:
                # 策略2：适当延长总时长（记录延长量）
                print(f"    📏 无法完全压缩，总时长将延长 {remaining_to_compress}ms")
                self._final_extension = remaining_to_compress
        
        return self._rebuild_timeline(final_durations, compressed_gaps, [self._get_audio_duration(f) for f in self.audio_files])
    
    def _rebuild_timeline(self, adjusted_durations: List[int], gaps: List[int], original_durations: List[int]) -> List[Dict]:
        """
        重建时间轴 - 使用累积时间，保持原始间隔不变
        
        策略：
        1. 计算每条字幕前的原始间隔
        2. 使用累积时间 + 原始间隔计算新的开始时间
        3. 根据调整后的配音时长设置结束时间
        4. 总时长自然变化（不强制等于原始总时长）
        """
        updated_subtitles = []
        current_time = 0  # 使用累积时间
        
        print(f"\n  🔨 重建时间轴（保持原始间隔不变）:")
        
        for i, (subtitle, duration, original_duration) in enumerate(zip(self.subtitles, adjusted_durations, original_durations)):
            # 计算原始间隔
            if i == 0:
                original_gap = subtitle['start_ms']  # 第一条字幕前的空白
            else:
                original_gap = subtitle['start_ms'] - self.subtitles[i-1]['end_ms']
            
            # 添加原始间隔
            current_time += original_gap
            
            # 设置新的时间轴
            updated_subtitle = subtitle.copy()
            updated_subtitle['start_ms'] = current_time  # 使用累积时间
            updated_subtitle['end_ms'] = current_time + duration
            
            # 保存调整信息
            if abs(original_duration - duration) > 10:
                updated_subtitle['original_duration_ms'] = original_duration
                updated_subtitle['adjusted_duration_ms'] = duration
                speed_ratio = original_duration / duration if duration > 0 else 1.0
                
                print(f"    字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                      f"(间隔: {original_gap}ms, 配音: {duration}ms, 语速: {speed_ratio:.2f}x)")
            else:
                print(f"    字幕 {i+1}: {updated_subtitle['start_ms']}ms - {updated_subtitle['end_ms']}ms "
                      f"(间隔: {original_gap}ms, 配音: {duration}ms)")
            
            updated_subtitles.append(updated_subtitle)
            
            # 移动到下一个位置
            current_time += duration
        
        final_time = updated_subtitles[-1]['end_ms'] if updated_subtitles else 0
        time_diff = final_time - self.original_total_time
        
        print(f"\n  📊 时间轴重建完成:")
        print(f"    原始总时长: {self.original_total_time}ms ({self.original_total_time/1000:.1f}秒)")
        print(f"    实际总时长: {final_time}ms ({final_time/1000:.1f}秒)")
        print(f"    时长差异: {time_diff:+d}ms ({time_diff/1000:+.1f}秒)")
        
        if abs(time_diff) <= 100:
            print(f"    ✅ 总时长基本一致（误差 ≤ 0.1秒）")
        elif time_diff < 0:
            print(f"    ✅ 总时长缩短 {abs(time_diff)}ms（配音加速所致）")
        else:
            print(f"    ⚠️ 总时长延长 {time_diff}ms（配音减速所致）")
        
        # 验证间隔是否保持
        print(f"\n  🔍 间隔验证:")
        all_gaps_preserved = True
        for i in range(len(updated_subtitles)):
            if i == 0:
                original_gap = self.subtitles[i]['start_ms']
                actual_gap = updated_subtitles[i]['start_ms']
            else:
                original_gap = self.subtitles[i]['start_ms'] - self.subtitles[i-1]['end_ms']
                actual_gap = updated_subtitles[i]['start_ms'] - updated_subtitles[i-1]['end_ms']
            
            gap_diff = actual_gap - original_gap
            if abs(gap_diff) > 10:  # 误差>10ms
                print(f"    字幕 {i+1}: 原始间隔={original_gap}ms, 实际间隔={actual_gap}ms, 差异={gap_diff:+d}ms ⚠️")
                all_gaps_preserved = False
            elif i < 3:  # 只显示前3个
                print(f"    字幕 {i+1}: 间隔={actual_gap}ms ✅")
        
        if all_gaps_preserved:
            print(f"    ✅ 所有间隔保持不变")
        else:
            print(f"    ⚠️ 部分间隔有变化")
        
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
        
        # 计算需要的总间隙（原始间隙 + 需要增加的）
        target_total_gap = total_gap + shortage_time
        
        # 按比例扩展间隙
        if total_gap > 0:
            # 有原始间隙，按比例扩展
            expansion_ratio = target_total_gap / total_gap
            expanded_gaps = [int(gap * expansion_ratio) for gap in gaps]
        else:
            # 没有原始间隙，均匀分配
            # 第一个字幕前不加间隙，其余字幕间均匀分配
            expanded_gaps = [0]  # 第一个字幕前无间隙
            if len(self.subtitles) > 1:
                avg_gap = shortage_time // (len(self.subtitles) - 1)
                expanded_gaps.extend([avg_gap] * (len(self.subtitles) - 1))
        
        # 微调以确保总时长精确匹配
        current_total = sum(actual_durations) + sum(expanded_gaps)
        adjustment = self.original_total_time - current_total
        if adjustment != 0 and len(expanded_gaps) > 0:
            # 将调整量分配到最后一个间隙，确保不为负数
            expanded_gaps[-1] = max(0, expanded_gaps[-1] + adjustment)
        
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
        print(f"  误差: {final_time - self.original_total_time:+d}ms")
        
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
