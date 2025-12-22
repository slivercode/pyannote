"""
视频合并模块
使用FFmpeg将MP4视频、SRT字幕和WAV音轨合并对齐
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, List


class VideoMerger:
    """
    视频合并器
    
    功能：
    1. 将TTS生成的音轨替换原视频音轨
    2. 将更新后的SRT字幕嵌入视频
    3. 支持多种合并模式
    """
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        """
        初始化视频合并器
        
        Args:
            ffmpeg_path: FFmpeg可执行文件路径，默认使用系统PATH中的ffmpeg
        """
        self.ffmpeg_path = ffmpeg_path
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode != 0:
                raise RuntimeError("FFmpeg不可用")
            print(f"✅ FFmpeg可用: {result.stdout.split()[2]}")
        except FileNotFoundError:
            raise RuntimeError(f"未找到FFmpeg: {self.ffmpeg_path}")
        except Exception as e:
            raise RuntimeError(f"FFmpeg检查失败: {e}")
    
    def merge_video_audio_only(
        self,
        video_path: str,
        audio_path: str,
        output_path: str = None,
        mode: str = "replace",
        enable_slowdown: bool = True
    ) -> str:
        """
        只合并视频和音频（不涉及字幕）
        
        Args:
            video_path: 原始MP4视频路径
            audio_path: 音频文件路径
            output_path: 输出视频路径（可选）
            mode: 合并模式
                - "replace": 替换音轨（默认）
                - "mix": 混合音轨（保留原音+新音频）
                - "remove": 仅去除原音轨
            enable_slowdown: 当音频比视频长时，是否自动慢放视频（默认True）
        
        Returns:
            输出视频路径
        """
        print("\n" + "="*60)
        print("🎬 合并视频和音频（无字幕）")
        print("="*60)
        
        # 验证输入文件
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        # 确定输出路径
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_merged{video_path.suffix}"
        else:
            output_path = Path(output_path)
        
        print(f"📹 原视频: {video_path}")
        print(f"🎵 音频: {audio_path}")
        print(f"💾 输出: {output_path}")
        print(f"🔧 模式: {mode}")
        print(f"🔧 自动慢放: {enable_slowdown}")
        
        # 获取视频和音频时长
        video_duration = self._get_media_duration(str(video_path))
        audio_duration = self._get_media_duration(str(audio_path))
        
        print(f"\n📊 媒体信息:")
        print(f"   视频时长: {video_duration:.2f}秒")
        print(f"   音频时长: {audio_duration:.2f}秒")
        
        # 判断是否需要慢放视频
        need_slowdown = enable_slowdown and audio_duration > video_duration * 1.05
        
        if need_slowdown:
            stretch_ratio = audio_duration / video_duration
            print(f"\n🎯 检测到音频比视频长，启用视频慢放同步")
            print(f"   慢放比例: {stretch_ratio:.2f}x")
            
            # 获取视频帧率
            video_fps = self._get_video_fps(str(video_path))
            target_fps = video_fps / stretch_ratio
            
            print(f"   原始帧率: {video_fps:.2f} fps")
            print(f"   目标帧率: {target_fps:.2f} fps")
        
        # 构建FFmpeg命令
        cmd = [self.ffmpeg_path, '-y']
        
        # 输入文件
        cmd.extend(['-i', str(video_path)])
        cmd.extend(['-i', str(audio_path)])
        
        # 视频处理
        if need_slowdown:
            # 慢放视频
            video_filter = f"setpts={stretch_ratio}*PTS,fps={target_fps:.4f}"
            cmd.extend(['-filter:v', video_filter])
        else:
            # 直接复制视频流
            cmd.extend(['-c:v', 'copy'])
        
        # 音频处理
        if mode == "replace":
            # 替换音轨：只使用新音频
            cmd.extend(['-map', '0:v'])  # 视频流来自第一个输入
            cmd.extend(['-map', '1:a'])  # 音频流来自第二个输入
            cmd.extend(['-c:a', 'aac'])
            cmd.extend(['-b:a', '192k'])
        elif mode == "mix":
            # 混合音轨：原音+新音频
            audio_filter = "[0:a][1:a]amix=inputs=2:duration=longest[aout]"
            cmd.extend(['-filter_complex', audio_filter])
            cmd.extend(['-map', '0:v'])
            cmd.extend(['-map', '[aout]'])
            cmd.extend(['-c:a', 'aac'])
            cmd.extend(['-b:a', '192k'])
        elif mode == "remove":
            # 只保留视频，去除所有音轨
            cmd.extend(['-map', '0:v'])
            cmd.extend(['-an'])  # 无音频
        
        # 输出文件
        cmd.append(str(output_path))
        
        # 执行FFmpeg命令
        print(f"\n🎬 执行FFmpeg合并...")
        print(f"命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print(f"\n✅ 合并完成！")
            print(f"   输出文件: {output_path}")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"\n❌ FFmpeg执行失败:")
            print(f"   错误码: {e.returncode}")
            print(f"   错误信息: {e.stderr}")
            raise RuntimeError(f"视频合并失败: {e.stderr}")
    
    def merge_video_audio_subtitle(
        self,
        video_path: str,
        audio_path: str,
        subtitle_path: Optional[str] = None,
        output_path: str = None,
        mode: str = "replace_audio",
        remove_original_audio: bool = True
    ) -> str:
        """
        合并视频、音频和字幕
        
        Args:
            video_path: 原始MP4视频路径
            audio_path: TTS生成的WAV音轨路径
            subtitle_path: 更新后的SRT字幕路径（可选）
            output_path: 输出视频路径（可选，默认在原视频目录）
            mode: 合并模式
                - "replace_audio": 替换音轨（默认）
                - "mix_audio": 混合音轨（保留原音+配音）
                - "embed_subtitle": 嵌入字幕
                - "burn_subtitle": 烧录字幕（硬字幕）
                - "remove_audio": 仅去除原音轨
                - "video_only": 仅保留视频（无音轨）
            remove_original_audio: 是否去除原始音轨（默认True）
        
        Returns:
            输出视频路径
        """
        print("\n" + "="*60)
        print("🎬 开始合并视频、音频和字幕")
        print("="*60)
        
        # 验证输入文件
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        if subtitle_path:
            subtitle_path = Path(subtitle_path)
            if not subtitle_path.exists():
                raise FileNotFoundError(f"字幕文件不存在: {subtitle_path}")
        
        # 确定输出路径
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_dubbed{video_path.suffix}"
        else:
            output_path = Path(output_path)
        
        print(f"📹 原视频: {video_path}")
        print(f"🎵 音轨: {audio_path}")
        if subtitle_path:
            print(f"📝 字幕: {subtitle_path}")
        print(f"💾 输出: {output_path}")
        print(f"🔧 模式: {mode}")
        print(f"🔧 去除原音轨: {remove_original_audio}")
        
        # 根据模式选择合并方法
        if mode == "replace_audio":
            return self._replace_audio(video_path, audio_path, subtitle_path, output_path, remove_original_audio)
        elif mode == "mix_audio":
            return self._mix_audio(video_path, audio_path, subtitle_path, output_path, remove_original_audio)
        elif mode == "embed_subtitle":
            return self._embed_subtitle(video_path, audio_path, subtitle_path, output_path, remove_original_audio)
        elif mode == "burn_subtitle":
            # 烧录字幕模式已合并到replace_audio，这里保留兼容性
            print("⚠️ 注意：burn_subtitle模式已合并到replace_audio，将使用replace_audio模式")
            return self._replace_audio(video_path, audio_path, subtitle_path, output_path, remove_original_audio)
        elif mode == "remove_audio":
            return self._remove_audio_only(video_path, subtitle_path, output_path)
        elif mode == "video_only":
            return self._video_only(video_path, output_path)
        else:
            raise ValueError(f"不支持的合并模式: {mode}")
    
    def _get_video_fps(self, video_path: Path) -> float:
        """获取视频帧率"""
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-hide_banner"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            # FFmpeg的信息在stderr中
            info_text = result.stderr
            
            # 提取帧率 (例如: "30 fps" 或 "29.97 fps")
            import re
            fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', info_text)
            if fps_match:
                return float(fps_match.group(1))
            else:
                print(f"⚠️ 无法解析帧率，使用默认值30fps")
                return 30.0
            
        except Exception as e:
            print(f"⚠️ 获取视频帧率失败: {e}，使用默认值30fps")
            return 30.0
    
    def _adjust_subtitle_timeline(self, subtitle_path: Path, stretch_ratio: float, output_path: Path) -> Path:
        """
        调整字幕时间轴以匹配视频慢放，并验证调整结果
        
        Args:
            subtitle_path: 原始字幕文件路径
            stretch_ratio: 拉伸系数
            output_path: 调整后的字幕文件路径
            
        Returns:
            调整后的字幕文件路径
        """
        print(f"📝 调整字幕时间轴: 拉伸 {stretch_ratio:.3f}x")
        
        try:
            # 读取原始字幕
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析并调整SRT时间轴
            import re
            
            # 记录调整前后的时间戳（用于验证）
            adjustments = []
            
            def adjust_timestamp(match):
                """调整单个时间戳"""
                time_str = match.group(0)
                # 解析时间戳: HH:MM:SS,mmm
                parts = time_str.replace(',', ':').split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                milliseconds = int(parts[3])
                
                # 转换为总毫秒数
                total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
                
                # 应用拉伸系数
                new_total_ms = int(total_ms * stretch_ratio)
                
                # 记录调整（用于验证）
                adjustments.append((total_ms, new_total_ms))
                
                # 转换回时间格式
                new_hours = new_total_ms // 3600000
                new_minutes = (new_total_ms % 3600000) // 60000
                new_seconds = (new_total_ms % 60000) // 1000
                new_milliseconds = new_total_ms % 1000
                
                return f"{new_hours:02d}:{new_minutes:02d}:{new_seconds:02d},{new_milliseconds:03d}"
            
            # 匹配SRT时间戳格式: HH:MM:SS,mmm
            pattern = r'\d{2}:\d{2}:\d{2},\d{3}'
            adjusted_content = re.sub(pattern, adjust_timestamp, content)
            
            # 保存调整后的字幕
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(adjusted_content)
            
            # 验证调整结果
            print(f"✅ 字幕时间轴已调整:")
            print(f"   调整的时间戳数量: {len(adjustments)}")
            if adjustments:
                first_orig, first_new = adjustments[0]
                last_orig, last_new = adjustments[-1]
                print(f"   第一个时间戳: {first_orig/1000:.2f}s → {first_new/1000:.2f}s")
                print(f"   最后时间戳: {last_orig/1000:.2f}s → {last_new/1000:.2f}s")
                print(f"   原始时长: {last_orig/1000:.2f}s")
                print(f"   调整后时长: {last_new/1000:.2f}s")
                print(f"   实际拉伸比: {last_new/last_orig:.3f}x (预期: {stretch_ratio:.3f}x)")
            print(f"   保存到: {output_path}")
            
            return output_path
            
        except Exception as e:
            print(f"⚠️ 字幕时间轴调整失败: {e}")
            import traceback
            traceback.print_exc()
            print(f"   将使用原始字幕文件")
            return subtitle_path
    
    def _replace_audio(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Optional[Path],
        output_path: Path,
        remove_original_audio: bool = True
    ) -> str:
        """
        替换音轨模式：用TTS音轨替换原视频音轨，支持字幕烧录
        支持音视频同步 - 如果音轨更长，会延长视频以匹配音轨长度
        如果提供字幕文件，会自动烧录到视频画面中
        """
        has_subtitle = subtitle_path is not None
        mode_desc = "替换音轨 + 烧录字幕" if has_subtitle else "替换音轨"
        print(f"\n🔄 模式：{mode_desc}（支持音视频同步）")
        
        # 首先获取视频和音频的时长信息
        video_info = self.get_media_duration(video_path)
        audio_info = self.get_media_duration(audio_path)
        
        video_duration = video_info.get('duration_seconds', 0)
        audio_duration = audio_info.get('duration_seconds', 0)
        
        print(f"📹 原视频时长: {video_duration:.2f}秒")
        print(f"🎵 音轨时长: {audio_duration:.2f}秒")
        if has_subtitle:
            print(f"📝 字幕文件: {subtitle_path}")
        
        cmd = [
            self.ffmpeg_path,
            "-y",  # 覆盖输出文件
            "-i", str(video_path),  # 输入视频
            "-i", str(audio_path),  # 输入音频
        ]
        
        # 检查音视频时长差异，计算拉伸系数
        stretch_ratio = 1.0
        need_stretch = False
        original_fps = None
        target_fps = None
        
        if audio_duration > video_duration + 0.1:  # 0.1秒容差
            stretch_ratio = audio_duration / video_duration
            need_stretch = True
            
            # 获取原视频帧率
            original_fps = self._get_video_fps(video_path)
            target_fps = original_fps / stretch_ratio
            
            print(f"🎯 音轨({audio_duration:.2f}秒)比视频({video_duration:.2f}秒)长")
            print(f"   将通过慢放视频来匹配音轨时长")
            print(f"   拉伸系数: {stretch_ratio:.3f}x (视频慢放 {(stretch_ratio-1)*100:.1f}%)")
            print(f"   原视频帧率: {original_fps:.2f}fps")
            print(f"   目标帧率: {target_fps:.2f}fps")
            print(f"   最终视频时长: {audio_duration:.2f}秒")
        
        # 构建视频滤镜
        if has_subtitle:
            # 如果需要慢放，先调整字幕时间轴
            subtitle_to_use = subtitle_path
            if need_stretch:
                # 创建临时调整后的字幕文件
                adjusted_subtitle_path = subtitle_path.parent / f"{subtitle_path.stem}_adjusted{subtitle_path.suffix}"
                subtitle_to_use = self._adjust_subtitle_timeline(subtitle_path, stretch_ratio, adjusted_subtitle_path)
            
            # 转义字幕路径（Windows路径处理）
            subtitle_path_str = str(subtitle_to_use).replace('\\', '/').replace(':', '\\:')
            
            if need_stretch:
                # 慢放视频 + 烧录字幕（字幕时间轴已调整）
                # 关键修复：同时调整时间戳和帧率，避免画面静止
                # setpts 改变时间戳，fps 调整帧率以匹配新的播放速度
                video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps},subtitles='{subtitle_path_str}'[vout]"
            else:
                # 仅烧录字幕
                video_filter = f"[0:v]subtitles='{subtitle_path_str}'[vout]"
            
            cmd.extend([
                "-filter_complex", video_filter,
                "-map", "[vout]",  # 使用处理后的视频流
                "-map", "1:a",     # 使用音频流
            ])
        else:
            # 没有字幕
            if need_stretch:
                # 仅慢放视频
                # 关键修复：同时调整时间戳和帧率，避免画面静止
                video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]"
                cmd.extend([
                    "-filter_complex", video_filter,
                    "-map", "[vout]",  # 使用慢放后的视频流
                    "-map", "1:a",     # 使用音频流
                ])
            else:
                # 正常映射
                cmd.extend([
                    "-map", "0:v",  # 使用原视频流
                    "-map", "1:a",  # 使用音频流
                ])
        
        # 编码设置
        # 如果有字幕烧录或需要慢放视频，必须重新编码
        need_reencode = has_subtitle or need_stretch
        
        cmd.extend([
            "-c:v", "libx264" if need_reencode else "copy",  # 烧录字幕或延长视频需要重新编码
            "-preset", "medium",  # 编码预设
            "-crf", "23",         # 视频质量
            "-c:a", "aac",        # 音频编码为AAC
            "-b:a", "192k",       # 音频比特率
            "-avoid_negative_ts", "make_zero",  # 避免负时间戳
            str(output_path)
        ])
        
        if need_reencode:
            print("⚠️ 注意：烧录字幕或延长视频需要重新编码，可能需要较长时间")
        
        print(f"🔧 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            success_msg = "音轨替换和字幕烧录成功" if has_subtitle else "音轨替换成功"
            print(f"✅ {success_msg}，音视频已同步")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败:")
            print(f"   返回码: {e.returncode}")
            print(f"   错误信息: {e.stderr}")
            raise RuntimeError(f"视频合并失败: {e.stderr}")
    
    def _mix_audio(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Optional[Path],
        output_path: Path
    ) -> str:
        """
        混合音轨模式：保留原音并混合TTS配音
        支持音视频同步 - 如果音轨更长，会延长视频以匹配音轨长度
        """
        print("\n🔄 模式：混合音轨（原音+配音，支持音视频同步）")
        
        # 获取时长信息
        video_info = self.get_media_duration(video_path)
        audio_info = self.get_media_duration(audio_path)
        
        video_duration = video_info.get('duration_seconds', 0)
        audio_duration = audio_info.get('duration_seconds', 0)
        
        print(f"📹 原视频时长: {video_duration:.2f}秒")
        print(f"🎵 TTS音轨时长: {audio_duration:.2f}秒")
        
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
        ]
        
        if subtitle_path:
            cmd.extend(["-i", str(subtitle_path)])
        
        # 检查音视频时长差异，计算拉伸系数
        stretch_ratio = 1.0
        need_stretch = False
        target_fps = None
        
        if audio_duration > video_duration + 0.1:  # 0.1秒容差
            stretch_ratio = audio_duration / video_duration
            need_stretch = True
            
            # 获取原视频帧率并计算目标帧率
            original_fps = self._get_video_fps(video_path)
            target_fps = original_fps / stretch_ratio
            
            print(f"🎯 TTS音轨({audio_duration:.2f}秒)比视频({video_duration:.2f}秒)长")
            print(f"   将通过慢放视频来匹配音轨时长")
            print(f"   拉伸系数: {stretch_ratio:.3f}x (视频慢放 {(stretch_ratio-1)*100:.1f}%)")
            print(f"   原视频帧率: {original_fps:.2f}fps → 目标帧率: {target_fps:.2f}fps")
        
        # 构建复合滤镜
        if need_stretch:
            # 慢放视频 + 混合音频
            # 注意：原视频音轨也需要慢放以匹配视频
            # 关键修复：同时调整时间戳和帧率，避免画面静止
            filter_complex = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]; [0:a]atempo={1/stretch_ratio}[a0]; [a0][1:a]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]",
            ])
        else:
            # 正常混合音频
            audio_filter = "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
            cmd.extend([
                "-filter_complex", audio_filter,
                "-map", "0:v",
                "-map", "[aout]",
            ])
        
        if subtitle_path:
            subtitle_input_index = "2" if subtitle_path else "1"
            cmd.extend([
                "-map", f"{subtitle_input_index}:s?",
                "-c:s", "mov_text",
            ])
        
        cmd.extend([
            "-c:v", "libx264" if audio_duration > video_duration + 0.1 else "copy",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-avoid_negative_ts", "make_zero",
            str(output_path)
        ])
        
        # 移除 -shortest 参数，使用 duration=longest 来保持最长的流
        
        print(f"🔧 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print("✅ 音轨混合成功，音视频已同步")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e.stderr}")
            raise RuntimeError(f"视频合并失败: {e.stderr}")
    
    def _embed_subtitle(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
        remove_original_audio: bool = True
    ) -> str:
        """
        嵌入字幕模式：将字幕作为软字幕嵌入视频
        支持音视频同步 - 如果音轨更长，会延长视频以匹配音轨长度
        """
        print("\n🔄 模式：嵌入字幕（软字幕，支持音视频同步）")
        
        if not subtitle_path:
            raise ValueError("嵌入字幕模式需要提供字幕文件")
        
        # 获取时长信息
        video_info = self.get_media_duration(video_path)
        audio_info = self.get_media_duration(audio_path)
        
        video_duration = video_info.get('duration_seconds', 0)
        audio_duration = audio_info.get('duration_seconds', 0)
        
        print(f"📹 原视频时长: {video_duration:.2f}秒")
        print(f"🎵 音轨时长: {audio_duration:.2f}秒")
        
        # 检查音视频时长差异，计算拉伸系数
        stretch_ratio = 1.0
        need_stretch = False
        target_fps = None
        
        if audio_duration > video_duration + 0.1:  # 0.1秒容差
            stretch_ratio = audio_duration / video_duration
            need_stretch = True
            
            # 获取原视频帧率并计算目标帧率
            original_fps = self._get_video_fps(video_path)
            target_fps = original_fps / stretch_ratio
            
            print(f"🎯 音轨({audio_duration:.2f}秒)比视频({video_duration:.2f}秒)长")
            print(f"   将通过慢放视频来匹配音轨时长")
            print(f"   拉伸系数: {stretch_ratio:.3f}x (视频慢放 {(stretch_ratio-1)*100:.1f}%)")
            print(f"   原视频帧率: {original_fps:.2f}fps → 目标帧率: {target_fps:.2f}fps")
        
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-i", str(subtitle_path),
        ]
        
        if need_stretch:
            # 慢放视频
            # 关键修复：同时调整时间戳和帧率，避免画面静止
            video_filter = f"[0:v]setpts={stretch_ratio}*PTS,fps={target_fps}[vout]"
            cmd.extend([
                "-filter_complex", video_filter,
                "-map", "[vout]",
                "-map", "1:a",
                "-map", "2:s",
            ])
        else:
            cmd.extend([
                "-map", "0:v",
                "-map", "1:a",
                "-map", "2:s",
            ])
        
        cmd.extend([
            "-c:v", "libx264" if need_stretch else "copy",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=chi",  # 设置字幕语言
            "-metadata:s:s:0", "title=Chinese",
            "-avoid_negative_ts", "make_zero",
            str(output_path)
        ])
        
        print(f"🔧 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print("✅ 字幕嵌入成功，音视频已同步")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e.stderr}")
            raise RuntimeError(f"视频合并失败: {e.stderr}")
    
    def _burn_subtitle(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
        remove_original_audio: bool = True
    ) -> str:
        """
        烧录字幕模式：将字幕烧录到视频画面（硬字幕）
        支持音视频同步 - 如果音轨更长，会延长视频以匹配音轨长度
        """
        print("\n🔄 模式：烧录字幕（硬字幕，支持音视频同步）")
        
        if not subtitle_path:
            raise ValueError("烧录字幕模式需要提供字幕文件")
        
        # 获取时长信息
        video_info = self.get_media_duration(video_path)
        audio_info = self.get_media_duration(audio_path)
        
        video_duration = video_info.get('duration_seconds', 0)
        audio_duration = audio_info.get('duration_seconds', 0)
        
        print(f"📹 原视频时长: {video_duration:.2f}秒")
        print(f"🎵 音轨时长: {audio_duration:.2f}秒")
        
        # 转义字幕路径中的特殊字符
        subtitle_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
        
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
        ]
        
        # 如果音轨比视频长，需要延长视频并烧录字幕
        if audio_duration > video_duration + 0.1:  # 0.1秒容差
            print(f"🔄 音轨较长，将延长视频并烧录字幕以匹配音轨时长")
            # 创建复合滤镜：延长视频 + 烧录字幕
            video_filter = f"[0:v]loop=loop=-1:size=1:start=0,trim=duration={audio_duration},subtitles='{subtitle_path_escaped}'[vout]"
            cmd.extend([
                "-filter_complex", video_filter,
                "-map", "[vout]",
                "-map", "1:a",
            ])
        else:
            # 视频不需要延长，直接烧录字幕
            cmd.extend([
                "-vf", f"subtitles='{subtitle_path_escaped}'",
                "-map", "0:v",
                "-map", "1:a",
            ])
        
        cmd.extend([
            "-c:v", "libx264",  # 需要重新编码视频
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-avoid_negative_ts", "make_zero",
            str(output_path)
        ])
        
        print(f"🔧 执行命令: {' '.join(cmd)}")
        print("⚠️ 注意：烧录字幕需要重新编码视频，可能需要较长时间")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print("✅ 字幕烧录成功，音视频已同步")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e.stderr}")
            raise RuntimeError(f"视频合并失败: {e.stderr}")
    
    def get_media_duration(self, media_path: Path) -> Dict:
        """
        获取媒体文件时长
        
        Args:
            media_path: 媒体文件路径
            
        Returns:
            包含时长信息的字典
        """
        cmd = [
            self.ffmpeg_path,
            "-i", str(media_path),
            "-hide_banner"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            # FFmpeg的信息在stderr中
            info_text = result.stderr
            
            # 提取时长
            import re
            duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", info_text)
            if duration_match:
                h, m, s = duration_match.groups()
                duration_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                return {
                    "path": str(media_path),
                    "duration_seconds": duration_seconds,
                    "duration_formatted": f"{h}:{m}:{s}"
                }
            else:
                print(f"⚠️ 无法解析时长信息: {media_path}")
                return {"path": str(media_path), "duration_seconds": 0}
            
        except Exception as e:
            print(f"⚠️ 获取媒体时长失败: {e}")
            return {"path": str(media_path), "duration_seconds": 0, "error": str(e)}

    def get_video_info(self, video_path: str) -> Dict:
        """
        获取视频信息
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频信息字典
        """
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-hide_banner"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            # FFmpeg的信息在stderr中
            info_text = result.stderr
            
            # 解析基本信息
            info = {
                "path": video_path,
                "has_video": "Video:" in info_text,
                "has_audio": "Audio:" in info_text,
                "has_subtitle": "Subtitle:" in info_text,
            }
            
            # 提取时长
            import re
            duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", info_text)
            if duration_match:
                h, m, s = duration_match.groups()
                info["duration_seconds"] = int(h) * 3600 + int(m) * 60 + float(s)
            
            return info
            
        except Exception as e:
            print(f"⚠️ 获取视频信息失败: {e}")
            return {"path": video_path, "error": str(e)}
    
    def _remove_audio_only(self, video_path: Path, subtitle_path: Optional[Path], output_path: Path) -> str:
        """
        仅去除音轨模式：移除视频中的音轨，保留视频流
        """
        print("\n🔄 模式：去除音轨")
        
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_path),
        ]
        
        if subtitle_path:
            cmd.extend(["-i", str(subtitle_path)])
        
        # 仅映射视频流
        cmd.extend([
            "-map", "0:v",  # 仅使用视频流
            "-c:v", "copy",  # 复制视频流
        ])
        
        if subtitle_path:
            cmd.extend([
                "-map", "1:s?",
                "-c:s", "mov_text",
            ])
        
        cmd.append(str(output_path))
        
        print(f"🔧 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print("✅ 音轨移除成功")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e.stderr}")
            raise RuntimeError(f"音轨移除失败: {e.stderr}")
    
    def _video_only(self, video_path: Path, output_path: Path) -> str:
        """
        仅视频模式：提取视频流，无音轨无字幕
        """
        print("\n🔄 模式：仅保留视频")
        
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-map", "0:v",  # 仅视频流
            "-c:v", "copy",  # 复制视频流
            "-an",  # 无音频
            str(output_path)
        ]
        
        print(f"🔧 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=True
            )
            print("✅ 视频提取成功")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg执行失败: {e.stderr}")
            raise RuntimeError(f"视频提取失败: {e.stderr}")


# 使用示例
if __name__ == "__main__":
    # 创建合并器
    merger = VideoMerger()
    
    # 示例1：替换音轨
    try:
        output = merger.merge_video_audio_subtitle(
            video_path="input/video.mp4",
            audio_path="output/dubbing_result.wav",
            subtitle_path="output/updated_subtitles.srt",
            mode="replace_audio"
        )
        print(f"✅ 合并完成: {output}")
    except Exception as e:
        print(f"❌ 合并失败: {e}")
    
    # 示例2：获取视频信息
    info = merger.get_video_info("input/video.mp4")
    print(f"视频信息: {info}")
