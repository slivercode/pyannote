"""
双重变速机制 - 智能音频/视频速度调整器
参考 pyvideotrans 项目的 SpeedRate 实现
支持：音频加速、视频慢速、智能策略选择
"""

import os
import subprocess
from pathlib import Path
from pydub import AudioSegment
import json
from typing import List, Dict, Optional, Tuple
import shutil


class SpeedRateAdjuster:
    """
    双重变速机制处理器
    实现音频加速和视频慢速的智能调整
    """
    
    # 常量配置
    MIN_CLIP_DURATION_MS = 40  # 最小片段时长（毫秒）
    AUDIO_SAMPLE_RATE = 44100  # 统一音频采样率
    AUDIO_CHANNELS = 2  # 统一音频声道数
    BEST_AUDIO_RATE = 1.3  # 最佳音频加速倍率阈值
    
    def __init__(
        self,
        subtitles: List[Dict],
        audio_files: List[str],
        output_dir: str,
        enable_audio_speedup: bool = True,
        enable_video_slowdown: bool = False,
        max_audio_speed_rate: float = 100.0,
        max_video_pts_rate: float = 10.0,
        remove_silent_gaps: bool = False,
        align_subtitle_audio: bool = True,
        raw_total_time_ms: int = 0
    ):
        """
        初始化双重变速调整器
        
        Args:
            subtitles: 字幕列表 [{'start_ms': int, 'end_ms': int, 'text': str, 'audio_file': str}, ...]
            audio_files: 配音文件列表（与字幕对应）
            output_dir: 输出目录
            enable_audio_speedup: 是否启用音频加速
            enable_video_slowdown: 是否启用视频慢速
            max_audio_speed_rate: 音频最大加速倍率
            max_video_pts_rate: 视频最大慢速倍率
            remove_silent_gaps: 是否移除字幕间的静音间隙
            align_subtitle_audio: 是否对齐字幕和音频时间轴
            raw_total_time_ms: 原始视频总时长（毫秒）
        """
        self.subtitles = subtitles
        self.audio_files = audio_files
        self.output_dir = Path(output_dir)
        self.enable_audio_speedup = enable_audio_speedup
        self.enable_video_slowdown = enable_video_slowdown
        self.max_audio_speed_rate = max_audio_speed_rate
        self.max_video_pts_rate = max_video_pts_rate
        self.remove_silent_gaps = remove_silent_gaps
        self.align_subtitle_audio = align_subtitle_audio
        self.raw_total_time_ms = raw_total_time_ms
        
        # 创建临时目录
        self.temp_dir = self.output_dir / "speed_adjust_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 检测可用的音频变速滤镜
        self.audio_speed_filter = self._check_ffmpeg_filters()
        
        print(f"🚀 双重变速机制初始化完成")
        print(f"  - 音频加速: {'✅' if enable_audio_speedup else '❌'}")
        print(f"  - 视频慢速: {'✅' if enable_video_slowdown else '❌'}")
        print(f"  - 音频变速引擎: {self.audio_speed_filter}")
        print(f"  - 最大音频加速倍率: {max_audio_speed_rate}x")
        print(f"  - 最大视频慢速倍率: {max_video_pts_rate}x")
    
    def _check_ffmpeg_filters(self) -> Optional[str]:
        """检查FFmpeg支持的音频变速滤镜"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-filters'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            filters_output = result.stdout
            
            if 'rubberband' in filters_output:
                print("✅ 检测到 FFmpeg 支持 'rubberband' 滤镜（高质量变速）")
                return 'rubberband'
            elif 'atempo' in filters_output:
                print("⚠️ 仅检测到 'atempo' 滤镜（标准变速）")
                return 'atempo'
            else:
                print("❌ 未检测到音频变速滤镜")
                return None
        except Exception as e:
            print(f"⚠️ 检查 FFmpeg 滤镜失败: {e}")
            return None
    
    def _get_audio_duration_ms(self, audio_path: str) -> int:
        """获取音频文件时长（毫秒）"""
        if not audio_path or not os.path.exists(audio_path):
            return 0
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio)
        except Exception as e:
            print(f"⚠️ 获取音频时长失败 {audio_path}: {e}")
            return 0
    
    def _prepare_data(self):
        """准备数据：计算原始时长、静音间隙等"""
        print("\n" + "="*60)
        print("📊 阶段 1/5: 准备数据")
        print("="*60)
        
        for i, subtitle in enumerate(self.subtitles):
            # 计算原始字幕时长
            subtitle['source_duration_ms'] = subtitle['end_ms'] - subtitle['start_ms']
            subtitle['start_time_source'] = subtitle['start_ms']
            subtitle['end_time_source'] = subtitle['end_ms']
            
            # 获取配音时长
            audio_file = self.audio_files[i] if i < len(self.audio_files) else None
            subtitle['audio_file'] = audio_file
            subtitle['dubb_time_ms'] = self._get_audio_duration_ms(audio_file)
            
            # 如果配音不存在，使用静音替代
            if subtitle['dubb_time_ms'] == 0:
                subtitle['dubb_time_ms'] = subtitle['source_duration_ms']
                subtitle['audio_file'] = None
            
            # 初始化目标时长（后续会调整）
            subtitle['final_audio_duration_theoretical'] = subtitle['dubb_time_ms']
            subtitle['final_video_duration_theoretical'] = subtitle['source_duration_ms']
            
            print(f"  字幕 {i+1}: 原时长={subtitle['source_duration_ms']}ms, "
                  f"配音时长={subtitle['dubb_time_ms']}ms")
        
        # 计算静音间隙
        for i, subtitle in enumerate(self.subtitles):
            if i < len(self.subtitles) - 1:
                subtitle['silent_gap'] = self.subtitles[i+1]['start_time_source'] - subtitle['end_time_source']
            else:
                subtitle['silent_gap'] = self.raw_total_time_ms - subtitle['end_time_source'] if self.raw_total_time_ms > 0 else 0
            subtitle['silent_gap'] = max(0, subtitle['silent_gap'])
    
    def _calculate_adjustments(self):
        """计算调整方案：智能选择音频加速/视频慢速策略"""
        print("\n" + "="*60)
        print("🧮 阶段 2/5: 计算调整方案")
        print("="*60)
        
        for i, subtitle in enumerate(self.subtitles):
            dubb_duration = subtitle['dubb_time_ms']
            source_duration = subtitle['source_duration_ms']
            silent_gap = subtitle['silent_gap']
            
            print(f"\n--- 分析字幕 {i+1} ---")
            print(f"  配音时长: {dubb_duration}ms")
            print(f"  字幕时长: {source_duration}ms")
            print(f"  静音间隙: {silent_gap}ms")
            
            if source_duration <= 0 or dubb_duration <= 0:
                print(f"  ⚠️ 时长异常，跳过调整")
                continue
            
            # 如果配音可以被原始时段容纳，无需处理
            if dubb_duration <= source_duration:
                print(f"  ✅ 配音时长 <= 字幕时长，无需调整")
                subtitle['final_audio_duration_theoretical'] = dubb_duration
                subtitle['final_video_duration_theoretical'] = source_duration
                continue
            
            # 可用总时长（包含静音间隙）
            block_source_duration = source_duration + silent_gap
            target_duration = dubb_duration
            video_target_duration = source_duration
            
            # 策略1: 音频加速 + 视频慢速
            if self.enable_audio_speedup and self.enable_video_slowdown:
                print(f"  📋 策略: 音频加速 + 视频慢速")
                speed_to_fit_source = dubb_duration / source_duration
                
                if block_source_duration >= dubb_duration:
                    print(f"  ✅ 利用静音间隙可容纳，无需变速")
                    target_duration = dubb_duration
                elif speed_to_fit_source <= self.BEST_AUDIO_RATE:
                    print(f"  ⚡ 仅需音频加速 (倍率{speed_to_fit_source:.2f} <= {self.BEST_AUDIO_RATE})")
                    target_duration = source_duration
                else:
                    print(f"  🔄 音频和视频共同承担调整")
                    over_time = dubb_duration - source_duration
                    video_extension = over_time / 2
                    target_duration = int(source_duration + video_extension)
                    video_target_duration = target_duration
            
            # 策略2: 仅音频加速
            elif self.enable_audio_speedup:
                print(f"  📋 策略: 仅音频加速")
                speed_to_fit_source = dubb_duration / source_duration
                
                if block_source_duration >= dubb_duration:
                    print(f"  ✅ 利用静音间隙可容纳，无需加速")
                    target_duration = dubb_duration
                elif speed_to_fit_source <= self.BEST_AUDIO_RATE:
                    print(f"  ⚡ 加速至原字幕时长 (倍率{speed_to_fit_source:.2f})")
                    target_duration = source_duration
                else:
                    speed_to_fit_source = min(speed_to_fit_source, self.max_audio_speed_rate)
                    target_duration = int(dubb_duration / speed_to_fit_source)
                    print(f"  ⚡ 限制最大加速倍率 {speed_to_fit_source:.2f}x")
            
            # 策略3: 仅视频慢速
            elif self.enable_video_slowdown:
                print(f"  📋 策略: 仅视频慢速")
                speed_to_fit_source = dubb_duration / source_duration
                
                if block_source_duration >= dubb_duration:
                    print(f"  ✅ 利用静音间隙可容纳，无需慢放")
                    video_target_duration = source_duration
                elif speed_to_fit_source <= self.max_video_pts_rate:
                    print(f"  🐌 视频慢放至配音时长")
                    video_target_duration = dubb_duration
                else:
                    speed_to_fit_source = min(speed_to_fit_source, self.max_video_pts_rate)
                    video_target_duration = int(dubb_duration / speed_to_fit_source)
                    print(f"  🐌 限制最大慢速倍率 {speed_to_fit_source:.2f}x")
            
            subtitle['final_audio_duration_theoretical'] = target_duration
            subtitle['final_video_duration_theoretical'] = video_target_duration
            
            print(f"  🎯 最终方案: 音频目标={target_duration}ms, 视频目标={video_target_duration}ms")
    
    def _execute_audio_speedup(self):
        """执行音频加速"""
        print("\n" + "="*60)
        print("⚡ 阶段 3/5: 执行音频加速")
        print("="*60)
        
        if not self.audio_speed_filter:
            print("⚠️ 未找到音频变速滤镜，跳过音频加速")
            return
        
        if not self.enable_audio_speedup:
            print("⚠️ 未启用音频加速")
            return
        
        for i, subtitle in enumerate(self.subtitles):
            target_duration_ms = int(subtitle['final_audio_duration_theoretical'])
            current_duration_ms = subtitle['dubb_time_ms']
            
            # 只有需要压缩时才处理
            if current_duration_ms <= target_duration_ms or not subtitle['audio_file']:
                continue
            
            speedup_ratio = current_duration_ms / target_duration_ms
            if speedup_ratio <= 1.0:
                continue
            
            print(f"\n  字幕 {i+1}: 加速 {speedup_ratio:.2f}x ({current_duration_ms}ms -> {target_duration_ms}ms)")
            
            input_file = subtitle['audio_file']
            output_file = self.temp_dir / f"speedup_{i:04d}.wav"
            
            # 构建FFmpeg命令
            cmd = ['ffmpeg', '-y', '-i', input_file]
            
            # 选择滤镜
            if self.audio_speed_filter == 'rubberband':
                filter_str = f"rubberband=tempo={speedup_ratio}"
            elif self.audio_speed_filter == 'atempo':
                # atempo限制在0.5-4.0之间，需要链式处理
                tempo_filters = []
                current_tempo = speedup_ratio
                while current_tempo > 4.0:
                    tempo_filters.append("atempo=4.0")
                    current_tempo /= 4.0
                if current_tempo >= 0.5:
                    tempo_filters.append(f"atempo={current_tempo}")
                filter_str = ",".join(tempo_filters)
            else:
                continue
            
            target_duration_sec = target_duration_ms / 1000.0
            cmd.extend([
                '-filter:a', filter_str,
                '-t', f'{target_duration_sec:.4f}',
                '-ar', str(self.AUDIO_SAMPLE_RATE),
                '-ac', str(self.AUDIO_CHANNELS),
                '-c:a', 'pcm_s16le',
                str(output_file)
            ])
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                # 更新音频文件和时长
                new_duration = self._get_audio_duration_ms(str(output_file))
                if new_duration > 0:
                    subtitle['audio_file'] = str(output_file)
                    subtitle['dubb_time_ms'] = new_duration
                    print(f"    ✅ 加速成功，实际时长: {new_duration}ms")
                else:
                    print(f"    ❌ 加速失败")
            except Exception as e:
                print(f"    ❌ 加速失败: {e}")
    
    def _merge_audio_segments(self) -> str:
        """合并音频片段"""
        print("\n" + "="*60)
        print("🔗 阶段 4/5: 合并音频片段")
        print("="*60)
        
        audio_segments = []
        total_duration = 0
        
        for i, subtitle in enumerate(self.subtitles):
            # 添加字幕前的静音
            if i == 0:
                silence_before = subtitle['start_time_source']
            else:
                silence_before = subtitle['start_time_source'] - self.subtitles[i-1]['end_time_source']
            
            if not self.remove_silent_gaps and silence_before > 0:
                print(f"  字幕 {i+1} 前添加静音: {silence_before}ms")
                audio_segments.append(AudioSegment.silent(duration=silence_before))
                total_duration += silence_before
            
            # 更新字幕开始时间
            if self.align_subtitle_audio:
                subtitle['start_ms'] = total_duration
            
            # 加载配音片段
            if subtitle['audio_file'] and os.path.exists(subtitle['audio_file']):
                try:
                    audio = AudioSegment.from_file(subtitle['audio_file'])
                    audio_segments.append(audio)
                    dubb_duration = len(audio)
                    total_duration += dubb_duration
                    print(f"  字幕 {i+1}: 添加配音 {dubb_duration}ms")
                except Exception as e:
                    print(f"  ⚠️ 字幕 {i+1} 加载音频失败: {e}")
                    silence = AudioSegment.silent(duration=subtitle['source_duration_ms'])
                    audio_segments.append(silence)
                    total_duration += subtitle['source_duration_ms']
            else:
                # 使用静音填充
                silence = AudioSegment.silent(duration=subtitle['source_duration_ms'])
                audio_segments.append(silence)
                total_duration += subtitle['source_duration_ms']
                print(f"  字幕 {i+1}: 使用静音填充 {subtitle['source_duration_ms']}ms")
            
            # 更新字幕结束时间
            if self.align_subtitle_audio:
                subtitle['end_ms'] = total_duration
        
        # 补充结尾静音
        if not self.remove_silent_gaps and self.raw_total_time_ms > 0 and total_duration < self.raw_total_time_ms:
            final_silence = self.raw_total_time_ms - total_duration
            print(f"  添加结尾静音: {final_silence}ms")
            audio_segments.append(AudioSegment.silent(duration=final_silence))
        
        # 合并所有片段
        print(f"\n  🔗 合并 {len(audio_segments)} 个音频片段...")
        final_audio = sum(audio_segments)
        
        # 导出最终音频
        output_path = self.output_dir / "final_audio_speedup.wav"
        print(f"  💾 导出最终音频: {output_path}")
        final_audio.export(str(output_path), format="wav")
        
        return str(output_path)
    
    def process(self) -> Tuple[str, List[Dict]]:
        """
        执行完整的双重变速处理流程
        
        Returns:
            (最终音频路径, 更新后的字幕列表)
        """
        print("\n" + "🎬 "*30)
        print("🎬 开始双重变速机制处理")
        print("🎬 "*30)
        
        # 如果既不加速也不慢速，直接合并
        if not self.enable_audio_speedup and not self.enable_video_slowdown:
            print("⚠️ 未启用变速功能，直接合并音频")
            output_path = self._merge_audio_segments()
            return output_path, self.subtitles
        
        # 阶段1: 准备数据
        self._prepare_data()
        
        # 阶段2: 计算调整方案
        self._calculate_adjustments()
        
        # 阶段3: 执行音频加速
        self._execute_audio_speedup()
        
        # 阶段4: 合并音频片段
        output_path = self._merge_audio_segments()
        
        # 阶段5: 清理临时文件
        print("\n" + "="*60)
        print("🧹 阶段 5/5: 清理临时文件")
        print("="*60)
        try:
            for temp_file in self.temp_dir.glob("*.wav"):
                temp_file.unlink()
            print("  ✅ 临时文件清理完成")
        except Exception as e:
            print(f"  ⚠️ 清理临时文件失败: {e}")
        
        print("\n" + "✅ "*30)
        print("✅ 双重变速处理完成！")
        print("✅ "*30 + "\n")
        
        return output_path, self.subtitles


if __name__ == "__main__":
    # 测试代码
    test_subtitles = [
        {'start_ms': 0, 'end_ms': 2000, 'text': '第一句话'},
        {'start_ms': 2500, 'end_ms': 5000, 'text': '第二句话'},
        {'start_ms': 6000, 'end_ms': 8000, 'text': '第三句话'},
    ]
    
    test_audio_files = [
        'audio_001.wav',
        'audio_002.wav',
        'audio_003.wav',
    ]
    
    adjuster = SpeedRateAdjuster(
        subtitles=test_subtitles,
        audio_files=test_audio_files,
        output_dir='./output',
        enable_audio_speedup=True,
        enable_video_slowdown=False,
        max_audio_speed_rate=2.0,
    )
    
    final_audio, updated_subtitles = adjuster.process()
    print(f"最终音频: {final_audio}")
    print(f"更新后的字幕: {updated_subtitles}")
