"""
视频字幕烧录模块
专注于视频和硬字幕的烧录合并，导出带字幕的MP4文件

支持GPU加速：
- 自动检测NVIDIA GPU可用性
- 使用h264_nvenc硬件编码器加速
- 支持CUDA硬件解码加速
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, List

# 尝试相对导入，如果失败则使用绝对导入
try:
    from .srt_cleaner import SrtCleaner
except ImportError:
    try:
        from srt_cleaner import SrtCleaner
    except ImportError:
        # 如果都失败，定义一个简单的内联版本
        import re
        
        class SrtCleaner:
            """简单的SRT清理器（内联版本）"""
            
            def __init__(self):
                # 匹配说话人标识的正则表达式
                self.speaker_pattern = re.compile(r'\[spk\d+\]:\s*')
                # 额外的清理模式
                self.additional_patterns = [
                    re.compile(r'\[speaker\d+\]:\s*', re.IGNORECASE),
                    re.compile(r'\[说话人\d+\]:\s*'),
                    re.compile(r'\[\w+\d*\]:\s*'),
                ]
            
            def clean_srt_content(self, content: str) -> str:
                """清理SRT内容，去除说话人标识"""
                lines = content.split('\n')
                cleaned_lines = []
                
                for line in lines:
                    # 首先使用主要的说话人模式清理
                    cleaned_line = self.speaker_pattern.sub('', line)
                    
                    # 然后使用额外的模式进行清理
                    for pattern in self.additional_patterns:
                        cleaned_line = pattern.sub('', cleaned_line)
                    
                    cleaned_lines.append(cleaned_line)
                
                return '\n'.join(cleaned_lines)
            
            def clean_srt_file(self, input_path: str, output_path: Optional[str] = None) -> str:
                """清理SRT文件"""
                input_path = Path(input_path)
                
                if not input_path.exists():
                    raise FileNotFoundError(f"SRT文件不存在: {input_path}")
                
                if output_path is None:
                    output_path = input_path.parent / f"{input_path.stem}_cleaned{input_path.suffix}"
                else:
                    output_path = Path(output_path)
                
                print(f"🧹 清理SRT文件:")
                print(f"   输入: {input_path}")
                print(f"   输出: {output_path}")
                
                try:
                    with open(input_path, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    
                    cleaned_content = self.clean_srt_content(original_content)
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(cleaned_content)
                    
                    print(f"✅ SRT清理完成: {output_path}")
                    return str(output_path)
                    
                except Exception as e:
                    print(f"❌ SRT清理失败: {e}")
                    raise


class VideoMerger:
    """
    视频合并器 - 专注于视频和硬字幕烧录合并
    
    功能：
    1. 将视频和字幕合并，烧录硬字幕到视频画面
    2. 支持字体大小和字体样式自定义
    3. 导出带字幕的MP4文件
    4. 自动检测并使用GPU加速（如果可用）
    """
    
    def __init__(
        self, 
        ffmpeg_path: str = None, 
        subtitle_font_size: int = 24, 
        subtitle_font_name: str = "Arial",
        use_gpu: bool = None,  # None=自动检测, True=强制使用, False=强制禁用
        gpu_id: int = 0
    ):
        """
        初始化视频合并器
        
        Args:
            ffmpeg_path: FFmpeg可执行文件路径，默认自动检测
            subtitle_font_size: 字幕字体大小，默认24
            subtitle_font_name: 字幕字体名称，默认Arial
            use_gpu: GPU使用模式
                - None: 自动检测GPU可用性
                - True: 强制使用GPU（如果不可用会报错）
                - False: 强制使用CPU
            gpu_id: GPU设备ID，默认0
        """
        self.ffmpeg_path = ffmpeg_path or self._detect_ffmpeg_path()
        self.subtitle_font_size = subtitle_font_size
        self.subtitle_font_name = subtitle_font_name
        self.gpu_id = gpu_id
        
        # GPU加速配置
        self._gpu_available = self._check_gpu_availability()
        self._nvenc_available = self._check_nvenc_availability()
        
        # 确定是否使用GPU
        if use_gpu is None:
            # 自动检测模式
            self.use_gpu = self._gpu_available and self._nvenc_available
        elif use_gpu:
            # 强制使用GPU
            if not self._gpu_available:
                raise RuntimeError("GPU不可用，无法强制使用GPU模式")
            if not self._nvenc_available:
                raise RuntimeError("NVENC编码器不可用，无法强制使用GPU模式")
            self.use_gpu = True
        else:
            # 强制使用CPU
            self.use_gpu = False
        
        self._check_ffmpeg()
        self._print_acceleration_status()
    
    def _detect_ffmpeg_path(self) -> str:
        """
        自动检测FFmpeg路径
        
        Returns:
            FFmpeg可执行文件路径
        """
        import platform
        
        system = platform.system()
        
        # 1. 尝试项目目录中的FFmpeg
        if system == "Windows":
            project_ffmpeg = Path("ffmpeg/bin/ffmpeg.exe")
            if project_ffmpeg.exists():
                return str(project_ffmpeg)
        else:
            project_ffmpeg = Path("ffmpeg/bin/ffmpeg")
            if project_ffmpeg.exists():
                return str(project_ffmpeg)
        
        # 2. 尝试系统PATH中的FFmpeg
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg
        
        # 3. 默认值
        return "ffmpeg.exe" if system == "Windows" else "ffmpeg"
    
    def _check_gpu_availability(self) -> bool:
        """
        检查NVIDIA GPU是否可用
        
        Returns:
            GPU是否可用
        """
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                self._gpu_name = result.stdout.strip().split('\n')[0]
                return True
            return False
            
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        except Exception:
            return False
    
    def _check_nvenc_availability(self) -> bool:
        """
        检查FFmpeg是否支持NVENC硬件编码
        
        Returns:
            NVENC是否可用
        """
        if not self._gpu_available:
            return False
        
        try:
            result = subprocess.run(
                [self.ffmpeg_path, '-encoders'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=10
            )
            
            if result.returncode == 0:
                return 'h264_nvenc' in result.stdout
            return False
            
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        except Exception:
            return False
    
    def _print_acceleration_status(self):
        """打印加速状态信息"""
        print("\n" + "="*50)
        print("🖥️  硬件加速状态")
        print("="*50)
        
        if self._gpu_available:
            print(f"✅ GPU检测: {getattr(self, '_gpu_name', 'NVIDIA GPU')}")
        else:
            print("❌ GPU检测: 未检测到NVIDIA GPU")
        
        if self._nvenc_available:
            print("✅ NVENC编码器: 可用")
        else:
            print("❌ NVENC编码器: 不可用")
        
        if self.use_gpu:
            print("🚀 加速模式: GPU硬件加速")
        else:
            print("💻 加速模式: CPU软件编码")
        
        print("="*50 + "\n")
    
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
    
    def burn_subtitle_to_video(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str = None,
        subtitle_font_size: Optional[int] = None,
        subtitle_font_name: Optional[str] = None,
        subtitle_color: str = "white",
        subtitle_outline_color: str = "black",
        subtitle_outline_width: int = 2,
        subtitle_position: str = "bottom",
        subtitle_bold_weight: int = 0,
        subtitle_margin_v: int = 20
    ) -> str:
        """
        将字幕烧录到视频中（硬字幕）
        
        Args:
            video_path: 原始MP4视频路径
            subtitle_path: SRT字幕文件路径
            output_path: 输出视频路径（可选）
            subtitle_font_size: 字幕字体大小（可选，如果不指定则使用初始化时的默认值）
            subtitle_font_name: 字幕字体名称（可选，如果不指定则使用初始化时的默认值）
            subtitle_color: 字幕颜色，默认白色
            subtitle_outline_color: 字幕描边颜色，默认黑色
            subtitle_outline_width: 字幕描边宽度，默认2
            subtitle_position: 字幕位置，默认bottom（底部）
            subtitle_bold_weight: 字体粗细（0-900），0=正常，400=常规粗体，700=加粗，900=特粗，默认0
            subtitle_margin_v: 垂直边距（像素），默认20
        
        Returns:
            输出视频路径
        """
        print("\n" + "="*60)
        print("🎬 开始视频字幕烧录合并")
        print("="*60)
        
        # 验证输入文件
        video_path = Path(video_path)
        subtitle_path = Path(subtitle_path)
        
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not subtitle_path.exists():
            raise FileNotFoundError(f"字幕文件不存在: {subtitle_path}")
        
        # 确定输出路径
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_with_subtitles{video_path.suffix}"
        else:
            output_path = Path(output_path)
        
        print(f"📹 原视频: {video_path}")
        print(f"📝 字幕: {subtitle_path}")
        print(f"💾 输出: {output_path}")
        
        # 使用传入的字体设置，如果没有指定则使用默认值
        font_size = subtitle_font_size if subtitle_font_size is not None else self.subtitle_font_size
        font_name = subtitle_font_name if subtitle_font_name is not None else self.subtitle_font_name
        
        print(f"🎨 字体设置:")
        print(f"   字体: {font_name}")
        print(f"   大小: {font_size}")
        print(f"   粗细: {subtitle_bold_weight} {'(正常)' if subtitle_bold_weight == 0 else '(加粗)' if subtitle_bold_weight >= 400 else ''}")
        print(f"   颜色: {subtitle_color}")
        print(f"   描边: {subtitle_outline_color} (宽度: {subtitle_outline_width})")
        print(f"   位置: {subtitle_position}")
        print(f"   垂直边距: {subtitle_margin_v}px")
        
        # 转义字幕路径中的特殊字符（Windows路径处理）
        subtitle_path_str = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
        
        print(f"🔧 FFmpeg将使用的字幕文件路径: {subtitle_path_str}")
        
        # 位置映射
        position_map = {
            'top': 8,           # 顶部居中
            'middle': 5,        # 中部居中
            'bottom': 2,        # 底部居中
            'top-left': 7,      # 顶部左对齐
            'top-right': 9,     # 顶部右对齐
            'bottom-left': 1,   # 底部左对齐
            'bottom-right': 3   # 底部右对齐
        }
        
        alignment = position_map.get(subtitle_position, 2)  # 默认底部居中
        
        # 构建字幕样式
        # Bold: 0=正常, -1=粗体（传统方式）
        # 或者使用具体数值: 0-900 (0=正常, 400=常规粗体, 700=加粗, 900=特粗)
        # ASS格式支持 -1(粗体) 或 0(正常)，但某些实现支持数值
        # 为了兼容性，我们将数值映射为 -1 或 0
        if subtitle_bold_weight >= 400:
            bold_value = -1  # 粗体
        else:
            bold_value = 0   # 正常
        
        subtitle_style = (
            f"FontName={font_name},"
            f"FontSize={font_size},"
            f"Bold={bold_value},"
            f"PrimaryColour=&H{self._color_to_hex(subtitle_color)},"
            f"OutlineColour=&H{self._color_to_hex(subtitle_outline_color)},"
            f"Outline={subtitle_outline_width},"
            f"Alignment={alignment},"
            f"MarginV={subtitle_margin_v}"
        )
        
        # 构建FFmpeg命令
        cmd = [
            self.ffmpeg_path,
            "-y",  # 覆盖输出文件
        ]
        
        # GPU硬件解码加速（如果可用）
        if self.use_gpu:
            cmd.extend([
                '-hwaccel', 'cuda',
                '-hwaccel_device', str(self.gpu_id),
            ])
        
        cmd.extend(["-i", str(video_path)])  # 输入视频
        
        # 添加字幕烧录滤镜
        subtitle_filter = f"subtitles='{subtitle_path_str}':force_style='{subtitle_style}'"
        
        cmd.extend(["-vf", subtitle_filter])  # 视频滤镜
        
        # 视频编码器设置
        if self.use_gpu:
            # 使用NVIDIA GPU硬件编码器
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p4",  # NVENC预设 (p1最快-p7最慢质量最好)
                "-cq", "23",      # 恒定质量模式
                "-b:v", "0",      # 禁用比特率限制，使用CQ模式
            ])
            print("🚀 使用GPU硬件编码 (h264_nvenc)")
        else:
            # 使用CPU软件编码器
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
            ])
            print("💻 使用CPU软件编码 (libx264)")
        
        cmd.extend([
            "-c:a", "copy",         # 音频直接复制
            str(output_path)
        ])
        
        print(f"\n🔧 执行FFmpeg命令:")
        print(f"   {' '.join(cmd)}")
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
            print(f"\n✅ 字幕烧录完成！")
            print(f"   输出文件: {output_path}")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            print(f"\n❌ FFmpeg执行失败:")
            print(f"   错误码: {e.returncode}")
            print(f"   错误信息: {e.stderr}")
            raise RuntimeError(f"字幕烧录失败: {e.stderr}")
    
    def burn_subtitle_to_video_with_cleaning(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str = None,
        subtitle_font_size: Optional[int] = None,
        subtitle_font_name: Optional[str] = None,
        subtitle_color: str = "white",
        subtitle_outline_color: str = "black",
        subtitle_outline_width: int = 2,
        subtitle_position: str = "bottom",
        subtitle_bold_weight: int = 0,
        subtitle_margin_v: int = 20,
        clean_speakers: bool = True
    ) -> str:
        """
        将字幕烧录到视频中（硬字幕），支持自动清理说话人标识
        
        Args:
            video_path: 原始MP4视频路径
            subtitle_path: SRT字幕文件路径
            output_path: 输出视频路径（可选）
            subtitle_font_size: 字幕字体大小（可选）
            subtitle_font_name: 字幕字体名称（可选）
            subtitle_color: 字幕颜色，默认白色
            subtitle_outline_color: 字幕描边颜色，默认黑色
            subtitle_outline_width: 字幕描边宽度，默认2
            subtitle_position: 字幕位置，默认bottom（底部）
            subtitle_bold_weight: 字体粗细（0-900），默认0
            subtitle_margin_v: 垂直边距（像素），默认20
            clean_speakers: 是否清理说话人标识，默认True
        
        Returns:
            输出视频路径
        """
        print("\n" + "="*60)
        print("🎬 开始视频字幕烧录合并（支持说话人标识清理）")
        print("="*60)
        
        # 验证输入文件
        video_path = Path(video_path)
        subtitle_path = Path(subtitle_path)
        
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not subtitle_path.exists():
            raise FileNotFoundError(f"字幕文件不存在: {subtitle_path}")
        
        # 处理字幕文件
        subtitle_to_use = subtitle_path
        if clean_speakers:
            print("🧹 检测到需要清理说话人标识")
            print(f"   原始字幕文件: {subtitle_path}")
            
            # 先检查原始文件内容
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            import re
            # 更新正则表达式以匹配有空格和没有空格的情况
            # 例如: [spk01]: 或 [spk01] :
            original_count = len(re.findall(r'\[spk\d+\]\s*:', original_content))
            print(f"   原始文件中的说话人标识数量: {original_count}")
            
            cleaner = SrtCleaner()
            
            # 创建临时清理后的字幕文件
            temp_subtitle_path = subtitle_path.parent / f"{subtitle_path.stem}_temp_cleaned{subtitle_path.suffix}"
            print(f"   临时清理文件路径: {temp_subtitle_path}")
            
            subtitle_to_use = Path(cleaner.clean_srt_file(str(subtitle_path), str(temp_subtitle_path)))
            print(f"   清理后字幕文件: {subtitle_to_use}")
            
            # 验证清理结果
            with open(subtitle_to_use, 'r', encoding='utf-8') as f:
                cleaned_content = f.read()
            
            cleaned_count = len(re.findall(r'\[spk\d+\]\s*:', cleaned_content))
            print(f"   清理后剩余的说话人标识数量: {cleaned_count}")
            if original_count > 0:
                print(f"   清理成功率: {((original_count - cleaned_count) / original_count * 100):.1f}%")
            
            # 显示清理前后的对比示例
            print("   清理前后对比示例:")
            original_lines = original_content.split('\n')
            cleaned_lines = cleaned_content.split('\n')
            
            count = 0
            for i, (orig, clean) in enumerate(zip(original_lines, cleaned_lines)):
                if orig != clean and '[spk' in orig:
                    print(f"     行 {i+1}: '{orig}' -> '{clean}'")
                    count += 1
                    if count >= 2:  # 只显示前2个示例
                        break
        else:
            print("⚠️ 未启用说话人标识清理")
        
        print(f"🎯 最终传递给FFmpeg的字幕文件: {subtitle_to_use}")
        
        try:
            # 调用原始的字幕烧录方法
            result = self.burn_subtitle_to_video(
                video_path=str(video_path),
                subtitle_path=str(subtitle_to_use),
                output_path=output_path,
                subtitle_font_size=subtitle_font_size,
                subtitle_font_name=subtitle_font_name,
                subtitle_color=subtitle_color,
                subtitle_outline_color=subtitle_outline_color,
                subtitle_outline_width=subtitle_outline_width,
                subtitle_position=subtitle_position,
                subtitle_bold_weight=subtitle_bold_weight,
                subtitle_margin_v=subtitle_margin_v
            )
            
            return result
            
        finally:
            # 清理临时文件
            if clean_speakers and subtitle_to_use != subtitle_path:
                try:
                    subtitle_to_use.unlink()
                    print(f"🗑️ 已清理临时文件: {subtitle_to_use}")
                except Exception as e:
                    print(f"⚠️ 清理临时文件失败: {e}")
    
    def _color_to_hex(self, color_name: str) -> str:
        """
        将颜色名称转换为BGR十六进制格式（FFmpeg使用BGR格式）
        
        Args:
            color_name: 颜色名称
            
        Returns:
            BGR十六进制颜色代码
        """
        color_map = {
            'white': 'FFFFFF',
            'black': '000000',
            'red': '0000FF',
            'green': '00FF00',
            'blue': 'FF0000',
            'yellow': '00FFFF',
            'cyan': 'FFFF00',
            'magenta': 'FF00FF',
            'gray': '808080',
            'grey': '808080'
        }
        
        return color_map.get(color_name.lower(), 'FFFFFF')  # 默认白色
    
    def _get_media_duration(self, media_path: str) -> float:
        """
        获取媒体文件时长（秒）
        
        Args:
            media_path: 媒体文件路径
            
        Returns:
            时长（秒）
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
                return duration_seconds
            else:
                print(f"⚠️ 无法解析时长信息: {media_path}")
                return 0.0
            
        except Exception as e:
            print(f"⚠️ 获取媒体时长失败: {e}")
            return 0.0

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


# 使用示例
if __name__ == "__main__":
    # 创建合并器（自动检测GPU）
    # use_gpu=None: 自动检测
    # use_gpu=True: 强制使用GPU
    # use_gpu=False: 强制使用CPU
    merger = VideoMerger(
        subtitle_font_size=28, 
        subtitle_font_name="Microsoft YaHei",
        use_gpu=None  # 自动检测GPU
    )
    
    # 示例：烧录字幕到视频
    try:
        output = merger.burn_subtitle_to_video_with_cleaning(
            video_path="input/video.mp4",
            subtitle_path="input/subtitles.srt",
            subtitle_font_size=32,
            subtitle_font_name="Arial",
            subtitle_color="yellow",
            clean_speakers=True
        )
        print(f"✅ 字幕烧录完成: {output}")
    except Exception as e:
        print(f"❌ 字幕烧录失败: {e}")
    
    # 示例：获取视频信息
    info = merger.get_video_info("input/video.mp4")
    print(f"视频信息: {info}")