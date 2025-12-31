"""
视频时间轴同步处理器（四合一模块）

功能：
1. SRT对齐和差异分析
2. 视频片段切割
3. 视频片段慢放
4. 视频拼接和音轨替换

使用场景：
- 中文视频 + 中文SRT（原始时间轴）
- 日文配音 + 日文SRT（新时间轴）
- 通过切割、慢放、拼接视频，使画面与日文配音同步
"""

import os
import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class SubtitleEntry:
    """字幕条目"""
    index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    text: str
    
    @property
    def start_sec(self) -> float:
        return self.start_ms / 1000.0
    
    @property
    def end_sec(self) -> float:
        return self.end_ms / 1000.0


@dataclass
class TimelineDiff:
    """时间轴差异"""
    index: int
    original_entry: SubtitleEntry
    updated_entry: SubtitleEntry
    duration_diff_ms: int
    slowdown_ratio: float
    needs_slowdown: bool
    warning: Optional[str] = None


class VideoTimelineSyncProcessor:
    """视频时间轴同步处理器"""
    
    def __init__(
        self,
        original_video_path: str,
        original_srt_path: str,
        updated_audio_path: str,
        updated_srt_path: str,
        output_dir: str,
        max_slowdown_ratio: float = 2.0,
        quality_preset: str = "medium",
        enable_frame_interpolation: bool = True,
        include_gaps: bool = True,
        slowdown_start_index: int = 1
    ):
        """
        初始化处理器
        
        Args:
            original_video_path: 原始视频文件路径（中文视频）
            original_srt_path: 原始SRT文件路径（中文字幕）
            updated_audio_path: 更新后的音频文件路径（日文配音）
            updated_srt_path: 更新后的SRT文件路径（日文字幕）
            output_dir: 输出目录
            max_slowdown_ratio: 最大慢放倍率（默认2.0x）
            quality_preset: 质量预设 (fast/medium/high)
            enable_frame_interpolation: 是否启用帧插值
            include_gaps: 是否包含字幕之间的间隔片段（默认True）
            slowdown_start_index: 从第几句开始慢放（默认1，即从第一句开始）
        """
        self.original_video_path = Path(original_video_path)
        self.original_srt_path = Path(original_srt_path)
        self.updated_audio_path = Path(updated_audio_path)
        self.updated_srt_path = Path(updated_srt_path)
        self.output_dir = Path(output_dir)
        self.max_slowdown_ratio = max_slowdown_ratio
        self.quality_preset = quality_preset
        self.enable_frame_interpolation = enable_frame_interpolation
        self.include_gaps = include_gaps
        self.slowdown_start_index = slowdown_start_index
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建临时目录
        self.temp_dir = self.output_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.segments_dir = self.temp_dir / "segments"
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        
        self.slowed_dir = self.temp_dir / "slowed"
        self.slowed_dir.mkdir(parents=True, exist_ok=True)
    
    def parse_srt(self, srt_path: Path) -> List[SubtitleEntry]:
        """
        解析SRT文件
        
        Args:
            srt_path: SRT文件路径
            
        Returns:
            字幕条目列表
        """
        print(f"📖 解析SRT文件: {srt_path}")
        
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 标准化换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        entries = []
        blocks = re.split(r'\n\n+', content.strip())
        
        time_pattern = re.compile(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})')
        
        for block in blocks:
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            
            if len(lines) < 3:
                continue
            
            # 解析序号
            try:
                index = int(lines[0])
            except ValueError:
                continue
            
            # 解析时间轴
            time_match = time_pattern.match(lines[1])
            if not time_match:
                continue
            
            # 提取时间
            start_h, start_m, start_s, start_ms = map(int, time_match.groups()[:4])
            end_h, end_m, end_s, end_ms = map(int, time_match.groups()[4:])
            
            start_total_ms = (start_h * 3600 + start_m * 60 + start_s) * 1000 + start_ms
            end_total_ms = (end_h * 3600 + end_m * 60 + end_s) * 1000 + end_ms
            
            # 提取文本（移除说话人标识）
            text_lines = lines[2:]
            text = '\n'.join(text_lines)
            
            # 移除说话人标识 [spk00]
            text = re.sub(r'^\[.*?\]\s*', '', text)
            
            entries.append(SubtitleEntry(
                index=index,
                start_ms=start_total_ms,
                end_ms=end_total_ms,
                duration_ms=end_total_ms - start_total_ms,
                text=text
            ))
        
        print(f"✅ 解析完成: {len(entries)} 条字幕")
        return entries
    
    def analyze_timeline_diff(self) -> List[TimelineDiff]:
        """
        分析原始SRT和更新SRT的时间轴差异
        
        Returns:
            时间轴差异列表
        """
        print("\n" + "="*60)
        print("📊 分析时间轴差异")
        print("="*60)
        
        original_entries = self.parse_srt(self.original_srt_path)
        updated_entries = self.parse_srt(self.updated_srt_path)
        
        if len(original_entries) != len(updated_entries):
            print(f"⚠️ 警告: 字幕数量不一致")
            print(f"   原始SRT: {len(original_entries)} 条")
            print(f"   更新SRT: {len(updated_entries)} 条")
            # 使用较小的数量
            min_len = min(len(original_entries), len(updated_entries))
            original_entries = original_entries[:min_len]
            updated_entries = updated_entries[:min_len]
        
        timeline_diffs = []
        total_slowdown = 0
        needs_slowdown_count = 0
        warnings = []
        
        for orig, upd in zip(original_entries, updated_entries):
            duration_diff = upd.duration_ms - orig.duration_ms
            slowdown_ratio = upd.duration_ms / orig.duration_ms if orig.duration_ms > 0 else 1.0
            
            # 简化判断逻辑：只要时长比例不是1.0就需要慢放
            # 这样确保每个片段都按照新旧SRT的比例进行调整
            needs_slowdown = (
                abs(slowdown_ratio - 1.0) > 0.01 and  # 比例差异>1%
                abs(duration_diff) > 50  # 时长差异>50ms，避免处理微小差异
            )
            
            warning = None
            if slowdown_ratio > self.max_slowdown_ratio:
                warning = f"慢放倍率 {slowdown_ratio:.2f}x 超过最大限制 {self.max_slowdown_ratio}x"
                warnings.append(f"字幕{orig.index}: {warning}")
            elif slowdown_ratio < 1.0 and needs_slowdown:
                warning = f"需要加速 {slowdown_ratio:.2f}x (配音短于画面)"
                warnings.append(f"字幕{orig.index}: {warning}")
            
            timeline_diffs.append(TimelineDiff(
                index=orig.index,
                original_entry=orig,
                updated_entry=upd,
                duration_diff_ms=duration_diff,
                slowdown_ratio=slowdown_ratio,
                needs_slowdown=needs_slowdown,
                warning=warning
            ))
            
            if needs_slowdown:
                total_slowdown += slowdown_ratio
                needs_slowdown_count += 1
        
        # 如果包含间隔片段，显示全局慢放比例信息(仅供参考,不覆盖原始比例)
        if self.include_gaps and len(timeline_diffs) > 0:
            self._show_global_slowdown_info(timeline_diffs, original_entries)
        
        # 统计信息
        original_total = original_entries[-1].end_ms if original_entries else 0
        updated_total = updated_entries[-1].end_ms if updated_entries else 0
        
        # 重新统计needs_slowdown_count(因为可能被_recalculate_slowdown_with_gaps修改)
        needs_slowdown_count = sum(1 for d in timeline_diffs if d.needs_slowdown)
        total_slowdown = sum(d.slowdown_ratio for d in timeline_diffs if d.needs_slowdown)
        
        print(f"\n📈 统计信息:")
        print(f"   总字幕数: {len(timeline_diffs)}")
        print(f"   原始总时长: {original_total/1000:.1f}秒")
        print(f"   更新总时长: {updated_total/1000:.1f}秒")
        print(f"   时长差异: {(updated_total - original_total)/1000:+.1f}秒")
        print(f"   需要慢放的片段: {needs_slowdown_count}")
        
        if needs_slowdown_count > 0:
            avg_slowdown = total_slowdown / needs_slowdown_count
            print(f"   平均慢放倍率: {avg_slowdown:.2f}x")
        
        if warnings:
            print(f"\n⚠️ 发现 {len(warnings)} 个警告:")
            for warning in warnings[:5]:
                print(f"   {warning}")
            if len(warnings) > 5:
                print(f"   ... 还有 {len(warnings)-5} 个警告")
        
        return timeline_diffs
    
    def _show_global_slowdown_info(
        self, 
        timeline_diffs: List[TimelineDiff],
        original_entries: List[SubtitleEntry]
    ) -> None:
        """
        显示考虑间隔片段后的全局慢放比例信息(仅供参考)
        
        注意: 此方法不修改timeline_diffs,只显示统计信息
        
        Args:
            timeline_diffs: 时间轴差异列表
            original_entries: 原始字幕条目列表
        """
        print("\n📊 全局慢放比例分析（考虑间隔片段）...")
        
        # 获取视频总时长
        video_duration_sec = self._get_video_duration()
        
        # 1. 计算间隔片段的总时长
        gap_total_ms = 0.0
        
        # 开头间隔
        if len(original_entries) > 0:
            first_start_ms = original_entries[0].start_ms
            if first_start_ms > 100:  # 大于0.1秒
                gap_total_ms += first_start_ms
                print(f"  开头间隔: {first_start_ms/1000:.2f}秒")
        
        # 字幕之间的间隔
        gap_count = 0
        for i in range(len(original_entries) - 1):
            gap_ms = original_entries[i+1].start_ms - original_entries[i].end_ms
            if gap_ms > 100:  # 大于0.1秒
                gap_total_ms += gap_ms
                gap_count += 1
        if gap_count > 0:
            print(f"  中间间隔: {gap_count}个, 总计{gap_total_ms/1000:.2f}秒")
        
        # 尾部间隔
        if len(original_entries) > 0 and video_duration_sec > 0:
            last_end_ms = original_entries[-1].end_ms
            video_duration_ms = video_duration_sec * 1000
            tail_gap_ms = video_duration_ms - last_end_ms
            if tail_gap_ms > 100:  # 大于0.1秒
                gap_total_ms += tail_gap_ms
                print(f"  尾部间隔: {tail_gap_ms/1000:.2f}秒")
        
        print(f"  间隔片段总时长: {gap_total_ms/1000:.2f}秒")
        
        # 2. 计算字幕片段的原始总时长
        subtitle_original_total_ms = sum(diff.original_entry.duration_ms for diff in timeline_diffs)
        print(f"  字幕片段原始总时长: {subtitle_original_total_ms/1000:.2f}秒")
        
        # 3. 获取音频文件的实际总时长（目标时长）
        audio_duration_sec = self._get_audio_duration()
        if audio_duration_sec > 0:
            audio_total_ms = audio_duration_sec * 1000
            print(f"  音频文件实际总时长: {audio_total_ms/1000:.2f}秒")
        else:
            # 如果无法获取音频时长,使用字幕的结束时间作为备选
            audio_total_ms = timeline_diffs[-1].updated_entry.end_ms if timeline_diffs else 0
            print(f"  音频总时长（从字幕推断）: {audio_total_ms/1000:.2f}秒")
        
        # 4. 计算字幕片段需要的总时长
        subtitle_target_total_ms = audio_total_ms - gap_total_ms
        print(f"  字幕片段目标总时长: {subtitle_target_total_ms/1000:.2f}秒")
        
        # 边界检查
        if subtitle_target_total_ms <= 0:
            print(f"  ⚠️ 警告: 间隔片段时长({gap_total_ms/1000:.2f}秒) >= 音频总时长({audio_total_ms/1000:.2f}秒)")
            return
        
        # 5. 计算全局慢放比例(仅供参考)
        if subtitle_original_total_ms > 0:
            global_slowdown_ratio = subtitle_target_total_ms / subtitle_original_total_ms
            
            print(f"\n  💡 如果使用全局统一慢放比例:")
            print(f"     全局慢放比例: {global_slowdown_ratio:.3f}x")
            print(f"     (字幕目标时长 / 字幕原始时长 = {subtitle_target_total_ms/1000:.2f} / {subtitle_original_total_ms/1000:.2f})")
            
            # 检查是否需要加速（比例<1）
            if global_slowdown_ratio < 1.0:
                print(f"     ⚠️ 注意: 需要加速视频（比例<1.0）")
            
            # 检查是否超过最大慢放限制
            if global_slowdown_ratio > self.max_slowdown_ratio:
                print(f"     ⚠️ 警告: 全局比例({global_slowdown_ratio:.2f}x) 超过最大限制({self.max_slowdown_ratio}x)")
            
            print(f"\n  ℹ️  实际处理: 每个片段使用各自的慢放比例(基于原始SRT vs 更新SRT)")
        else:
            print(f"  ⚠️ 字幕片段总时长为0，无法计算比例")
    
    def cut_video_segments(self, timeline_diffs: List[TimelineDiff], include_gaps: bool = True) -> List[Path]:
        """
        根据原始SRT的时间轴切割视频，可选包含字幕间隔
        
        Args:
            timeline_diffs: 时间轴差异列表
            include_gaps: 是否包含字幕之间的间隔片段
            
        Returns:
            切割后的视频片段路径列表（按时间顺序）
        """
        print("\n" + "="*60)
        print("✂️  切割视频片段")
        print("="*60)
        
        if include_gaps:
            print("📝 将包含字幕之间的间隔片段")
            return self._cut_segments_with_gaps(timeline_diffs)
        else:
            return self._cut_subtitle_segments_only(timeline_diffs)
    
    def _cut_subtitle_segments_only(self, timeline_diffs: List[TimelineDiff]) -> List[Path]:
        """仅切割字幕对应的片段（原有逻辑）"""
        segments = []
        
        for i, diff in enumerate(timeline_diffs):
            print(f"切割片段 {i+1}/{len(timeline_diffs)}: "
                  f"{diff.original_entry.start_sec:.2f}s - {diff.original_entry.end_sec:.2f}s")
            
            output_path = self.segments_dir / f"segment_{i+1:04d}.mp4"
            
            # FFmpeg切割命令
            cmd = [
                'ffmpeg', '-y',
                '-i', str(self.original_video_path),
                '-ss', str(diff.original_entry.start_sec),
                '-to', str(diff.original_entry.end_sec),
                '-c:v', 'libx264',
                '-preset', self.quality_preset,
                '-crf', '18',
                '-c:a', 'aac',
                '-avoid_negative_ts', 'make_zero',
                output_path
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    check=True
                )
                segments.append(output_path)
            except subprocess.CalledProcessError as e:
                print(f"   ❌ 切割失败: {e}")
                print(f"   错误输出: {e.stderr[:200]}")
                raise
        
        print(f"\n✅ 切割完成: {len(segments)} 个片段")
        return segments
    
    def _get_audio_duration(self) -> float:
        """
        获取音频总时长（秒）
        
        Returns:
            音频时长（秒）
        """
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(self.updated_audio_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            duration = float(result.stdout.strip())
            return duration
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"⚠️ 无法获取音频时长: {e}")
            return 0.0
    
    def _get_video_duration(self) -> float:
        """
        获取原始视频总时长（秒）
        
        Returns:
            视频时长（秒）
        """
        return self._get_video_duration_from_file(self.original_video_path)
    
    def _get_video_duration_from_file(self, video_path: Path) -> float:
        """
        获取指定视频文件的总时长（秒）
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频时长（秒）
        """
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            duration = float(result.stdout.strip())
            return duration
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"⚠️ 无法获取视频时长: {e}")
            return 0.0
    
    def _cut_segments_with_gaps(self, timeline_diffs: List[TimelineDiff]) -> List[Path]:
        """
        切割字幕片段和间隔片段
        
        返回格式：[开头间隔, 字幕1, 间隔1, 字幕2, 间隔2, ..., 字幕N, 尾部间隔]
        """
        segments = []
        segment_counter = 0
        
        # 获取视频总时长
        video_duration = self._get_video_duration()
        if video_duration > 0:
            print(f"📹 视频总时长: {video_duration:.2f}秒")
        
        # 0. 切割第一个字幕之前的间隔（如果存在）
        if len(timeline_diffs) > 0:
            first_subtitle_start = timeline_diffs[0].original_entry.start_sec
            
            # 如果第一个字幕不是从0秒开始，切割开头的间隔
            if first_subtitle_start > 0.1:
                segment_counter += 1
                initial_gap_output = self.segments_dir / f"segment_{segment_counter:04d}_initial_gap.mp4"
                
                print(f"切割开头间隔片段: 0.00s - {first_subtitle_start:.2f}s (时长: {first_subtitle_start:.2f}s)")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(self.original_video_path),
                    '-ss', '0',
                    '-to', str(first_subtitle_start),
                    '-c:v', 'libx264',
                    '-preset', self.quality_preset,
                    '-crf', '18',
                    '-c:a', 'aac',
                    '-avoid_negative_ts', 'make_zero',
                    initial_gap_output
                ]
                
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                    segments.append(initial_gap_output)
                    print(f"  ✅ 开头间隔片段已添加")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠️ 切割开头间隔片段失败（将跳过）: {e}")
        
        for i, diff in enumerate(timeline_diffs):
            # 1. 切割字幕片段
            segment_counter += 1
            subtitle_output = self.segments_dir / f"segment_{segment_counter:04d}_subtitle.mp4"
            
            print(f"切割字幕片段 {i+1}/{len(timeline_diffs)}: "
                  f"{diff.original_entry.start_sec:.2f}s - {diff.original_entry.end_sec:.2f}s")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', str(self.original_video_path),
                '-ss', str(diff.original_entry.start_sec),
                '-to', str(diff.original_entry.end_sec),
                '-c:v', 'libx264',
                '-preset', self.quality_preset,
                '-crf', '18',
                '-c:a', 'aac',
                '-avoid_negative_ts', 'make_zero',
                subtitle_output
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                segments.append(subtitle_output)
            except subprocess.CalledProcessError as e:
                print(f"   ❌ 切割字幕片段失败: {e}")
                raise
            
            # 2. 切割间隔片段（如果存在下一个字幕）
            if i < len(timeline_diffs) - 1:
                gap_start = diff.original_entry.end_sec
                gap_end = timeline_diffs[i + 1].original_entry.start_sec
                gap_duration = gap_end - gap_start
                
                # 只有当间隔大于0.1秒时才切割
                if gap_duration > 0.1:
                    segment_counter += 1
                    gap_output = self.segments_dir / f"segment_{segment_counter:04d}_gap.mp4"
                    
                    print(f"  切割间隔片段: {gap_start:.2f}s - {gap_end:.2f}s (时长: {gap_duration:.2f}s)")
                    
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', str(self.original_video_path),
                        '-ss', str(gap_start),
                        '-to', str(gap_end),
                        '-c:v', 'libx264',
                        '-preset', self.quality_preset,
                        '-crf', '18',
                        '-c:a', 'aac',
                        '-avoid_negative_ts', 'make_zero',
                        gap_output
                    ]
                    
                    try:
                        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                        segments.append(gap_output)
                    except subprocess.CalledProcessError as e:
                        print(f"   ⚠️ 切割间隔片段失败（将跳过）: {e}")
                        # 间隔片段失败不影响整体流程
        
        # 3. 切割最后一个字幕之后的尾部间隔（如果存在）
        if len(timeline_diffs) > 0 and video_duration > 0:
            last_subtitle_end = timeline_diffs[-1].original_entry.end_sec
            tail_gap_duration = video_duration - last_subtitle_end
            
            # 只有当尾部间隔大于0.1秒时才切割
            if tail_gap_duration > 0.1:
                segment_counter += 1
                tail_gap_output = self.segments_dir / f"segment_{segment_counter:04d}_tail_gap.mp4"
                
                print(f"切割尾部间隔片段: {last_subtitle_end:.2f}s - {video_duration:.2f}s (时长: {tail_gap_duration:.2f}s)")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(self.original_video_path),
                    '-ss', str(last_subtitle_end),
                    '-to', str(video_duration),
                    '-c:v', 'libx264',
                    '-preset', self.quality_preset,
                    '-crf', '18',
                    '-c:a', 'aac',
                    '-avoid_negative_ts', 'make_zero',
                    tail_gap_output
                ]
                
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                    segments.append(tail_gap_output)
                    print(f"  ✅ 尾部间隔片段已添加")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠️ 切割尾部间隔片段失败（将跳过）: {e}")
        
        print(f"\n✅ 切割完成: {len(segments)} 个片段（包含字幕和间隔）")
        return segments
    
    def slowdown_video_segment(
        self,
        input_path: Path,
        output_path: Path,
        slowdown_ratio: float,
        target_duration_sec: float
    ) -> bool:
        """
        对视频片段进行慢放处理
        
        Args:
            input_path: 输入片段路径
            output_path: 输出片段路径
            slowdown_ratio: 慢放倍率
            target_duration_sec: 目标时长（秒）
            
        Returns:
            是否成功
        """
        # 如果不需要慢放（倍率接近1.0），直接复制
        if abs(slowdown_ratio - 1.0) < 0.01:
            shutil.copy(input_path, output_path)
            return True
        
        # 选择慢放方法
        if slowdown_ratio < 1.5 or not self.enable_frame_interpolation:
            # 方法1：PTS调整（简单快速）
            cmd = [
                'ffmpeg', '-y',
                '-i', str(input_path),
                '-vf', f'setpts={slowdown_ratio}*PTS',
                '-an',  # 移除音频（后续会替换）
                '-c:v', 'libx264',
                '-preset', self.quality_preset,
                '-crf', '18',
                str(output_path)
            ]
        else:
            # 方法2：帧插值（高质量）
            cmd = [
                'ffmpeg', '-y',
                '-i', str(input_path),
                '-vf', f"minterpolate='fps=60:mi_mode=mci',setpts={slowdown_ratio}*PTS",
                '-an',
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-crf', '18',
                str(output_path)
            ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"   ❌ 慢放失败: {e}")
            print(f"   错误输出: {e.stderr[:200]}")
            return False
    
    def slowdown_segments(
        self,
        segments: List[Path],
        timeline_diffs: List[TimelineDiff]
    ) -> List[Path]:
        """
        对所有需要慢放的片段进行处理（跳过间隔片段）
        
        Args:
            segments: 原始片段列表（可能包含间隔片段）
            timeline_diffs: 时间轴差异列表
            
        Returns:
            处理后的片段列表
        """
        print("\n" + "="*60)
        print("🐌 慢放视频片段")
        print("="*60)
        
        processed_segments = []
        diff_index = 0  # timeline_diffs的索引
        
        for i, segment in enumerate(segments):
            # 判断是否是间隔片段（文件名包含_gap）
            is_gap = '_gap' in segment.name
            
            if is_gap:
                # 间隔片段直接保留，不做慢放处理
                print(f"保留间隔片段 {i+1}/{len(segments)}: {segment.name}")
                processed_segments.append(segment)
            else:
                # 字幕片段，检查是否需要慢放
                if diff_index < len(timeline_diffs):
                    diff = timeline_diffs[diff_index]
                    
                    if diff.needs_slowdown:
                        print(f"处理字幕片段 {i+1}/{len(segments)}: "
                              f"慢放 {diff.slowdown_ratio:.2f}x "
                              f"({diff.original_entry.duration_ms}ms → {diff.updated_entry.duration_ms}ms)")
                        
                        output_path = self.slowed_dir / f"slowed_{diff_index+1:04d}.mp4"
                        target_duration = diff.updated_entry.duration_ms / 1000.0
                        
                        success = self.slowdown_video_segment(
                            segment,
                            output_path,
                            diff.slowdown_ratio,
                            target_duration
                        )
                        
                        if success:
                            processed_segments.append(output_path)
                        else:
                            print(f"   ⚠️ 慢放失败，使用原始片段")
                            processed_segments.append(segment)
                    else:
                        print(f"保留字幕片段 {i+1}/{len(segments)}: 无需慢放")
                        processed_segments.append(segment)
                    
                    diff_index += 1
                else:
                    # 超出timeline_diffs范围，直接保留
                    print(f"保留片段 {i+1}/{len(segments)}: 超出范围")
                    processed_segments.append(segment)
        
        print(f"\n✅ 处理完成: {len(processed_segments)} 个片段")
        return processed_segments
    
    def concatenate_segments(self, segments: List[Path], output_path: Path) -> bool:
        """
        拼接视频片段
        
        Args:
            segments: 片段路径列表（已包含间隔片段）
            output_path: 输出视频路径
            
        Returns:
            是否成功
        """
        print("\n" + "="*60)
        print("🔗 拼接视频片段")
        print("="*60)
        
        # 创建concat文件列表
        concat_file = self.temp_dir / "concat_list.txt"
        with open(concat_file, 'w', encoding='utf-8') as f:
            for segment in segments:
                # 使用绝对路径，并转换为Unix风格路径（FFmpeg在Windows上也支持）
                abs_path = segment.resolve()
                # 将Windows路径转换为Unix风格（用正斜杠）
                unix_path = str(abs_path).replace('\\', '/')
                f.write(f"file '{unix_path}'\n")
        
        print(f"拼接 {len(segments)} 个片段...")
        
        # FFmpeg concat命令
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            str(output_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print(f"✅ 拼接完成: {output_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 拼接失败: {e}")
            print(f"错误输出: {e.stderr[:200]}")
            return False
    
    def replace_audio_and_add_subtitle(
        self,
        video_path: Path,
        audio_path: Path,
        srt_path: Path,
        output_path: Path
    ) -> bool:
        """
        替换视频音轨并添加字幕
        
        Args:
            video_path: 视频文件路径
            audio_path: 音频文件路径
            srt_path: 字幕文件路径
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        print("\n" + "="*60)
        print("🎵 替换音轨和添加字幕")
        print("="*60)
        
        # FFmpeg命令
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_path),
            '-i', str(audio_path),
            '-i', str(srt_path),
            '-map', '0:v',  # 视频流
            '-map', '1:a',  # 音频流
            '-map', '2:s',  # 字幕流
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-c:s', 'mov_text',
            str(output_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print(f"✅ 完成: {output_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 失败: {e}")
            print(f"错误输出: {e.stderr[:200]}")
            return False
    
    def process(self) -> Dict:
        """
        执行完整的视频时间轴同步流程
        
        Returns:
            处理结果字典
        """
        print("\n" + "="*60)
        print("🎬 视频时间轴同步处理器")
        print("="*60)
        print(f"原始视频: {self.original_video_path}")
        print(f"原始SRT: {self.original_srt_path}")
        print(f"更新音频: {self.updated_audio_path}")
        print(f"更新SRT: {self.updated_srt_path}")
        print(f"输出目录: {self.output_dir}")
        print(f"包含间隔片段: {'是' if self.include_gaps else '否'}")
        
        try:
            # 步骤1：分析时间轴差异
            timeline_diffs = self.analyze_timeline_diff()
            
            # 获取视频和音频时长
            video_duration = self._get_video_duration()
            audio_duration = self._get_audio_duration()
            
            print(f"\n📊 时长信息:")
            print(f"   原始视频时长: {video_duration:.2f}秒")
            print(f"   更新音频时长: {audio_duration:.2f}秒")
            
            # 判断处理策略
            if abs(video_duration - audio_duration) < 1.0:
                # 策略A：视频和音频时长接近，直接按更新SRT切割
                print(f"\n📝 策略A：视频时长与音频接近，直接按更新SRT切割")
                segments = self._cut_by_updated_srt(timeline_diffs)
                processed_segments = segments  # 不需要慢放
            else:
                # 策略B：视频和音频时长差异大，先全局慢放再切割
                print(f"\n📝 策略B：视频时长与音频差异大，先全局慢放再切割")
                
                # 计算全局慢放比例
                global_ratio = audio_duration / video_duration if video_duration > 0 else 1.0
                print(f"   全局慢放比例: {global_ratio:.3f}x")
                
                # 全局慢放视频
                slowed_video = self._slowdown_full_video(global_ratio)
                
                # 按更新SRT切割慢放后的视频
                segments = self._cut_slowed_video_by_updated_srt(slowed_video, timeline_diffs)
                processed_segments = segments
            
            # 步骤4：拼接视频片段
            temp_video = self.temp_dir / "concatenated.mp4"
            if not self.concatenate_segments(processed_segments, temp_video):
                raise Exception("视频拼接失败")
            
            # 步骤5：替换音轨和添加字幕
            final_output = self.output_dir / "synced_video.mp4"
            if not self.replace_audio_and_add_subtitle(
                temp_video,
                self.updated_audio_path,
                self.updated_srt_path,
                final_output
            ):
                raise Exception("音轨替换失败")
            
            # 清理临时文件
            print("\n🧹 清理临时文件...")
            shutil.rmtree(self.temp_dir)
            
            print("\n" + "="*60)
            print("✅ 处理完成！")
            print("="*60)
            print(f"输出文件: {final_output}")
            
            return {
                'success': True,
                'output_path': str(final_output),
                'timeline_diffs': len(timeline_diffs),
                'segments_processed': len(processed_segments)
            }
            
        except Exception as e:
            print(f"\n❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def _slowdown_full_video(self, ratio: float) -> Path:
        """
        全局慢放整个视频
        
        Args:
            ratio: 慢放比例
            
        Returns:
            慢放后的视频路径
        """
        print(f"\n🐌 全局慢放视频 ({ratio:.3f}x)...")
        
        output_path = self.temp_dir / "slowed_full.mp4"
        
        cmd = [
            'ffmpeg', '-y',
            '-i', str(self.original_video_path),
            '-filter:v', f'setpts={ratio}*PTS',
            '-an',  # 移除音频
            '-c:v', 'libx264',
            '-preset', self.quality_preset,
            '-crf', '18',
            str(output_path)
        ]
        
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print(f"✅ 全局慢放完成: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"❌ 全局慢放失败: {e}")
            raise
    
    def _cut_by_updated_srt(self, timeline_diffs: List[TimelineDiff]) -> List[Path]:
        """
        直接按更新SRT切割原始视频（策略A）- 包含间隔片段
        
        Args:
            timeline_diffs: 时间轴差异列表
            
        Returns:
            切割后的片段列表（包含字幕片段和间隔片段）
        """
        print("\n✂️  按更新SRT切割视频（包含间隔）...")
        
        segments = []
        segment_counter = 0
        
        # 获取视频总时长
        video_duration = self._get_video_duration()
        
        # 0. 切割第一个字幕之前的初始间隔（如果存在）
        if len(timeline_diffs) > 0:
            first_start = timeline_diffs[0].updated_entry.start_sec
            if first_start > 0.1:
                segment_counter += 1
                initial_gap_output = self.segments_dir / f"segment_{segment_counter:04d}_initial_gap.mp4"
                
                print(f"切割开头间隔: 0.00s - {first_start:.2f}s")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(self.original_video_path),
                    '-ss', '0',
                    '-to', str(first_start),
                    '-c:v', 'libx264',
                    '-preset', self.quality_preset,
                    '-crf', '18',
                    '-an',  # 移除音频
                    '-avoid_negative_ts', 'make_zero',
                    str(initial_gap_output)
                ]
                
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                    segments.append(initial_gap_output)
                    print(f"  ✅ 开头间隔已添加")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠️ 切割开头间隔失败: {e}")
        
        # 1. 切割字幕片段和中间间隔
        for i, diff in enumerate(timeline_diffs):
            # 切割字幕片段
            segment_counter += 1
            subtitle_output = self.segments_dir / f"segment_{segment_counter:04d}_subtitle.mp4"
            
            print(f"切割字幕片段 {i+1}/{len(timeline_diffs)}: "
                  f"{diff.updated_entry.start_sec:.2f}s - {diff.updated_entry.end_sec:.2f}s")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', str(self.original_video_path),
                '-ss', str(diff.updated_entry.start_sec),
                '-to', str(diff.updated_entry.end_sec),
                '-c:v', 'libx264',
                '-preset', self.quality_preset,
                '-crf', '18',
                '-an',  # 移除音频
                '-avoid_negative_ts', 'make_zero',
                str(subtitle_output)
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                segments.append(subtitle_output)
            except subprocess.CalledProcessError as e:
                print(f"   ❌ 切割字幕片段失败: {e}")
                raise
            
            # 切割间隔片段（如果存在下一个字幕）
            if i < len(timeline_diffs) - 1:
                gap_start = diff.updated_entry.end_sec
                gap_end = timeline_diffs[i + 1].updated_entry.start_sec
                gap_duration = gap_end - gap_start
                
                if gap_duration > 0.1:
                    segment_counter += 1
                    gap_output = self.segments_dir / f"segment_{segment_counter:04d}_gap.mp4"
                    
                    print(f"  切割间隔: {gap_start:.2f}s - {gap_end:.2f}s")
                    
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', str(self.original_video_path),
                        '-ss', str(gap_start),
                        '-to', str(gap_end),
                        '-c:v', 'libx264',
                        '-preset', self.quality_preset,
                        '-crf', '18',
                        '-an',  # 移除音频
                        '-avoid_negative_ts', 'make_zero',
                        str(gap_output)
                    ]
                    
                    try:
                        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                        segments.append(gap_output)
                    except subprocess.CalledProcessError as e:
                        print(f"   ⚠️ 切割间隔失败: {e}")
        
        # 2. 切割尾部间隔（如果存在）
        if len(timeline_diffs) > 0 and video_duration > 0:
            last_end = timeline_diffs[-1].updated_entry.end_sec
            tail_gap_duration = video_duration - last_end
            
            if tail_gap_duration > 0.1:
                segment_counter += 1
                tail_gap_output = self.segments_dir / f"segment_{segment_counter:04d}_tail_gap.mp4"
                
                print(f"切割尾部间隔: {last_end:.2f}s - {video_duration:.2f}s")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(self.original_video_path),
                    '-ss', str(last_end),
                    '-to', str(video_duration),
                    '-c:v', 'libx264',
                    '-preset', self.quality_preset,
                    '-crf', '18',
                    '-an',  # 移除音频
                    '-avoid_negative_ts', 'make_zero',
                    str(tail_gap_output)
                ]
                
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                    segments.append(tail_gap_output)
                    print(f"  ✅ 尾部间隔已添加")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠️ 切割尾部间隔失败: {e}")
        
        print(f"\n✅ 切割完成: {len(segments)} 个片段（包含字幕和间隔）")
        return segments
    
    def _cut_slowed_video_by_updated_srt(
        self, 
        slowed_video: Path, 
        timeline_diffs: List[TimelineDiff]
    ) -> List[Path]:
        """
        按更新SRT切割慢放后的视频（策略B）- 包含间隔片段
        
        Args:
            slowed_video: 慢放后的视频路径
            timeline_diffs: 时间轴差异列表
            
        Returns:
            切割后的片段列表（包含字幕片段和间隔片段）
        """
        print("\n✂️  按更新SRT切割慢放后的视频（包含间隔）...")
        
        segments = []
        segment_counter = 0
        
        # 获取慢放后视频的总时长
        slowed_video_duration = self._get_video_duration_from_file(slowed_video)
        
        # 0. 切割第一个字幕之前的初始间隔（如果存在）
        if len(timeline_diffs) > 0:
            first_start = timeline_diffs[0].updated_entry.start_sec
            if first_start > 0.1:
                segment_counter += 1
                initial_gap_output = self.segments_dir / f"segment_{segment_counter:04d}_initial_gap.mp4"
                
                print(f"切割开头间隔: 0.00s - {first_start:.2f}s")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(slowed_video),
                    '-ss', '0',
                    '-to', str(first_start),
                    '-c:v', 'libx264',
                    '-preset', self.quality_preset,
                    '-crf', '18',
                    '-an',  # 移除音频
                    '-avoid_negative_ts', 'make_zero',
                    str(initial_gap_output)
                ]
                
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                    segments.append(initial_gap_output)
                    print(f"  ✅ 开头间隔已添加")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠️ 切割开头间隔失败: {e}")
        
        # 1. 切割字幕片段和中间间隔
        for i, diff in enumerate(timeline_diffs):
            # 切割字幕片段
            segment_counter += 1
            subtitle_output = self.segments_dir / f"segment_{segment_counter:04d}_subtitle.mp4"
            
            print(f"切割字幕片段 {i+1}/{len(timeline_diffs)}: "
                  f"{diff.updated_entry.start_sec:.2f}s - {diff.updated_entry.end_sec:.2f}s")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', str(slowed_video),
                '-ss', str(diff.updated_entry.start_sec),
                '-to', str(diff.updated_entry.end_sec),
                '-c:v', 'libx264',
                '-preset', self.quality_preset,
                '-crf', '18',
                '-an',  # 移除音频
                '-avoid_negative_ts', 'make_zero',
                str(subtitle_output)
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                segments.append(subtitle_output)
            except subprocess.CalledProcessError as e:
                print(f"   ❌ 切割字幕片段失败: {e}")
                raise
            
            # 切割间隔片段（如果存在下一个字幕）
            if i < len(timeline_diffs) - 1:
                gap_start = diff.updated_entry.end_sec
                gap_end = timeline_diffs[i + 1].updated_entry.start_sec
                gap_duration = gap_end - gap_start
                
                if gap_duration > 0.1:
                    segment_counter += 1
                    gap_output = self.segments_dir / f"segment_{segment_counter:04d}_gap.mp4"
                    
                    print(f"  切割间隔: {gap_start:.2f}s - {gap_end:.2f}s")
                    
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', str(slowed_video),
                        '-ss', str(gap_start),
                        '-to', str(gap_end),
                        '-c:v', 'libx264',
                        '-preset', self.quality_preset,
                        '-crf', '18',
                        '-an',  # 移除音频
                        '-avoid_negative_ts', 'make_zero',
                        str(gap_output)
                    ]
                    
                    try:
                        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                        segments.append(gap_output)
                    except subprocess.CalledProcessError as e:
                        print(f"   ⚠️ 切割间隔失败: {e}")
        
        # 2. 切割尾部间隔（如果存在）
        if len(timeline_diffs) > 0 and slowed_video_duration > 0:
            last_end = timeline_diffs[-1].updated_entry.end_sec
            tail_gap_duration = slowed_video_duration - last_end
            
            if tail_gap_duration > 0.1:
                segment_counter += 1
                tail_gap_output = self.segments_dir / f"segment_{segment_counter:04d}_tail_gap.mp4"
                
                print(f"切割尾部间隔: {last_end:.2f}s - {slowed_video_duration:.2f}s")
                
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(slowed_video),
                    '-ss', str(last_end),
                    '-to', str(slowed_video_duration),
                    '-c:v', 'libx264',
                    '-preset', self.quality_preset,
                    '-crf', '18',
                    '-an',  # 移除音频
                    '-avoid_negative_ts', 'make_zero',
                    str(tail_gap_output)
                ]
                
                try:
                    subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True)
                    segments.append(tail_gap_output)
                    print(f"  ✅ 尾部间隔已添加")
                except subprocess.CalledProcessError as e:
                    print(f"  ⚠️ 切割尾部间隔失败: {e}")
        
        print(f"\n✅ 切割完成: {len(segments)} 个片段（包含字幕和间隔）")
        return segments


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="视频时间轴同步处理器")
    parser.add_argument("--video", required=True, help="原始视频文件路径")
    parser.add_argument("--original-srt", required=True, help="原始SRT文件路径")
    parser.add_argument("--audio", required=True, help="更新后的音频文件路径")
    parser.add_argument("--updated-srt", required=True, help="更新后的SRT文件路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--max-slowdown", type=float, default=2.0, help="最大慢放倍率")
    parser.add_argument("--quality", default="medium", choices=['fast', 'medium', 'high'], help="质量预设")
    parser.add_argument("--no-interpolation", action='store_true', help="禁用帧插值")
    
    args = parser.parse_args()
    
    processor = VideoTimelineSyncProcessor(
        original_video_path=args.video,
        original_srt_path=args.original_srt,
        updated_audio_path=args.audio,
        updated_srt_path=args.updated_srt,
        output_dir=args.output_dir,
        max_slowdown_ratio=args.max_slowdown,
        quality_preset=args.quality,
        enable_frame_interpolation=not args.no_interpolation
    )
    
    result = processor.process()
    
    if result['success']:
        print(f"\n✅ 成功！输出文件: {result['output_path']}")
    else:
        print(f"\n❌ 失败: {result.get('error', '未知错误')}")
        exit(1)
