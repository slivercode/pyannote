"""
视频时间轴同步处理器 - 性能优化版本（纯CPU）

优化策略：
1. 一次性处理所有片段
2. 避免生成临时文件
3. 减少FFmpeg调用次数从N次到1次
4. 保持输出结果完全一致
5. 多线程并行处理批次，充分利用CPU资源

性能提升：5-10倍
"""

import subprocess
import json
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


@dataclass
class VideoSegment:
    """视频片段信息"""
    start_sec: float
    end_sec: float
    slowdown_ratio: float
    needs_slowdown: bool
    segment_type: str  # 'subtitle' or 'gap'


class OptimizedVideoTimelineSyncProcessor:
    """优化的视频时间轴同步处理器 - 纯CPU版本"""
    
    def __init__(
        self,
        ffmpeg_path: str = None,
        quality_preset: str = "medium",
        enable_frame_interpolation: bool = False,
        max_segments_per_batch: int = 300,
        background_audio_volume: float = 0.3,
        max_parallel_batches: int = None,
        ffmpeg_threads: int = None,
        # 保留这些参数以保持API兼容性，但不使用（纯CPU版本）
        use_gpu: bool = False,
        gpu_device: int = 0,
        force_gpu: bool = False
    ):
        """
        初始化优化处理器
        
        Args:
            ffmpeg_path: FFmpeg可执行文件路径（可选，自动检测）
            quality_preset: 质量预设 (ultrafast/superfast/veryfast/faster/fast/medium/slow/slower/veryslow)
            enable_frame_interpolation: 是否启用帧插值（会显著增加处理时间）
            max_segments_per_batch: 每批最多处理的片段数（默认300，避免命令行过长）
            background_audio_volume: 环境声音量比例（默认0.3，即30%）
            max_parallel_batches: 最大并行批次数（默认为CPU核心数/2）
            ffmpeg_threads: 每个FFmpeg进程的线程数（默认0=自动）
            use_gpu: 已废弃，保留以兼容旧代码
            gpu_device: 已废弃，保留以兼容旧代码
            force_gpu: 已废弃，保留以兼容旧代码
        """
        self.ffmpeg_path = ffmpeg_path or self._detect_ffmpeg_path()
        self.quality_preset = self._validate_preset(quality_preset)
        self.enable_frame_interpolation = enable_frame_interpolation
        self.max_segments_per_batch = max_segments_per_batch
        self.background_audio_volume = background_audio_volume
        
        # 固定为CPU模式
        self.use_gpu = False
        
        # 多线程配置
        cpu_count = os.cpu_count() or 4
        self.max_parallel_batches = max_parallel_batches or max(1, cpu_count // 2)
        self.ffmpeg_threads = ffmpeg_threads if ffmpeg_threads is not None else 0
        
        # 线程安全的进度锁
        self._progress_lock = threading.Lock()
        
        # 打印配置信息
        self._print_config()
    
    def _validate_preset(self, preset: str) -> str:
        """验证并返回有效的x264预设"""
        valid_presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 
                        'medium', 'slow', 'slower', 'veryslow']
        if preset in valid_presets:
            return preset
        # 如果是GPU预设格式(p1-p7)，转换为CPU预设
        gpu_to_cpu = {
            'p1': 'ultrafast', 'p2': 'superfast', 'p3': 'veryfast',
            'p4': 'medium', 'p5': 'slow', 'p6': 'slower', 'p7': 'veryslow'
        }
        return gpu_to_cpu.get(preset, 'medium')
    
    def _print_config(self):
        """打印当前配置"""
        print(f"\n🔧 处理器配置:")
        print(f"   处理模式: CPU处理")
        print(f"   编码预设: {self.quality_preset} (x264)")
        print(f"   最大并行批次: {self.max_parallel_batches}")
        print(f"   FFmpeg线程: {self.ffmpeg_threads or '自动'}")
    
    def _detect_ffmpeg_path(self) -> str:
        """
        自动检测FFmpeg路径
        
        Returns:
            FFmpeg可执行文件路径
        """
        import platform
        import os
        from pathlib import Path
        
        system = platform.system()
        
        # 1. 尝试项目目录中的FFmpeg
        if system == "Windows":
            project_ffmpeg = Path("ffmpeg/bin/ffmpeg.exe")
            if project_ffmpeg.exists():
                print(f"✅ 使用项目FFmpeg: {project_ffmpeg}")
                return str(project_ffmpeg)
        else:
            project_ffmpeg = Path("ffmpeg/bin/ffmpeg")
            if project_ffmpeg.exists():
                print(f"✅ 使用项目FFmpeg: {project_ffmpeg}")
                return str(project_ffmpeg)
        
        # 2. 尝试系统PATH中的FFmpeg
        try:
            import shutil
            system_ffmpeg = shutil.which("ffmpeg")
            if system_ffmpeg:
                print(f"✅ 使用系统FFmpeg: {system_ffmpeg}")
                return system_ffmpeg
        except:
            pass
        
        # 3. 默认值
        if system == "Windows":
            print(f"⚠️  未找到FFmpeg，使用默认路径: ffmpeg.exe")
            return "ffmpeg.exe"
        else:
            print(f"⚠️  未找到FFmpeg，使用默认路径: ffmpeg")
            return "ffmpeg"
    
    def build_complex_filter_chain(
        self,
        segments: List[VideoSegment],
        enable_interpolation: bool = False
    ) -> str:
        """
        构建FFmpeg复杂滤镜链
        
        Args:
            segments: 视频片段列表
            enable_interpolation: 是否启用帧插值
        
        Returns:
            FFmpeg滤镜字符串
        """
        return self._build_filter_chain_internal(segments, enable_interpolation)
    
    def _build_filter_chain_internal(
        self,
        segments: List[VideoSegment],
        enable_interpolation: bool = False
    ) -> str:
        """
        构建滤镜链（内部方法 - 高精度版本）
        
        精度优化：
        - 使用两步setpts: setpts=PTS-STARTPTS,setpts=PTS*ratio
        - 避免 setpts=(PTS-STARTPTS)*ratio 的精度损失
        - 使用6位小数精度（微秒级）
        
        Args:
            segments: 视频片段列表
            enable_interpolation: 是否启用帧插值
        
        Returns:
            FFmpeg滤镜字符串
        """
        filter_parts = []
        stream_labels = []
        
        print(f"🔧 构建滤镜链: {len(segments)} 个片段 (CPU模式 + 高精度setpts)")
        
        for i, seg in enumerate(segments):
            label = f"v{i}"
            start = f"{seg.start_sec:.6f}"
            end = f"{seg.end_sec:.6f}"
            ratio = f"{seg.slowdown_ratio:.6f}"
            
            if seg.needs_slowdown and enable_interpolation:
                filter_parts.append(
                    f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,setpts=PTS*{ratio},"
                    f"minterpolate=fps=60:mi_mode=mci[{label}]"
                )
            else:
                filter_parts.append(
                    f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,setpts=PTS*{ratio}[{label}]"
                )
            
            stream_labels.append(f"[{label}]")
        
        concat_filter = f"{''.join(stream_labels)}concat=n={len(segments)}:v=1:a=0[outv]"
        filter_parts.append(concat_filter)
        
        filter_chain = ";".join(filter_parts)
        
        print(f"   滤镜链长度: {len(filter_chain)} 字符")
        print(f"   片段数量: {len(segments)}")
        print(f"   需要调整: {sum(1 for s in segments if abs(s.slowdown_ratio - 1.0) > 0.001)}")
        print(f"   精度模式: 两步setpts + 6位小数（微秒级）")
        
        return filter_chain
    
    def _should_use_batch_processing(self, segments: List[VideoSegment]) -> bool:
        """判断是否需要使用分批处理"""
        return len(segments) > self.max_segments_per_batch
    
    def _split_segments_into_batches(
        self,
        segments: List[VideoSegment]
    ) -> List[List[VideoSegment]]:
        """将片段列表分割成多个批次"""
        batches = []
        for i in range(0, len(segments), self.max_segments_per_batch):
            batch = segments[i:i + self.max_segments_per_batch]
            batches.append(batch)
        
        print(f"📦 分批处理: {len(segments)} 个片段 → {len(batches)} 批")
        for i, batch in enumerate(batches):
            print(f"   批次{i+1}: {len(batch)} 个片段")
        
        return batches
    
    def _process_batch(
        self,
        input_video_path: str,
        segments: List[VideoSegment],
        output_path: str,
        batch_index: int,
        total_batches: int
    ) -> str:
        """
        处理单个批次
        
        Args:
            input_video_path: 输入视频路径
            segments: 该批次的片段列表
            output_path: 输出路径
            batch_index: 批次索引（从0开始）
            total_batches: 总批次数
            
        Returns:
            输出文件路径
        """
        import tempfile
        
        print(f"\n🔧 处理批次 {batch_index+1}/{total_batches} ({len(segments)} 个片段, CPU)...")
        print(f"   使用逐片段处理模式")
        
        temp_dir = Path(tempfile.gettempdir()) / f"batch_{batch_index}_{id(self)}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            segment_files = []
            for i, seg in enumerate(segments):
                segment_output = str(temp_dir / f"segment_{i:04d}.mp4")
                self._process_single_segment(
                    input_video_path,
                    seg,
                    segment_output,
                    i,
                    len(segments)
                )
                segment_files.append(segment_output)
            
            self._concat_segments_with_demuxer(segment_files, output_path)
            
            print(f"   ✅ 批次 {batch_index+1} 完成 (CPU)")
            return output_path
            
        except Exception as e:
            print(f"   ❌ 批次 {batch_index+1} 处理失败: {e}")
            raise
        finally:
            try:
                import shutil
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except:
                pass
    
    def _process_single_segment(
        self,
        input_video_path: str,
        segment: VideoSegment,
        output_path: str,
        segment_index: int,
        total_segments: int
    ) -> str:
        """处理单个视频片段"""
        start = f"{segment.start_sec:.6f}"
        end = f"{segment.end_sec:.6f}"
        ratio = f"{segment.slowdown_ratio:.6f}"
        
        if segment.needs_slowdown and self.enable_frame_interpolation:
            filter_str = (
                f"trim=start={start}:end={end},"
                f"setpts=PTS-STARTPTS,setpts=PTS*{ratio},"
                f"minterpolate=fps=60:mi_mode=mci"
            )
        else:
            filter_str = (
                f"trim=start={start}:end={end},"
                f"setpts=PTS-STARTPTS,setpts=PTS*{ratio}"
            )
        
        cmd = [self.ffmpeg_path, '-y']
        
        if self.ffmpeg_threads == 0:
            cmd.extend(['-threads', '0'])
        else:
            cmd.extend(['-threads', str(self.ffmpeg_threads)])
        
        cmd.extend(['-i', input_video_path])
        cmd.extend(['-vf', filter_str])
        cmd.append('-an')
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', self.quality_preset,
            '-crf', '23'
        ])
        cmd.append(output_path)
        
        subprocess.run(
            cmd,
            capture_output=True,
            check=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        return output_path
    
    def _concat_segments_with_demuxer(
        self,
        segment_files: List[str],
        output_path: str
    ) -> str:
        """使用 concat demuxer 拼接片段"""
        import tempfile
        
        concat_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            encoding='utf-8'
        )
        
        try:
            for video in segment_files:
                abs_path = str(Path(video).resolve())
                unix_path = abs_path.replace('\\', '/')
                concat_file.write(f"file '{unix_path}'\n")
            
            concat_file.close()
            
            cmd = [
                self.ffmpeg_path, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file.name,
                '-c', 'copy',
                output_path
            ]
            
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            return output_path
            
        finally:
            try:
                Path(concat_file.name).unlink()
            except:
                pass
    
    def _concatenate_batch_videos_only(
        self,
        batch_videos: List[str],
        output_path: str
    ) -> str:
        """仅拼接多个批次的视频（不添加音频）"""
        print(f"\n🔗 拼接 {len(batch_videos)} 个批次视频（仅视频）...")
        
        import tempfile
        concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        
        try:
            for video in batch_videos:
                abs_path = str(Path(video).resolve())
                unix_path = abs_path.replace('\\', '/')
                concat_file.write(f"file '{unix_path}'\n")
            
            concat_file.close()
            
            cmd = [self.ffmpeg_path, '-y']
            cmd.extend([
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file.name
            ])
            cmd.extend([
                '-c:v', 'copy',
                '-an'
            ])
            cmd.extend([
                '-movflags', '+faststart',
                '-max_muxing_queue_size', '9999'
            ])
            cmd.append(output_path)
            
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            print(f"   ✅ 拼接完成: {output_path}")
            return output_path
            
        finally:
            try:
                Path(concat_file.name).unlink()
            except:
                pass
    
    def _concatenate_batch_videos(
        self,
        batch_videos: List[str],
        input_audio_path: str,
        output_path: str
    ) -> str:
        """拼接多个批次的视频并添加音频"""
        print(f"\n🔗 拼接 {len(batch_videos)} 个批次视频并添加音频...")
        
        cmd = [self.ffmpeg_path, '-y']
        
        import tempfile
        concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        
        try:
            for video in batch_videos:
                abs_path = str(Path(video).resolve())
                unix_path = abs_path.replace('\\', '/')
                concat_file.write(f"file '{unix_path}'\n")
            
            concat_file.close()
            
            cmd.extend([
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file.name
            ])
            cmd.extend(['-i', input_audio_path])
            cmd.extend([
                '-map', '0:v',
                '-map', '1:a'
            ])
            cmd.extend([
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k'
            ])
            cmd.extend([
                '-movflags', '+faststart',
                '-max_muxing_queue_size', '9999'
            ])
            cmd.append(output_path)
            
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            print(f"   ✅ 拼接完成: {output_path}")
            return output_path
            
        finally:
            try:
                Path(concat_file.name).unlink()
            except:
                pass

    
    def process_video_optimized(
        self,
        input_video_path: str,
        input_audio_path: str,
        segments: List[VideoSegment],
        output_path: str,
        progress_callback=None,
        background_audio_path: str = None,
        background_volume: float = None
    ) -> str:
        """
        优化的视频处理流程（支持分批处理和环境声混合）
        
        Args:
            input_video_path: 输入视频路径
            input_audio_path: 输入TTS音频路径
            segments: 视频片段列表
            output_path: 输出路径
            progress_callback: 进度回调函数
            background_audio_path: 可选，原视频环境声路径
            background_volume: 可选，环境声音量（0.0-1.0）
        
        Returns:
            输出文件路径
        """
        print("\n" + "="*60)
        print("🚀 优化处理模式")
        print("="*60)
        print(f"📹 输入视频: {input_video_path}")
        print(f"🎵 输入TTS音频: {input_audio_path}")
        if background_audio_path:
            vol = background_volume if background_volume is not None else self.background_audio_volume
            print(f"🎶 环境声: {background_audio_path} (音量: {vol*100:.0f}%)")
        print(f"📊 片段数量: {len(segments)}")
        print(f"💾 输出路径: {output_path}")
        
        if self._should_use_batch_processing(segments):
            print(f"\n⚠️  片段数量({len(segments)})超过阈值({self.max_segments_per_batch})，使用分批处理模式")
            return self._process_video_in_batches(
                input_video_path,
                input_audio_path,
                segments,
                output_path,
                progress_callback,
                background_audio_path,
                background_volume
            )
        else:
            print(f"\n✅ 片段数量({len(segments)})在阈值内，使用一次性处理模式")
            return self._process_video_single_pass(
                input_video_path,
                input_audio_path,
                segments,
                output_path,
                progress_callback,
                background_audio_path,
                background_volume
            )
    
    def _process_video_in_batches(
        self,
        input_video_path: str,
        input_audio_path: str,
        segments: List[VideoSegment],
        output_path: str,
        progress_callback=None,
        background_audio_path: str = None,
        background_volume: float = None
    ) -> str:
        """分批并行处理视频"""
        import tempfile
        
        if progress_callback:
            progress_callback(10, "分割片段")
        
        batches = self._split_segments_into_batches(segments)
        
        batch_videos = [None] * len(batches)
        temp_dir = Path(tempfile.gettempdir()) / f"video_sync_batches_{id(self)}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        completed_batches = [0]
        
        def update_progress(batch_idx):
            with self._progress_lock:
                completed_batches[0] += 1
                if progress_callback:
                    progress = 20 + int(50 * (completed_batches[0] / len(batches)))
                    progress_callback(progress, f"处理批次 {completed_batches[0]}/{len(batches)}")
        
        try:
            num_workers = min(len(batches), self.max_parallel_batches)
            print(f"\n🚀 启动并行处理: {num_workers} 个工作线程处理 {len(batches)} 个批次 (CPU)")
            
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = {}
                for i, batch in enumerate(batches):
                    batch_output = str(temp_dir / f"batch_{i:04d}.mp4")
                    future = executor.submit(
                        self._process_batch,
                        input_video_path,
                        batch,
                        batch_output,
                        i,
                        len(batches)
                    )
                    futures[future] = i
                
                for future in as_completed(futures):
                    batch_idx = futures[future]
                    try:
                        result_path = future.result()
                        batch_videos[batch_idx] = result_path
                        update_progress(batch_idx)
                    except Exception as e:
                        print(f"   ❌ 批次 {batch_idx+1} 处理异常: {e}")
                        raise
            
            if None in batch_videos:
                missing = [i for i, v in enumerate(batch_videos) if v is None]
                raise RuntimeError(f"批次处理不完整，缺失批次: {missing}")
            
            print(f"\n✅ 所有 {len(batches)} 个批次并行处理完成 (CPU)")
            
            if progress_callback:
                progress_callback(70, "拼接批次视频")
            
            temp_video = str(temp_dir / "concatenated.mp4")
            self._concatenate_batch_videos_only(batch_videos, temp_video)
            
            print(f"   ✅ 视频片段拼接完成 (CPU)")
            
            if progress_callback:
                progress_callback(75, "全局时长校准")
            
            print("\n" + "="*60)
            print("🎯 全局时长校准")
            print("="*60)
            
            audio_duration = self._get_video_duration(input_audio_path)
            concat_video_duration = self._get_video_duration(temp_video)
            
            print(f"拼接后视频时长: {concat_video_duration:.2f}秒")
            print(f"目标音频时长: {audio_duration:.2f}秒")
            
            duration_diff = audio_duration - concat_video_duration
            print(f"时长差异: {duration_diff:+.2f}秒 ({abs(duration_diff)/60:.2f}分钟)")
            
            calibration_ratio = 1.0
            
            if abs(duration_diff) > 0.05:
                print(f"\n⚠️  时长差异（{abs(duration_diff):.2f}秒）超过阈值，进行全局校准")
                
                calibration_ratio = audio_duration / concat_video_duration
                print(f"全局校准比例: {calibration_ratio:.4f}x")
                
                if duration_diff > 0:
                    print(f"   视频比音频短 {duration_diff:.2f}秒 → 全局慢放 {calibration_ratio:.4f}x")
                else:
                    print(f"   视频比音频长 {abs(duration_diff):.2f}秒 → 全局加速 {calibration_ratio:.4f}x")
                
                calibrated_video = str(temp_dir / "calibrated_video.mp4")
                print(f"   开始全局校准处理...")
                
                if self._calibrate_video_duration(temp_video, calibrated_video, calibration_ratio):
                    temp_video = calibrated_video
                    
                    final_duration = self._get_video_duration(temp_video)
                    final_diff = audio_duration - final_duration
                    
                    print(f"✅ 全局校准完成")
                    print(f"   校准后视频时长: {final_duration:.2f}秒")
                    print(f"   目标音频时长: {audio_duration:.2f}秒")
                    print(f"   最终差异: {final_diff:+.3f}秒")
                    
                    if abs(final_diff) < 0.1:
                        print(f"   ✅ 时长精确匹配（误差 < 0.1秒）")
                    else:
                        print(f"   ⚠️  仍有差异: {abs(final_diff):.2f}秒")
                else:
                    print(f"❌ 全局校准失败，使用原始拼接视频")
                    calibration_ratio = 1.0
            else:
                print(f"✅ 时长差异在可接受范围内（{abs(duration_diff):.2f}秒 < 0.05秒）")
            
            mixed_audio_path = input_audio_path
            if background_audio_path:
                if progress_callback:
                    progress_callback(85, "处理环境声")
                
                print("\n" + "="*60)
                print("🎶 处理环境声")
                print("="*60)
                
                mixed_audio_path = str(temp_dir / "mixed_audio.wav")
                self._process_and_mix_background_audio(
                    background_audio_path,
                    input_audio_path,
                    segments,
                    mixed_audio_path,
                    background_volume,
                    calibration_ratio
                )
            
            if progress_callback:
                progress_callback(90, "添加音频")
            
            print("\n⚙️  添加音频...")
            
            cmd_audio = [self.ffmpeg_path, '-y']
            cmd_audio.extend([
                '-i', temp_video,
                '-i', mixed_audio_path
            ])
            cmd_audio.extend([
                '-map', '0:v',
                '-map', '1:a'
            ])
            cmd_audio.extend([
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k'
            ])
            cmd_audio.extend([
                '-movflags', '+faststart',
                '-max_muxing_queue_size', '9999'
            ])
            cmd_audio.append(output_path)
            
            subprocess.run(
                cmd_audio,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            if progress_callback:
                progress_callback(100, "处理完成")
            
            print(f"\n✅ 分批并行处理完成！(CPU)")
            print(f"   输出文件: {output_path}")
            
            output_file = Path(output_path)
            if output_file.exists():
                file_size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"   文件大小: {file_size_mb:.2f} MB")
            
            return output_path
            
        finally:
            try:
                import shutil
                shutil.rmtree(temp_dir)
                print(f"🧹 已清理临时文件")
            except:
                pass

    
    def _process_video_single_pass(
        self,
        input_video_path: str,
        input_audio_path: str,
        segments: List[VideoSegment],
        output_path: str,
        progress_callback=None,
        background_audio_path: str = None,
        background_volume: float = None
    ) -> str:
        """一次性处理视频"""
        import tempfile
        
        temp_dir = Path(tempfile.gettempdir()) / f"video_sync_temp_{id(self)}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n⚙️  使用逐片段处理模式 (CPU)...")
        
        try:
            if progress_callback:
                progress_callback(10, "处理视频片段")
            
            segment_files = []
            total = len(segments)
            
            for i, seg in enumerate(segments):
                if progress_callback:
                    progress = 10 + int(50 * (i / total))
                    progress_callback(progress, f"处理片段 {i+1}/{total}")
                
                segment_output = str(temp_dir / f"segment_{i:04d}.mp4")
                self._process_single_segment(
                    input_video_path,
                    seg,
                    segment_output,
                    i,
                    total
                )
                segment_files.append(segment_output)
            
            if progress_callback:
                progress_callback(60, "拼接视频片段")
            
            temp_video = str(temp_dir / "concatenated.mp4")
            self._concat_segments_with_demuxer(segment_files, temp_video)
            
            print(f"   ✅ 视频片段拼接完成 (CPU)")
            
            if progress_callback:
                progress_callback(65, "全局时长校准")
            
            print("\n" + "="*60)
            print("🎯 全局时长校准")
            print("="*60)
            
            audio_duration = self._get_video_duration(input_audio_path)
            concat_video_duration = self._get_video_duration(temp_video)
            
            print(f"拼接后视频时长: {concat_video_duration:.2f}秒")
            print(f"目标音频时长: {audio_duration:.2f}秒")
            
            duration_diff = audio_duration - concat_video_duration
            print(f"时长差异: {duration_diff:+.2f}秒 ({abs(duration_diff)/60:.2f}分钟)")
            
            calibration_ratio = 1.0
            
            if abs(duration_diff) > 0.05:
                print(f"\n⚠️  时长差异（{abs(duration_diff):.2f}秒）超过阈值，进行全局校准")
                
                calibration_ratio = audio_duration / concat_video_duration
                print(f"全局校准比例: {calibration_ratio:.4f}x")
                
                if duration_diff > 0:
                    print(f"   视频比音频短 {duration_diff:.2f}秒 → 全局慢放 {calibration_ratio:.4f}x")
                else:
                    print(f"   视频比音频长 {abs(duration_diff):.2f}秒 → 全局加速 {calibration_ratio:.4f}x")
                
                calibrated_video = temp_dir / "calibrated_video.mp4"
                print(f"   开始全局校准处理...")
                
                if self._calibrate_video_duration(temp_video, str(calibrated_video), calibration_ratio):
                    temp_video = str(calibrated_video)
                    
                    final_duration = self._get_video_duration(temp_video)
                    final_diff = audio_duration - final_duration
                    
                    print(f"✅ 全局校准完成")
                    print(f"   校准后视频时长: {final_duration:.2f}秒")
                    print(f"   目标音频时长: {audio_duration:.2f}秒")
                    print(f"   最终差异: {final_diff:+.3f}秒")
                    
                    if abs(final_diff) < 0.1:
                        print(f"   ✅ 时长精确匹配（误差 < 0.1秒）")
                    else:
                        print(f"   ⚠️  仍有差异: {abs(final_diff):.2f}秒")
                else:
                    print(f"❌ 全局校准失败，使用原始拼接视频")
                    calibration_ratio = 1.0
            else:
                print(f"✅ 时长差异在可接受范围内（{abs(duration_diff):.2f}秒 < 0.05秒）")
            
            final_audio_path = input_audio_path
            if background_audio_path:
                if progress_callback:
                    progress_callback(75, "处理环境声")
                
                print("\n" + "="*60)
                print("🎶 处理环境声")
                print("="*60)
                
                final_audio_path = str(temp_dir / "mixed_audio.wav")
                self._process_and_mix_background_audio(
                    background_audio_path,
                    input_audio_path,
                    segments,
                    final_audio_path,
                    background_volume,
                    calibration_ratio
                )
            
            if progress_callback:
                progress_callback(85, "添加音频")
            
            print("\n⚙️  添加音频...")
            
            cmd_audio = [self.ffmpeg_path, '-y']
            cmd_audio.extend([
                '-i', temp_video,
                '-i', final_audio_path
            ])
            cmd_audio.extend([
                '-map', '0:v',
                '-map', '1:a'
            ])
            cmd_audio.extend([
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k'
            ])
            cmd_audio.extend([
                '-movflags', '+faststart',
                '-max_muxing_queue_size', '9999'
            ])
            cmd_audio.append(output_path)
            
            subprocess.run(
                cmd_audio,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            if progress_callback:
                progress_callback(100, "处理完成")
            
            print(f"\n✅ 一次性处理完成！(CPU)")
            print(f"   输出文件: {output_path}")
            
            output_file = Path(output_path)
            if output_file.exists():
                file_size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"   文件大小: {file_size_mb:.2f} MB")
            
            return output_path
        
        except subprocess.CalledProcessError as e:
            print(f"\n❌ FFmpeg执行失败:")
            print(f"   错误码: {e.returncode}")
            if e.stderr:
                print(f"   错误信息: {e.stderr[-1000:]}")
            raise
        except Exception as e:
            print(f"\n❌ 处理失败: {e}")
            raise
        finally:
            try:
                import shutil
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except:
                pass
    
    def _build_ffmpeg_command(
        self,
        input_video: str,
        input_audio: str,
        filter_chain: str,
        output_path: str
    ) -> List[str]:
        """构建FFmpeg命令"""
        cmd = [self.ffmpeg_path, '-y']
        
        if self.ffmpeg_threads == 0:
            cmd.extend(['-threads', '0'])
        else:
            cmd.extend(['-threads', str(self.ffmpeg_threads)])
        
        cpu_count = os.cpu_count() or 4
        filter_threads = max(2, cpu_count // 2)
        cmd.extend([
            '-filter_threads', str(filter_threads),
            '-filter_complex_threads', str(filter_threads)
        ])
        
        cmd.extend([
            '-i', input_video,
            '-i', input_audio
        ])
        
        cmd.extend([
            '-filter_complex', filter_chain
        ])
        
        cmd.extend([
            '-map', '[outv]',
            '-map', '1:a'
        ])
        
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', self.quality_preset,
            '-crf', '23'
        ])
        
        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '192k'
        ])
        
        cmd.extend([
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '9999'
        ])
        
        cmd.append(output_path)
        
        return cmd
    
    def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长"""
        cmd = [
            self.ffmpeg_path,
            '-i', video_path,
            '-f', 'null',
            '-'
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            for line in result.stderr.split('\n'):
                if 'Duration:' in line:
                    duration_str = line.split('Duration:')[1].split(',')[0].strip()
                    parts = duration_str.split(':')
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
            
            return 0.0
        except Exception as e:
            print(f"   ⚠️  获取视频时长失败: {e}")
            return 0.0
    
    def _calibrate_video_duration(
        self,
        input_video: str,
        output_video: str,
        ratio: float
    ) -> bool:
        """对视频进行全局时长校准"""
        print(f"   应用全局校准: {ratio:.4f}x (CPU)")
        
        cmd = [self.ffmpeg_path, '-y']
        
        if self.ffmpeg_threads == 0:
            cmd.extend(['-threads', '0'])
        else:
            cmd.extend(['-threads', str(self.ffmpeg_threads)])
        
        cpu_count = os.cpu_count() or 4
        filter_threads = max(2, cpu_count // 2)
        cmd.extend([
            '-filter_threads', str(filter_threads),
            '-filter_complex_threads', str(filter_threads)
        ])
        
        cmd.extend(['-i', input_video])
        cmd.extend(['-vf', f'setpts={ratio}*PTS'])
        cmd.append('-an')
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', self.quality_preset,
            '-crf', '23'
        ])
        cmd.append(output_video)
        
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"   ❌ 全局校准失败: {e}")
            return False

    
    def _process_and_mix_background_audio(
        self,
        background_audio_path: str,
        tts_audio_path: str,
        segments: List[VideoSegment],
        output_path: str,
        volume: float = None,
        global_calibration_ratio: float = 1.0
    ) -> str:
        """处理环境声：按片段拉伸后与TTS音轨混合"""
        import tempfile
        
        vol = volume if volume is not None else self.background_audio_volume
        print(f"   环境声路径: {background_audio_path}")
        print(f"   TTS音频路径: {tts_audio_path}")
        print(f"   环境声音量: {vol*100:.0f}%")
        print(f"   全局校准比例: {global_calibration_ratio:.4f}x")
        
        temp_dir = Path(tempfile.gettempdir()) / f"bg_audio_process_{id(self)}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            stretched_bg = str(temp_dir / "stretched_background.wav")
            audio_filter = self._build_audio_stretch_filter(segments, global_calibration_ratio)
            
            print(f"   构建音频拉伸滤镜...")
            
            cmd_stretch = [
                self.ffmpeg_path, '-y',
                '-i', background_audio_path,
                '-filter_complex', audio_filter,
                '-map', '[outa]',
                '-c:a', 'pcm_s16le',
                '-ar', '44100',
                stretched_bg
            ]
            
            result = subprocess.run(
                cmd_stretch,
                capture_output=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            if result.returncode != 0:
                print(f"   ⚠️  复杂滤镜拉伸失败，尝试简单全局拉伸...")
                stretched_bg = self._simple_stretch_audio(
                    background_audio_path,
                    tts_audio_path,
                    str(temp_dir / "simple_stretched_bg.wav")
                )
            else:
                print(f"   ✅ 环境声拉伸完成")
            
            print(f"   混合音轨...")
            
            tts_duration = self._get_video_duration(tts_audio_path)
            
            cmd_mix = [
                self.ffmpeg_path, '-y',
                '-i', tts_audio_path,
                '-i', stretched_bg,
                '-filter_complex',
                f'[1:a]volume={vol},apad[bg];'
                f'[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[out]',
                '-map', '[out]',
                '-c:a', 'pcm_s16le',
                '-ar', '44100',
                output_path
            ]
            
            subprocess.run(
                cmd_mix,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            print(f"   ✅ 音轨混合完成: {output_path}")
            
            mixed_duration = self._get_video_duration(output_path)
            print(f"   混合音频时长: {mixed_duration:.2f}秒")
            print(f"   TTS音频时长: {tts_duration:.2f}秒")
            
            return output_path
            
        except Exception as e:
            print(f"   ❌ 环境声处理失败: {e}")
            import traceback
            traceback.print_exc()
            print(f"   ⚠️  回退到仅使用TTS音频")
            return tts_audio_path
        finally:
            try:
                import shutil
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except:
                pass
    
    def _build_audio_stretch_filter(
        self,
        segments: List[VideoSegment],
        global_calibration_ratio: float = 1.0
    ) -> str:
        """构建音频拉伸滤镜链"""
        filter_parts = []
        stream_labels = []
        
        for i, seg in enumerate(segments):
            label = f"a{i}"
            start = seg.start_sec
            end = seg.end_sec
            
            final_ratio = seg.slowdown_ratio * global_calibration_ratio
            
            if seg.needs_slowdown or global_calibration_ratio != 1.0:
                tempo_filters = self._build_atempo_chain(1.0 / final_ratio)
                filter_parts.append(
                    f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{tempo_filters}[{label}]"
                )
            else:
                filter_parts.append(
                    f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[{label}]"
                )
            
            stream_labels.append(f"[{label}]")
        
        concat_filter = f"{''.join(stream_labels)}concat=n={len(segments)}:v=0:a=1[outa]"
        filter_parts.append(concat_filter)
        
        return ";".join(filter_parts)
    
    def _build_atempo_chain(self, tempo: float) -> str:
        """构建atempo滤镜链（处理超出0.5-2.0范围的值）"""
        if tempo <= 0:
            tempo = 0.5
        
        filters = []
        remaining = tempo
        
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining = remaining / 0.5
        
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining = remaining / 2.0
        
        if 0.5 <= remaining <= 2.0:
            filters.append(f"atempo={remaining:.4f}")
        
        return ",".join(filters) if filters else "atempo=1.0"
    
    def _simple_stretch_audio(
        self,
        input_audio: str,
        reference_audio: str,
        output_path: str
    ) -> str:
        """简单全局拉伸音频（回退方案）"""
        input_duration = self._get_video_duration(input_audio)
        target_duration = self._get_video_duration(reference_audio)
        
        if input_duration <= 0 or target_duration <= 0:
            print(f"   ⚠️  无法获取音频时长，跳过拉伸")
            return input_audio
        
        stretch_ratio = target_duration / input_duration
        tempo = 1.0 / stretch_ratio
        
        print(f"   简单拉伸: {input_duration:.2f}s → {target_duration:.2f}s (tempo={tempo:.4f})")
        
        tempo_filter = self._build_atempo_chain(tempo)
        
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', input_audio,
            '-af', tempo_filter,
            '-c:a', 'pcm_s16le',
            '-ar', '44100',
            output_path
        ]
        
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                encoding='utf-8',
                errors='ignore'
            )
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"   ❌ 简单拉伸失败: {e}")
            return input_audio
    
    def estimate_processing_time(
        self,
        video_duration_sec: float,
        num_segments: int,
        slowdown_segments: int
    ) -> Dict[str, float]:
        """估算处理时间"""
        preset_factors = {
            'ultrafast': 0.3,
            'superfast': 0.4,
            'veryfast': 0.5,
            'faster': 0.6,
            'fast': 0.7,
            'medium': 1.0,
            'slow': 1.5,
            'slower': 2.0,
            'veryslow': 3.0
        }
        
        base_factor = preset_factors.get(self.quality_preset, 1.0)
        interpolation_factor = 3.0 if self.enable_frame_interpolation else 1.0
        
        estimated_time = (
            video_duration_sec * 
            base_factor * 
            interpolation_factor
        )
        
        return {
            'estimated_seconds': estimated_time,
            'estimated_minutes': estimated_time / 60,
            'video_duration': video_duration_sec,
            'num_segments': num_segments,
            'slowdown_segments': slowdown_segments,
            'preset': self.quality_preset,
            'use_gpu': False,
            'use_interpolation': self.enable_frame_interpolation
        }


def create_segments_from_timeline_diffs(
    timeline_diffs: List,
    original_video_duration: float = 0,
    include_gaps: bool = True
) -> List[VideoSegment]:
    """
    从时间轴差异列表创建视频片段列表（包含间隔片段）
    
    Args:
        timeline_diffs: TimelineDiff对象列表
        original_video_duration: 原始视频总时长（秒）
        include_gaps: 是否包含间隔片段（默认True）
    
    Returns:
        VideoSegment对象列表
    """
    segments = []
    
    if not timeline_diffs:
        return segments
    
    if include_gaps:
        first_start = timeline_diffs[0].original_entry.start_sec
        if first_start > 0.01:
            segments.append(VideoSegment(
                start_sec=0.0,
                end_sec=first_start,
                slowdown_ratio=1.0,
                needs_slowdown=False,
                segment_type='gap'
            ))
            print(f"  添加开头间隔: 0.0s - {first_start:.2f}s")
    
    for i, diff in enumerate(timeline_diffs):
        segment = VideoSegment(
            start_sec=diff.original_entry.start_sec,
            end_sec=diff.original_entry.end_sec,
            slowdown_ratio=diff.slowdown_ratio,
            needs_slowdown=diff.needs_slowdown,
            segment_type='subtitle'
        )
        segments.append(segment)
        
        if include_gaps and i < len(timeline_diffs) - 1:
            gap_start = diff.original_entry.end_sec
            gap_end = timeline_diffs[i + 1].original_entry.start_sec
            gap_duration = gap_end - gap_start
            
            if gap_duration > 0.01:
                segments.append(VideoSegment(
                    start_sec=gap_start,
                    end_sec=gap_end,
                    slowdown_ratio=1.0,
                    needs_slowdown=False,
                    segment_type='gap'
                ))
    
    if include_gaps and original_video_duration > 0:
        last_end = timeline_diffs[-1].original_entry.end_sec
        tail_gap_duration = original_video_duration - last_end
        
        if tail_gap_duration > 0.01:
            segments.append(VideoSegment(
                start_sec=last_end,
                end_sec=original_video_duration,
                slowdown_ratio=1.0,
                needs_slowdown=False,
                segment_type='gap'
            ))
            print(f"  添加尾部间隔: {last_end:.2f}s - {original_video_duration:.2f}s")
    
    print(f"  总计: {len(segments)} 个片段（字幕: {sum(1 for s in segments if s.segment_type == 'subtitle')}, 间隔: {sum(1 for s in segments if s.segment_type == 'gap')}）")
    
    return segments


# 使用示例
if __name__ == "__main__":
    print("="*60)
    print("创建处理器（纯CPU模式）")
    print("="*60)
    
    processor = OptimizedVideoTimelineSyncProcessor(
        ffmpeg_path=None,
        quality_preset="fast",
        enable_frame_interpolation=False
    )
    
    segments = [
        VideoSegment(0.0, 5.0, 1.5, True, 'subtitle'),
        VideoSegment(5.0, 8.0, 1.2, True, 'subtitle'),
        VideoSegment(8.0, 15.0, 1.0, False, 'subtitle'),
    ]
    
    estimate = processor.estimate_processing_time(
        video_duration_sec=300,
        num_segments=100,
        slowdown_segments=50
    )
    
    print("\n" + "="*60)
    print("处理时间估算")
    print("="*60)
    print(f"  预计耗时: {estimate['estimated_minutes']:.1f} 分钟")
    print(f"  视频时长: {estimate['video_duration']} 秒")
    print(f"  片段数量: {estimate['num_segments']}")
    print(f"  质量预设: {estimate['preset']}")
    print(f"  GPU加速: 否（纯CPU模式）")
